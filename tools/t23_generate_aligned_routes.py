#!/usr/bin/env python3
"""t23_generate_aligned_routes.py — 生成 UE4/UE5 语义对齐路线集（T2.3）。

策略:
- 在指定地图（Town10HD_Opt 或 Town10HD）上,用 spawn 点 + GlobalRoutePlanner 生成候选路线。
- 筛选长度 100–200m 的路线,按主导 RoadOption 分类(straight/left/right/lane_change)。
- 选取 20 条覆盖各类型;对每侧地图独立生成,语义对齐表按 route_type + 起点 spawn index 映射。

用法:
  PYTHONPATH=/home/xsl/MySim/tools conda run -n mysim-ue5 python tools/t23_generate_aligned_routes.py --side ue5 --out data/routes/ue5_aligned_routes.xml
"""
import argparse
import json
import math
import random
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

sys.path.insert(0, "/home/xsl/MySim/tools")
import server_watchdog as w


def host_ip():
    return w.host_ip()


def get_route_type(road_options):
    """根据 RoadOption 序列判断路线类型。"""
    cnt = Counter(road_options)
    if cnt.get("CHANGELANELEFT", 0) > 0 or cnt.get("CHANGELANERIGHT", 0) > 0:
        return "lane_change"
    if cnt.get("LEFT", 0) > cnt.get("RIGHT", 0):
        return "left"
    if cnt.get("RIGHT", 0) > cnt.get("LEFT", 0):
        return "right"
    if cnt.get("STRAIGHT", 0) > 0:
        return "straight"
    return "lanefollow"


def generate_candidates(world, grp, spawn_points, min_dist=100.0, max_dist=200.0, n_candidates=500):
    """生成候选路线。"""
    candidates = []
    n_spawn = len(spawn_points)
    random.seed(42)

    for _ in range(n_candidates):
        i = random.randint(0, n_spawn - 1)
        j = random.randint(0, n_spawn - 1)
        if i == j:
            continue
        start = spawn_points[i].location
        end = spawn_points[j].location
        try:
            route = grp.trace_route(start, end)
        except Exception:
            continue
        if len(route) < 2:
            continue
        dist = sum(
            route[k][0].transform.location.distance(route[k + 1][0].transform.location)
            for k in range(len(route) - 1)
        )
        if not (min_dist <= dist <= max_dist):
            continue
        road_options = [r[1].name for r in route]
        rtype = get_route_type(road_options)
        # 保存完整路线 waypoints(而非稀疏 keypoints),避免执行器重新规划时路径漂移
        full_waypoints = [r[0].transform.location for r in route]
        candidates.append({
            "start_spawn_idx": i,
            "end_spawn_idx": j,
            "distance": dist,
            "route_type": rtype,
            "keypoints": full_waypoints,
            "road_options": road_options,
        })
    return candidates


def generate_junction_candidates(world, grp, spawn_points, min_dist=100.0, max_dist=200.0):
    """利用路口生成转弯路线。"""
    candidates = []
    tmap = world.get_map()
    topology = tmap.get_topology()

    # 收集路口 waypoint
    junction_wps = []
    for wp_pair in topology:
        wp = wp_pair[0]
        if wp.is_junction:
            junction_wps.append(wp)

    print(f"[t23] junction waypoints={len(junction_wps)}")

    # 对每个 spawn 点,尝试规划经过路口的路线
    for i, sp in enumerate(spawn_points[:50]):  # 限制计算量
        start_loc = sp.location
        # 找最近的路口
        nearest_junction = None
        min_d = float("inf")
        for jwp in junction_wps:
            d = start_loc.distance(jwp.transform.location)
            if d < min_d:
                min_d = d
                nearest_junction = jwp
        if nearest_junction is None or min_d > 80.0:
            continue

        # 从路口出发,找 50-150m 外的终点
        junction_loc = nearest_junction.transform.location
        for j, sp2 in enumerate(spawn_points):
            if i == j:
                continue
            end_loc = sp2.location
            if junction_loc.distance(end_loc) < 30.0:
                continue
            try:
                route = grp.trace_route(start_loc, end_loc)
            except Exception:
                continue
            if len(route) < 2:
                continue
            dist = sum(
                route[k][0].transform.location.distance(route[k + 1][0].transform.location)
                for k in range(len(route) - 1)
            )
            if not (min_dist <= dist <= max_dist):
                continue
            # 检查是否经过路口
            passes_junction = any(
                r[0].transform.location.distance(junction_loc) < 10.0 for r in route
            )
            if not passes_junction:
                continue
            road_options = [r[1].name for r in route]
            rtype = get_route_type(road_options)
            if rtype == "lanefollow":
                continue
            # 保存完整路线 waypoints
            full_waypoints = [r[0].transform.location for r in route]
            candidates.append({
                "start_spawn_idx": i,
                "end_spawn_idx": j,
                "distance": dist,
                "route_type": rtype,
                "keypoints": full_waypoints,
                "road_options": road_options,
            })
    return candidates


def select_routes(candidates, n=20):
    """按类型覆盖选取 n 条路线。"""
    by_type = defaultdict(list)
    for c in candidates:
        by_type[c["route_type"]].append(c)

    target = {"straight": 4, "left": 5, "right": 5, "lane_change": 3, "lanefollow": 3}
    selected = []
    used_spawn_pairs = set()

    for rtype, count in target.items():
        pool = by_type.get(rtype, [])
        pool.sort(key=lambda x: x["distance"])
        take = pool[:count * 2]  # 多取一些备选
        for c in take:
            key = (c["start_spawn_idx"], c["end_spawn_idx"])
            if key in used_spawn_pairs:
                continue
            selected.append(c)
            used_spawn_pairs.add(key)
            if len(selected) >= n:
                break
        if len(selected) >= n:
            break

    if len(selected) < n:
        remaining = [c for c in candidates if (c["start_spawn_idx"], c["end_spawn_idx"]) not in used_spawn_pairs]
        remaining.sort(key=lambda x: x["distance"])
        for c in remaining:
            selected.append(c)
            used_spawn_pairs.add((c["start_spawn_idx"], c["end_spawn_idx"]))
            if len(selected) >= n:
                break

    return selected[:n]


def write_xml(routes, town, out_path):
    """写入 Bench2Drive 兼容 XML。"""
    root = ET.Element("routes")
    for idx, r in enumerate(routes):
        route_elem = ET.SubElement(root, "route", id=str(10000 + idx), road_id=str(r["start_spawn_idx"]), town=town)
        waypoints = ET.SubElement(route_elem, "waypoints")
        for kp in r["keypoints"]:
            ET.SubElement(waypoints, "position", x=str(round(kp.x, 1)), y=str(round(kp.y, 1)), z=str(round(kp.z, 1)))
        ET.SubElement(route_elem, "scenarios")
        weathers = ET.SubElement(route_elem, "weathers")
        ET.SubElement(weathers, "weather",
                      cloudiness="5.0", fog_density="10.0", precipitation="0.0",
                      precipitation_deposits="0.0", route_percentage="0",
                      sun_altitude_angle="45.0", sun_azimuth_angle="-1.0",
                      wetness="0.0", wind_intensity="10.0")
        ET.SubElement(weathers, "weather",
                      cloudiness="5.0", fog_density="10.0", precipitation="0.0",
                      precipitation_deposits="0.0", route_percentage="100",
                      sun_altitude_angle="45.0", sun_azimuth_angle="-1.0",
                      wetness="0.0", wind_intensity="10.0")

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    print(f"[t23] 写入 {out_path}: {len(routes)} 条路线, town={town}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", choices=["ue4", "ue5"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mapping-out", default=None)
    args = ap.parse_args()

    side = args.side
    port = w.SIDES[side]["port"]
    town = "Town10HD_Opt" if side == "ue5" else "Town10HD"

    import carla
    client = carla.Client(host_ip(), port)
    client.set_timeout(30.0)
    world = client.get_world()
    tmap = world.get_map()
    current_town = tmap.name.split("/")[-1]
    print(f"[t23] side={side} port={port} current_map={current_town}")

    if current_town != town:
        print(f"[t23] 切换地图 {current_town} → {town}")
        world = client.load_world(town)
        tmap = world.get_map()

    spawn_points = tmap.get_spawn_points()
    print(f"[t23] spawn_points={len(spawn_points)}")

    from agents.navigation.global_route_planner import GlobalRoutePlanner
    grp = GlobalRoutePlanner(tmap, 2.0)

    candidates = generate_candidates(world, grp, spawn_points, n_candidates=1000)
    print(f"[t23] 随机候选 {len(candidates)} 条")
    type_cnt = Counter(c["route_type"] for c in candidates)
    print(f"[t23] 随机类型分布: {dict(type_cnt)}")

    junction_candidates = generate_junction_candidates(world, grp, spawn_points)
    print(f"[t23] 路口候选 {len(junction_candidates)} 条")
    jtype_cnt = Counter(c["route_type"] for c in junction_candidates)
    print(f"[t23] 路口类型分布: {dict(jtype_cnt)}")

    all_candidates = candidates + junction_candidates
    selected = select_routes(all_candidates, n=20)
    print(f"[t23] 选取 {len(selected)} 条")
    sel_cnt = Counter(r["route_type"] for r in selected)
    print(f"[t23] 选取类型分布: {dict(sel_cnt)}")

    write_xml(selected, town, args.out)

    meta = [{
        "route_id": 10000 + i,
        "start_spawn_idx": r["start_spawn_idx"],
        "end_spawn_idx": r["end_spawn_idx"],
        "distance": round(r["distance"], 2),
        "route_type": r["route_type"],
        "start_xy": [round(r["keypoints"][0].x, 2), round(r["keypoints"][0].y, 2)],
        "end_xy": [round(r["keypoints"][-1].x, 2), round(r["keypoints"][-1].y, 2)],
    } for i, r in enumerate(selected)]

    meta_path = args.out.replace(".xml", "_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"[t23] 元数据 {meta_path}")


if __name__ == "__main__":
    main()
