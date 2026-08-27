#!/usr/bin/env python3
"""T0.5 前置:CARLA 0.10 API 能力探测。逐项 try/except,输出 JSON 可用性清单。

用法: python probe_ue5_api.py --port 2000 --out logs/probe-ue5.json
"""
import argparse, json, subprocess, time

SENSORS = [
    "sensor.camera.rgb", "sensor.camera.depth", "sensor.camera.semantic_segmentation",
    "sensor.camera.instance_segmentation", "sensor.camera.dvs", "sensor.camera.optical_flow",
    "sensor.lidar.ray_cast", "sensor.lidar.ray_cast_semantic", "sensor.other.radar",
    "sensor.other.gnss", "sensor.other.imu", "sensor.other.collision",
    "sensor.other.lane_invasion", "sensor.other.obstacle",
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=2000)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    host = subprocess.check_output("ip route show | awk '/default/{print $3}'", shell=True).decode().strip()

    import carla
    rep = {"host": host, "port": args.port, "blueprints": {}, "api": {}}
    client = carla.Client(host, args.port); client.set_timeout(30.0)
    world = client.get_world()
    lib = world.get_blueprint_library()

    for s in SENSORS:
        try:
            bp = lib.find(s)
            rep["blueprints"][s] = "ok" if bp else "missing"
        except Exception:
            rep["blueprints"][s] = "missing"

    # 天气接口
    try:
        w = world.get_weather()
        world.set_weather(w)
        rep["api"]["weather_get_set"] = "ok"
    except Exception as e:
        rep["api"]["weather_get_set"] = f"fail: {e}"
    # 交通灯
    try:
        actors = world.get_actors()
        tls = actors.filter("traffic.traffic_light*")
        rep["api"]["traffic_lights_found"] = len(tls)
    except Exception as e:
        rep["api"]["traffic_lights_found"] = f"fail: {e}"
    # TM
    try:
        tm = client.get_trafficmanager()
        rep["api"]["trafficmanager"] = "ok"
    except Exception as e:
        rep["api"]["trafficmanager"] = f"fail: {e}"
    # 同步模式
    try:
        st = world.get_settings()
        st.synchronous_mode = True; st.fixed_delta_seconds = 0.05
        world.apply_settings(st)
        world.tick()
        rep["api"]["sync_mode"] = "ok"
        st.synchronous_mode = False; world.apply_settings(st)
    except Exception as e:
        rep["api"]["sync_mode"] = f"fail: {e}"
    # 地图/spawn 点
    try:
        rep["api"]["map"] = world.get_map().name
        rep["api"]["spawn_points"] = len(world.get_map().get_spawn_points())
    except Exception as e:
        rep["api"]["map"] = f"fail: {e}"
    # spectator/截图调试口
    try:
        rep["api"]["spectator"] = "ok" if world.get_spectator() else "missing"
    except Exception as e:
        rep["api"]["spectator"] = f"fail: {e}"

    with open(args.out, "w") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(json.dumps(rep, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
