#!/usr/bin/env python3
"""test_scoring_core.py — scoring_core 单元测试（T2.2/T2.6）。

注入式验证各违章分项触发正确;trivial 路线 DS=100。
"""
import sys
sys.path.insert(0, "/home/xsl/MySim/tools/ue5harness")
import scoring_core


def make_tick(tick, sim_time, speed=5.0, completion=0.0, collision=None, tl_state=None, is_junction=False, road_id=1):
    return {
        "tick": tick,
        "timestamp": 1234567890.0 + sim_time,
        "sim_time": sim_time,
        "ego_location": (0.0, 0.0, 0.0),
        "ego_velocity": (speed, 0.0, 0.0),
        "ego_speed": speed,
        "ego_acceleration": (0.0, 0.0, 0.0),
        "collision_impulse": collision,
        "collision_actor": "vehicle.tesla.model3" if collision else None,
        "traffic_light_state": tl_state,
        "traffic_light_id": 1 if tl_state else None,
        "lane_id": 1,
        "road_id": road_id,
        "is_junction": is_junction,
        "route_completion": completion,
        "control": {"throttle": 0.5, "brake": 0.0, "steer": 0.0},
    }


def test_trivial():
    """无违章路线 DS=100。"""
    ticks = [make_tick(i, i * 0.05, completion=i * 100.0 / 100) for i in range(101)]
    score = scoring_core.compute_route_score(0, ticks, 100.0)
    assert score.score_route == 100.0, f"score_route={score.score_route}"
    assert score.score_penalty == 1.0, f"score_penalty={score.score_penalty}"
    assert score.score_composed == 100.0, f"score_composed={score.score_composed}"
    assert score.status == "Perfect", f"status={score.status}"
    print("PASS test_trivial")


def test_collision():
    """碰撞 penalty=0.6(车辆)。"""
    ticks = [make_tick(i, i * 0.05, completion=i * 100.0 / 100) for i in range(101)]
    ticks[50]["collision_impulse"] = 100.0
    ticks[50]["collision_actor"] = "vehicle.tesla.model3"
    score = scoring_core.compute_route_score(0, ticks, 100.0)
    assert score.score_penalty == 0.6, f"score_penalty={score.score_penalty}"
    assert score.score_composed == 60.0, f"score_composed={score.score_composed}"
    assert len(score.infractions["collisions_vehicle"]) == 1
    print("PASS test_collision")


def test_red_light():
    """闯红灯 penalty=0.7。"""
    ticks = [make_tick(i, i * 0.05, completion=i * 100.0 / 100) for i in range(101)]
    # 红灯时在路口内持续移动
    for i in range(50, 60):
        ticks[i]["traffic_light_state"] = "Red"
        ticks[i]["is_junction"] = True
        ticks[i]["ego_speed"] = 5.0
    score = scoring_core.compute_route_score(0, ticks, 100.0)
    assert score.score_penalty == 0.7, f"score_penalty={score.score_penalty}"
    assert score.score_composed == 70.0, f"score_composed={score.score_composed}"
    assert len(score.infractions["red_light"]) == 1
    print("PASS test_red_light")


def test_timeout():
    """超时 penalty=0.7。"""
    ticks = [make_tick(i, i * 0.05, completion=50.0) for i in range(101)]
    score = scoring_core.compute_route_score(0, ticks, 100.0, timeout=True)
    assert score.score_penalty == 0.7, f"score_penalty={score.score_penalty}"
    assert score.score_composed == 35.0, f"score_composed={score.score_composed}"
    assert len(score.infractions["route_timeout"]) == 1
    assert "Failed" in score.status
    print("PASS test_timeout")


def test_blocked():
    """堵路检测(不直接惩罚)。"""
    ticks = []
    for i in range(101):
        t = make_tick(i, i * 0.5, speed=0.0, completion=50.0)
        ticks.append(t)
    score = scoring_core.compute_route_score(0, ticks, 100.0)
    assert len(score.infractions["vehicle_blocked"]) >= 1
    print("PASS test_blocked")


def test_global():
    """全局汇总。"""
    s1 = scoring_core.RouteScore(0, 100.0, 1.0, 100.0, "Perfect", 0, {})
    s2 = scoring_core.RouteScore(1, 80.0, 0.6, 48.0, "Completed", 1, {})
    g = scoring_core.compute_global_scores([s1, s2])
    assert g["score_composed"] == 74.0, f"score_composed={g['score_composed']}"
    assert g["success_rate"] == 100.0
    print("PASS test_global")


if __name__ == "__main__":
    test_trivial()
    test_collision()
    test_red_light()
    test_timeout()
    test_blocked()
    test_global()
    print("全部单元测试通过")
