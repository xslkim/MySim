#!/usr/bin/env python3
"""t12_split220_dual.py — bench2drive220.xml 对半切成双实例并发用的两个子集(T1.2 阶段 B)。

切法:按 town 聚簇内**轮流发牌**(round-robin),两半各自拿到每个 town 的约一半路线,
镇数/场景类型分布天然对齐;两半各自保持官方相对顺序(同 town 连续,地图加载次数最优)。

用法: python3 tools/t12_split220_dual.py
输出: external/bench2drive/leaderboard/data/bench2drive220_halfA.xml
      external/bench2drive/leaderboard/data/bench2drive220_halfB.xml
"""
import xml.etree.ElementTree as ET
from collections import defaultdict
from xml.dom import minidom

SRC = "external/bench2drive/leaderboard/data/bench2drive220.xml"
DST = {
    0: "external/bench2drive/leaderboard/data/bench2drive220_halfA.xml",
    1: "external/bench2drive/leaderboard/data/bench2drive220_halfB.xml",
}


def main():
    tree = ET.parse(SRC)
    routes = tree.getroot().findall("route")

    # 每个 town 内轮流发牌 → assign[route_id] ∈ {0,1}
    by_town = defaultdict(list)
    for r in routes:
        by_town[r.get("town")].append(r)
    assign = {}
    for town, rs in by_town.items():
        for i, r in enumerate(rs):
            assign[r.get("id")] = i % 2

    for half in (0, 1):
        new_root = ET.Element("routes")
        for r in routes:  # 保持官方相对顺序
            if assign[r.get("id")] == half:
                new_root.append(r)
        raw = ET.tostring(new_root, encoding="utf-8")
        pretty = minidom.parseString(raw).toprettyxml(indent="   ", encoding="utf-8")
        with open(DST[half], "wb") as f:
            f.write(pretty)
        towns = defaultdict(int)
        for r in new_root.findall("route"):
            towns[r.get("town")] += 1
        print(f"written {DST[half]} ({len(new_root.findall('route'))} routes) {dict(towns)}")


if __name__ == "__main__":
    main()
