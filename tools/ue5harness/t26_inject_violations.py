#!/usr/bin/env python3
"""t26_inject_violations.py — T2.6 违章注入测试（UE4 侧）。

在 route_executor 运行中强制制造碰撞/闯红灯/超时,验证 scoring_core 判定正确性。
用法:
  PYTHONPATH=/home/xsl/MySim/tools conda run -n mysim-simlingo python tools/ue5harness/t26_inject_violations.py \
    --routes data/routes/ue4_aligned_routes_subset6.xml --out logs/t26-inject
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, "/home/xsl/MySim/tools")
sys.path.insert(0, "/home/xsl/MySim/tools/ue5harness")
from route_executor import RouteExecutor, parse_routes_xml, TickRecord
import scoring_core


def run_with_injection(args, route_config, inject_type):
    """运行路线并注入违章。基于 TM autopilot,在特定时刻覆盖控制。

    inject_type: collision / red_light / timeout / none
    """
    executor = RouteExecutor(args)
    try:
        executor.connect()
        executor.setup_route(route_config)

        import carla
        executor.start_time = time.time()
        executor.start_sim_time = executor.world.get_snapshot().timestamp.elapsed_seconds
        executor.tick_count = 0
        executor.tick_records = []
        executor.traveled_distance = 0.0
        executor.last_location = None

        # 使用 TM autopilot 作为基础
        executor.ego.set_autopilot(True, args.tm_port)
        executor.tm.ignore_lights_percentage(executor.ego, 0.0)
        executor.tm.ignore_signs_percentage(executor.ego, 0.0)

        result = {
            "route_id": route_config.route_id,
            "status": "Started",
            "route_length": executor.route_length,
        }

        print(f"[inject] 路线 {route_config.route_id} 注入类型={inject_type}", flush=True)

        injection_done = False
        red_light_injected = False
        while True:
            executor.world.tick()
            executor.tick_count += 1
            snapshot = executor.world.get_snapshot()
            sim_time = snapshot.timestamp.elapsed_seconds - executor.start_sim_time

            if not executor.ego or not executor.ego.is_alive:
                result["status"] = "Crashed"
                break

            velocity = executor.ego.get_velocity()
            speed = (velocity.x**2 + velocity.y**2 + velocity.z**2) ** 0.5
            acceleration = executor.ego.get_acceleration()
            control = executor.ego.get_control()

            tl_state, tl_id = executor._get_traffic_light_state()
            waypoint = executor.tmap.get_waypoint(executor.ego.get_location())

            record = TickRecord(
                tick=executor.tick_count,
                timestamp=time.time(),
                sim_time=sim_time,
                ego_location=(executor.ego.get_location().x, executor.ego.get_location().y, executor.ego.get_location().z),
                ego_velocity=(velocity.x, velocity.y, velocity.z),
                ego_speed=speed,
                ego_acceleration=(acceleration.x, acceleration.y, acceleration.z),
                collision_impulse=executor.latest_collision["impulse"] if executor.latest_collision else None,
                collision_actor=executor.latest_collision["actor"] if executor.latest_collision else None,
                traffic_light_state=tl_state,
                traffic_light_id=tl_id,
                lane_id=waypoint.lane_id if waypoint else None,
                road_id=waypoint.road_id if waypoint else None,
                is_junction=waypoint.is_junction if waypoint else False,
                route_completion=executor._get_route_progress(),
                control={"throttle": control.throttle, "brake": control.brake, "steer": control.steer},
            )
            executor.tick_records.append(record)

            # 注入违章(覆盖 autopilot 控制)
            if inject_type == "collision" and not injection_done and executor.tick_count == 30:
                # 关闭 autopilot,强制撞墙
                executor.ego.set_autopilot(False, args.tm_port)
                control = carla.VehicleControl(throttle=1.0, steer=-1.0, brake=0.0)
                executor.ego.apply_control(control)
                injection_done = True
                print(f"[inject] tick {executor.tick_count}: 注入碰撞(强制右转撞墙)", flush=True)
            elif inject_type == "red_light" and not red_light_injected and tl_state == "Red" and speed > 2.0 and waypoint.is_junction:
                # 红灯时在路口内继续加速
                executor.ego.set_autopilot(False, args.tm_port)
                control = carla.VehicleControl(throttle=1.0, brake=0.0, steer=0.0)
                executor.ego.apply_control(control)
                red_light_injected = True
                print(f"[inject] tick {executor.tick_count}: 注入闯红灯(speed={speed:.2f})", flush=True)
            elif inject_type == "timeout" and executor.tick_count == 50:
                # 关闭 autopilot,停车不动
                executor.ego.set_autopilot(False, args.tm_port)
                control = carla.VehicleControl(throttle=0.0, brake=1.0, steer=0.0)
                executor.ego.apply_control(control)
                print(f"[inject] tick {executor.tick_count}: 注入超时(停车)", flush=True)

            executor.latest_collision = None
            executor.latest_lane_invasion = None

            # 终止条件
            if record.route_completion >= 99.0:
                record.route_completion = 100.0
                executor.tick_records[-1] = record
                result["status"] = "Completed"
                break
            if sim_time > 120.0:
                result["status"] = "Failed - Route timeout"
                break

        result["duration_game"] = sim_time
        result["ticks"] = [vars(t) for t in executor.tick_records]

        # 用 scoring_core 评分
        timeout = "timeout" in result["status"].lower()
        score = scoring_core.compute_route_score(
            route_id=route_config.route_id,
            ticks=executor.tick_records,
            route_length=executor.route_length,
            timeout=timeout,
        )
        result["score"] = vars(score)

        print(f"[inject] 路线 {route_config.route_id} 结果: {result['status']} "
              f"DS={score.score_composed:.2f} penalty={score.score_penalty:.3f}", flush=True)
        print(f"[inject] 违章: {[(k, len(v)) for k, v in score.infractions.items() if len(v) > 0]}", flush=True)

        return result

    finally:
        executor.cleanup()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=2031)
    ap.add_argument("--tm-port", type=int, default=8010)
    ap.add_argument("--dt", type=float, default=0.05)
    ap.add_argument("--vehicle", default="vehicle.audi.tt")
    ap.add_argument("--use-socket-agent", action="store_true")
    ap.add_argument("--agent-port", type=int, default=5555)
    args = ap.parse_args()

    routes = parse_routes_xml(args.routes)
    os.makedirs(args.out, exist_ok=True)

    tests = [
        (routes[0], "none"),
        (routes[1], "collision"),
        (routes[2], "red_light"),
        (routes[3], "timeout"),
    ]

    results = []
    for route_config, inject_type in tests:
        result = run_with_injection(args, route_config, inject_type)
        results.append(result)
        time.sleep(2)

    with open(os.path.join(args.out, "inject_results.json"), "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"[inject] 全部测试完成,结果保存 {args.out}/inject_results.json", flush=True)


if __name__ == "__main__":
    main()
