#!/usr/bin/env python3
"""T0.5/T0.6 冒烟脚本:连接 → 同步模式 → spawn 车+RGB 相机 → 100 帧取帧 → autopilot 巡航。

用法: python smoke_carla.py --port 2000 --minutes 5 --out /home/xsl/MySim/logs/smoke-ue5.json
判据对应: spawn+取帧+autopilot N 分钟无崩溃;同步跟随率;RGB 流吞吐/丢帧;RPC 延迟。
0.9/0.10 API 差异项一律 try/except 记录,不让脚本整体失败。
"""
import argparse, json, time, traceback

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=None, help="默认动态取宿主 IP")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--minutes", type=float, default=5.0)
    ap.add_argument("--frames", type=int, default=100)
    ap.add_argument("--dt", type=float, default=0.05)
    ap.add_argument("--town", default=None, help="指定地图;缺省用当前")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    host = args.host
    if not host:
        import subprocess
        host = subprocess.check_output(
            "ip route show | awk '/default/{print $3}'", shell=True).decode().strip()

    report = {"host": host, "port": args.port, "dt": args.dt, "events": [], "probes": {}}
    t0 = time.time()

    import carla  # 环境内提供 carla 或 carla-ue5-api

    # RPC 延迟
    t_rpc = time.time()
    client = carla.Client(host, args.port)
    client.set_timeout(30.0)
    world = client.get_world()
    report["rpc_latency_s"] = round(time.time() - t_rpc, 3)
    report["server_version"] = world.get_actors() is not None
    try:
        report["map"] = world.get_map().name
    except Exception:
        report["map"] = "unavailable"

    if args.town:
        try:
            world = client.load_world(args.town)
            report["map"] = args.town
        except Exception as e:
            report["events"].append(f"load_world {args.town} 失败: {e}")

    # 可用地图清单(T0.3 判据需要)
    try:
        report["probes"]["available_maps"] = client.get_available_maps()
    except Exception as e:
        report["probes"]["available_maps"] = f"unavailable: {e}"

    # 同步模式
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = args.dt
    world.apply_settings(settings)

    # TM:端口实测候选(0.9 默认 8000;多实例约定 port+2;旧误算 port+8000 兜底)
    tm = None
    tm_errors = {}
    for cand in [8000, args.port + 2, args.port + 8000]:
        try:
            tm = client.get_trafficmanager(cand)
            tm.set_synchronous_mode(True)
            report["probes"]["traffic_manager"] = f"ok (port {cand})"
            break
        except Exception as e:
            tm_errors[cand] = str(e)[:120]
            tm = None
    if tm is None:
        report["probes"]["traffic_manager"] = f"unavailable: {tm_errors}"

    bp_lib = world.get_blueprint_library()
    vbp = bp_lib.filter("vehicle.tesla.model3") or bp_lib.filter("vehicle.*")
    spawn_pts = world.get_map().get_spawn_points()
    vehicle = None
    for sp in spawn_pts:
        try:
            vehicle = world.spawn_actor(vbp[0], sp)
            break
        except Exception:
            continue
    if vehicle is None:
        raise RuntimeError("spawn 车辆失败")
    report["vehicle"] = vehicle.type_id

    # RGB 相机 1280x720
    cam_bp = bp_lib.find("sensor.camera.rgb")
    cam_bp.set_attribute("image_size_x", "1280")
    cam_bp.set_attribute("image_size_y", "720")
    cam_bp.set_attribute("fov", "110")
    cam = world.spawn_actor(cam_bp, carla.Transform(carla.Location(x=1.5, z=2.4)), attach_to=vehicle)

    frames = {"n": 0, "bytes": 0, "first_ts": None, "last_ts": None, "gaps": 0, "last_frame": None}
    def on_img(img):
        frames["n"] += 1
        frames["bytes"] += len(img.raw_data)
        ts = time.time()
        if frames["first_ts"] is None: frames["first_ts"] = ts
        if frames["last_ts"] is not None and (img.frame - frames["last_frame"]) > 1:
            frames["gaps"] += img.frame - frames["last_frame"] - 1
        frames["last_ts"] = ts
        frames["last_frame"] = img.frame
    cam.listen(on_img)

    # 同步跟随率测试:踩 200 步量实测耗时
    t_sync = time.time()
    for _ in range(200):
        world.tick()
    sync_elapsed = time.time() - t_sync
    report["sync"] = {"ticks": 200, "elapsed_s": round(sync_elapsed, 2),
                      "achieved_fps": round(200 / sync_elapsed, 1),
                      "target_fps": round(1.0 / args.dt, 1)}
    print(f"[stage] sync done: {report['sync']}", flush=True)

    if tm and vehicle:
        try:
            vehicle.set_autopilot(True, tm.get_port())
        except Exception:
            vehicle.set_autopilot(True)
    print("[stage] autopilot on, cruise start", flush=True)

    # autopilot 巡航 N 分钟(每 30s 心跳,崩了也知道死在第几分钟)
    t_cruise = time.time()
    last_hb = t_cruise
    while time.time() - t_cruise < args.minutes * 60:
        world.tick()
        if time.time() - last_hb > 30:
            print(f"[stage] cruise {int(time.time()-t_cruise)}s frames={frames['n']}", flush=True)
            last_hb = time.time()
    print(f"[stage] cruise done frames={frames['n']}", flush=True)

    cam.stop(); cam.destroy(); vehicle.destroy()
    print("[stage] actors destroyed", flush=True)
    report["camera"] = {"frames": frames["n"], "MB": round(frames["bytes"] / 2**20, 1),
                        "dropped_frames": frames["gaps"],
                        "wall_s": round((frames["last_ts"] or t0) - (frames["first_ts"] or t0), 1)}
    report["elapsed_s"] = round(time.time() - t0, 1)
    report["result"] = "PASS"

    # 先落盘再恢复异步:carla-ue5-api 0.10.0 客户端在恢复异步 apply_settings 时
    # 会直接 C++ abort(std::exception 逃逸),不可 catch——数据必须先保住。
    with open(args.out, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # 恢复异步(已知会 abort 客户端进程,放最后;server 端状态不受影响)
    try:
        settings.synchronous_mode = False
        world.apply_settings(settings)
    except Exception:
        pass

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        raise SystemExit(f"SMOKE_FAIL: {e}")
