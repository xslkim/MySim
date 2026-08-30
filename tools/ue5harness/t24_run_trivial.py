#!/usr/bin/env python3
"""t24_run_trivial.py — UE5 trivial agent 全程无人值守运行（T2.4）。

运行 20 路线 × 3 seeds = 60 route-runs,内置崩溃自动重启与断点续跑。
用法:
  PYTHONPATH=/home/xsl/MySim/tools conda run -n mysim-ue5 python tools/ue5harness/t24_run_trivial.py \
    --routes data/routes/ue5_aligned_routes.xml --out logs/t24-trivial --max-restarts 3
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, "/home/xsl/MySim/tools")
sys.path.insert(0, "/home/xsl/MySim/tools/ue5harness")
import server_watchdog as w
from route_executor import RouteExecutor, parse_routes_xml, save_result
import scoring


def ensure_server():
    """确保 UE5 server 就绪。直接调用 watchdog,避免 subprocess segfault。"""
    try:
        port = w.SIDES["ue5"]["port"]
        if w.server_alive(port):
            used = w.gpu_used_mb()
            if used >= 5000:
                print(f"[ensure] ue5 就绪(port={port}, 5090 显存 {used} MiB)", flush=True)
                return True
            print(f"[ensure] ue5 RPC 通但 5090 显存仅 {used} MiB,判错卡,重启", flush=True)
        else:
            print(f"[ensure] ue5 失联,清理 + adapter 轮询重启", flush=True)
        return w.restart("ue5")
    except Exception as e:
        print(f"[ensure] ue5 保障异常: {e}", flush=True)
        return False


def run_single_route(args, route_config, seed, attempt=0):
    """运行单条路线,返回是否成功。"""
    executor = RouteExecutor(args)
    try:
        executor.connect()
        # 清理可能残留的 hero 车辆(上次运行异常退出时残留)
        for actor in executor.world.get_actors().filter('vehicle.*'):
            if actor.attributes.get('role_name') == 'hero':
                print(f"[t24] 清理残留 hero 车辆 id={actor.id}", flush=True)
                actor.destroy()
        # TODO: seed 用于背景交通 spawn(当前 trivial 验证基建无背景交通,种子仅记录)
        result = executor.run_route(route_config, max_game_time=args.max_game_time)
        out_dir = os.path.join(args.out, f"seed_{seed}")
        save_result(result, out_dir)
        return True
    except Exception as e:
        print(f"[t24] route {route_config.route_id} seed {seed} 异常: {e}", flush=True)
        return False
    finally:
        executor.cleanup()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=2021)
    ap.add_argument("--tm-port", type=int, default=8000)
    ap.add_argument("--dt", type=float, default=0.05)
    ap.add_argument("--vehicle", default="vehicle.lincoln.mkz")
    ap.add_argument("--max-game-time", type=float, default=200.0)
    ap.add_argument("--max-restarts", type=int, default=3)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--use-socket-agent", action="store_true", help="使用 socket agent 而非 TM autopilot")
    ap.add_argument("--agent-port", type=int, default=5555, help="agent socket 端口")
    args = ap.parse_args()

    routes = parse_routes_xml(args.routes)
    print(f"[t24] 共 {len(routes)} 条路线 × {len(args.seeds)} seeds = {len(routes) * len(args.seeds)} route-runs", flush=True)

    # 断点续跑:检查已有结果
    done = set()
    for seed in args.seeds:
        seed_dir = os.path.join(args.out, f"seed_{seed}")
        if os.path.exists(seed_dir):
            for f in os.listdir(seed_dir):
                if f.startswith("route_") and f.endswith("_result.json"):
                    rid = int(f.replace("route_", "").replace("_result.json", ""))
                    done.add((rid, seed))
    print(f"[t24] 已完成 {len(done)} 条,跳过", flush=True)

    total = len(routes) * len(args.seeds)
    completed = len(done)
    failed_routes = []

    for route_config in routes:
        for seed in args.seeds:
            if (route_config.route_id, seed) in done:
                continue
            print(f"[t24] 进度 {completed + 1}/{total}: route {route_config.route_id} seed {seed}", flush=True)

            success = False
            for attempt in range(args.max_restarts):
                if not ensure_server():
                    print("[t24] server 无法启动,BLOCKED", flush=True)
                    sys.exit(2)
                success = run_single_route(args, route_config, seed, attempt)
                if success:
                    break
                print(f"[t24] route {route_config.route_id} seed {seed} 第 {attempt + 1} 次失败,重试", flush=True)
                time.sleep(10)

            if not success:
                failed_routes.append((route_config.route_id, seed))
                print(f"[t24] route {route_config.route_id} seed {seed} 连续 {args.max_restarts} 次失败,标记", flush=True)

            completed += 1
            # 每 10 条写一次进度
            if completed % 10 == 0:
                with open(os.path.join(args.out, "progress.json"), "w") as f:
                    json.dump({"completed": completed, "total": total, "failed": failed_routes}, f)

    # 汇总评分
    print("[t24] 全部路线完成,汇总评分", flush=True)
    all_scores = []
    for seed in args.seeds:
        seed_dir = os.path.join(args.out, f"seed_{seed}")
        if os.path.exists(seed_dir):
            scores = scoring.score_directory(seed_dir)
            scores["seed"] = seed
            all_scores.append(scores)

    summary = {
        "total_route_runs": total,
        "completed": completed,
        "failed_routes": failed_routes,
        "per_seed": all_scores,
        "overall": {
            "score_composed": sum(s["score_composed"] for s in all_scores) / len(all_scores),
            "success_rate": sum(s["success_rate"] for s in all_scores) / len(all_scores),
        }
    }
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[t24] 汇总: DS={summary['overall']['score_composed']:.2f} SR={summary['overall']['success_rate']:.1f}%", flush=True)
    print(f"[t24] 失败路线: {failed_routes}", flush=True)


if __name__ == "__main__":
    main()
