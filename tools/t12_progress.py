#!/usr/bin/env python3
"""t12_progress.py — T1.2 评测进度统计 + 220 全量墙钟外推。

用法: python3 tools/t12_progress.py <out_dir> [routes_xml]
  out_dir    如 logs/t12-split20(读其 result.json)
  routes_xml 默认 external/bench2drive/leaderboard/data/bench2drive220.xml(全量,外推分母)

输出:每路线 town/game 时/wall 时/DS/SR/违章计数;按 town 均值外推 220 全量墙钟。
"""
import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

FULL220 = "external/bench2drive/leaderboard/data/bench2drive220.xml"


def town_map(xml_path):
    root = ET.parse(xml_path).getroot()
    return {r.get("id"): r.get("town") for r in root.findall("route")}


def main():
    out_dir = sys.argv[1]
    full_xml = sys.argv[2] if len(sys.argv) > 2 else FULL220
    data = json.load(open(f"{out_dir}/result.json"))
    ckpt = data["_checkpoint"]
    records = ckpt["records"]
    id2town = town_map(full_xml)

    print(f"progress: {ckpt['progress'][0]}/{ckpt['progress'][1]}  records={len(records)}")
    print(f"{'route':<28} {'town':<10} {'status':<22} {'game_s':>7} {'wall_s':>7} {'DS':>6} {'RC':>6} infr")
    by_town = defaultdict(list)
    for r in records:
        rid = r["route_id"].replace("RouteScenario_", "").replace("_rep0", "")
        town = id2town.get(rid, "?")
        meta = r.get("meta", {})
        game = meta.get("duration_game", 0)
        wall = meta.get("duration_system", 0)
        ds = r["scores"]["score_composed"]
        rc = r["scores"]["score_route"]
        infr = sum(len(v) for k, v in r["infractions"].items() if k != "min_speed_infractions")
        by_town[town].append((wall, game, ds))
        print(f"{r['route_id']:<28} {town:<10} {r['status']:<22} {game:>7.1f} {wall:>7.1f} {ds:>6.1f} {rc:>6.1f} {infr}")

    # 全量 town 分布
    full_towns = defaultdict(int)
    for t in id2town.values():
        full_towns[t] += 1

    print("\n--- 按 town 均值外推 220 ---")
    total_wall = 0.0
    for t in sorted(full_towns):
        n_full = full_towns[t]
        obs = by_town.get(t, [])
        if obs:
            mean_wall = sum(x[0] for x in obs) / len(obs)
            print(f"{t:<10} 全量 {n_full:>3} 条 | 样本 {len(obs)} 条,均值 wall {mean_wall:>7.1f}s → {n_full * mean_wall / 3600:>6.2f}h")
            total_wall += n_full * mean_wall
        else:
            print(f"{t:<10} 全量 {n_full:>3} 条 | 无样本")
    print(f"\n外推总墙钟(仅有样本 town 按均值,无样本 town 未计): {total_wall / 3600:.2f}h")


if __name__ == "__main__":
    main()
