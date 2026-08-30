#!/usr/bin/env python3
"""scoring_core.py — DS/SR 核心判定纯函数模块（T2.2）。

输入为 tick 原始记录列表（不依赖任何 CARLA API）,输出 route-level DS/SR 与各违章分项。
系数集与 Bench2Drive `leaderboard/utils/statistics_manager.py` 完全一致,为跨侧唯一事实源。

tick 记录字段清单（R4-N4）:
- collision_impulse: 碰撞冲量（None 表示无碰撞）
- collision_actor: 碰撞对象类型
- traffic_light_state: 交通灯原始状态（Red/Yellow/Green/Off/Unknown）
- lane_id / road_id: 车道几何
- ego_speed: 车速 m/s
- timestamp / sim_time: tick 时间戳
- route_completion: 路线完成度 0-100
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional


# ========== 系数集（唯一事实源,与 Bench2Drive 一致）==========

PENALTY_VALUE_DICT = {
    "collision_pedestrian": 0.5,
    "collision_vehicle": 0.6,
    "collision_static": 0.65,
    "red_light": 0.7,
    "stop_infraction": 0.8,
    "scenario_timeout": 0.7,
    "yield_emergency": 0.7,
}

PENALTY_PERC_DICT = {
    "outside_route_lanes": [0.0, "increases"],
    "min_speed": [0.7, "unused"],  # Bench2Drive 0.9.15 版标记 unused
}

INFRACTION_NAMES = [
    "collisions_layout",
    "collisions_pedestrian",
    "collisions_vehicle",
    "red_light",
    "stop_infraction",
    "outside_route_lanes",
    "min_speed_infractions",
    "yield_emergency_vehicle_infractions",
    "scenario_timeouts",
    "route_dev",
    "vehicle_blocked",
    "route_timeout",
]


@dataclass
class InfractionEvent:
    """单个违章事件。"""
    type: str
    tick: int
    sim_time: float
    detail: str = ""


@dataclass
class RouteScore:
    """路线评分结果。"""
    route_id: int
    score_route: float  # 0-100
    score_penalty: float  # 0-1
    score_composed: float  # 0-100
    status: str  # Completed / Failed - xxx
    num_infractions: int
    infractions: dict = field(default_factory=dict)  # name -> list of InfractionEvent
    route_length: float = 0.0
    duration_game: float = 0.0


def _classify_collision(actor_type: Optional[str]) -> str:
    """根据碰撞对象类型分类。"""
    if actor_type is None:
        return "collision_static"
    actor_type = actor_type.lower()
    if "pedestrian" in actor_type or "walker" in actor_type:
        return "collision_pedestrian"
    if "vehicle" in actor_type:
        return "collision_vehicle"
    return "collision_static"


def _detect_red_light_violation(ticks: List[dict], min_speed_threshold=1.0, min_ticks=3):
    """检测闯红灯:交通灯为 Red 且车辆持续移动。

    简化判定:某 tick 交通灯为 Red 且 speed > min_speed_threshold,之后 min_ticks 内仍移动则记一次闯红灯。
    同一红灯周期只记一次。要求车辆在路口内(is_junction),减少减速通过时的误报。
    """
    violations = []
    i = 0
    n = len(ticks)
    while i < n:
        t = ticks[i]
        if (t.get("traffic_light_state") == "Red"
                and t.get("ego_speed", 0.0) > min_speed_threshold
                and t.get("is_junction", False)):
            # 检查后续 min_ticks 是否持续移动
            sustained = True
            for j in range(i + 1, min(i + 1 + min_ticks, n)):
                if ticks[j].get("ego_speed", 0.0) <= min_speed_threshold:
                    sustained = False
                    break
            if sustained:
                violations.append(InfractionEvent(
                    type="red_light",
                    tick=t["tick"],
                    sim_time=t["sim_time"],
                    detail=f"Red light at speed {t['ego_speed']:.2f} m/s in junction",
                ))
                # 跳过当前红灯周期(等待状态变化)
                j = i + 1
                while j < n and ticks[j].get("traffic_light_state") == "Red":
                    j += 1
                i = j
                continue
        i += 1
    return violations


def _detect_blocked(ticks: List[dict], speed_threshold=0.05, min_duration=30.0):
    """检测堵路:速度低于阈值持续 min_duration 秒。

    提高阈值并延长时长,避免 TM autopilot 等红灯/让行时误报。
    仅在路线未完成时判定为堵路违章。
    """
    violations = []
    i = 0
    n = len(ticks)
    while i < n:
        t = ticks[i]
        if t.get("ego_speed", 0.0) < speed_threshold and t.get("route_completion", 0.0) < 99.0:
            start = i
            start_time = t["sim_time"]
            while i < n and ticks[i].get("ego_speed", 0.0) < speed_threshold:
                i += 1
            duration = ticks[i - 1]["sim_time"] - start_time if i > start else 0.0
            if duration >= min_duration:
                violations.append(InfractionEvent(
                    type="vehicle_blocked",
                    tick=ticks[start]["tick"],
                    sim_time=start_time,
                    detail=f"Blocked for {duration:.1f}s at {ticks[start].get('route_completion', 0):.1f}%",
                ))
        else:
            i += 1
    return violations


def _detect_route_deviation(ticks: List[dict], route_road_ids: set, min_ticks=5):
    """检测路线偏离:连续 min_ticks 不在路线 road_id 上。"""
    violations = []
    i = 0
    n = len(ticks)
    while i < n:
        t = ticks[i]
        if t.get("road_id") not in route_road_ids:
            start = i
            while i < n and ticks[i].get("road_id") not in route_road_ids:
                i += 1
            if i - start >= min_ticks:
                violations.append(InfractionEvent(
                    type="route_dev",
                    tick=ticks[start]["tick"],
                    sim_time=ticks[start]["sim_time"],
                    detail=f"Deviated for {i - start} ticks",
                ))
        else:
            i += 1
    return violations


def compute_route_score(route_id: int, ticks: List[dict], route_length: float,
                        route_road_ids: Optional[set] = None,
                        timeout: bool = False) -> RouteScore:
    """计算单条路线的 DS/SR。

    参数:
        route_id: 路线 ID
        ticks: tick 原始记录列表（dict 或 TickRecord）
        route_length: 路线长度（米）
        route_road_ids: 路线经过的 road_id 集合（用于偏离检测;None 则跳过）
        timeout: 是否发生路线超时（外部传入）
    """
    # 归一化 ticks 为 dict
    norm_ticks = []
    for t in ticks:
        if hasattr(t, "__dict__"):
            norm_ticks.append(vars(t))
        else:
            norm_ticks.append(t)

    infractions = {name: [] for name in INFRACTION_NAMES}
    score_penalty = 1.0

    # 碰撞检测
    for t in norm_ticks:
        if t.get("collision_impulse") is not None:
            ctype = _classify_collision(t.get("collision_actor"))
            name = {
                "collision_pedestrian": "collisions_pedestrian",
                "collision_vehicle": "collisions_vehicle",
                "collision_static": "collisions_layout",
            }[ctype]
            infractions[name].append(InfractionEvent(
                type=ctype,
                tick=t["tick"],
                sim_time=t["sim_time"],
                detail=f"Impulse {t['collision_impulse']:.2f} with {t.get('collision_actor')}",
            ))
            score_penalty *= PENALTY_VALUE_DICT[ctype]

    # 闯红灯
    for v in _detect_red_light_violation(norm_ticks):
        infractions["red_light"].append(v)
        score_penalty *= PENALTY_VALUE_DICT["red_light"]

    # 堵路
    for v in _detect_blocked(norm_ticks):
        infractions["vehicle_blocked"].append(v)
        # Bench2Drive 中 vehicle_blocked 不直接惩罚,但会终止路线
        # 这里标记事件,惩罚由 timeout/deviation 逻辑处理

    # 路线偏离
    if route_road_ids:
        for v in _detect_route_deviation(norm_ticks, route_road_ids):
            infractions["route_dev"].append(v)
            # Bench2Drive 中 route_dev 不直接惩罚,但会终止路线

    # 超时
    if timeout:
        infractions["route_timeout"].append(InfractionEvent(
            type="route_timeout",
            tick=norm_ticks[-1]["tick"] if norm_ticks else 0,
            sim_time=norm_ticks[-1]["sim_time"] if norm_ticks else 0.0,
            detail="Route timeout",
        ))
        score_penalty *= PENALTY_VALUE_DICT["scenario_timeout"]

    # 路线完成度
    score_route = norm_ticks[-1].get("route_completion", 0.0) if norm_ticks else 0.0
    score_composed = max(score_route * score_penalty, 0.0)

    # 状态判定
    target_reached = score_route >= 99.0
    if target_reached:
        status = "Completed" if any(len(v) > 0 for v in infractions.values()) else "Perfect"
    else:
        status = "Failed"
        if timeout:
            status += " - Agent timed out"
        elif infractions["vehicle_blocked"]:
            status += " - Agent got blocked"
        elif infractions["route_dev"]:
            status += " - Agent deviated from the route"

    return RouteScore(
        route_id=route_id,
        score_route=round(score_route, 6),
        score_penalty=round(score_penalty, 6),
        score_composed=round(score_composed, 6),
        status=status,
        num_infractions=sum(len(v) for v in infractions.values()),
        infractions=infractions,
        route_length=route_length,
        duration_game=norm_ticks[-1]["sim_time"] if norm_ticks else 0.0,
    )


def compute_global_scores(route_scores: List[RouteScore]) -> dict:
    """计算全局 DS/SR 汇总。"""
    n = len(route_scores)
    if n == 0:
        return {"score_composed": 0.0, "score_route": 0.0, "score_penalty": 0.0,
                "num_routes": 0, "status": "No routes"}

    mean_composed = sum(r.score_composed for r in route_scores) / n
    mean_route = sum(r.score_route for r in route_scores) / n
    mean_penalty = sum(r.score_penalty for r in route_scores) / n

    # SR: 完全完成（Completed 或 Perfect）的比例
    completed = sum(1 for r in route_scores if r.status in ("Completed", "Perfect"))
    sr = completed / n * 100.0

    # 标准差
    if n > 1:
        std_composed = math.sqrt(sum((r.score_composed - mean_composed) ** 2 for r in route_scores) / (n - 1))
    else:
        std_composed = 0.0

    global_status = "Perfect"
    for r in route_scores:
        if "Failed" in r.status:
            global_status = "Failed"
            break
        elif r.status == "Completed" and global_status == "Perfect":
            global_status = "Completed"

    return {
        "score_composed": round(mean_composed, 6),
        "score_route": round(mean_route, 6),
        "score_penalty": round(mean_penalty, 6),
        "score_composed_std": round(std_composed, 3),
        "success_rate": round(sr, 2),
        "num_routes": n,
        "num_completed": completed,
        "status": global_status,
    }
