#!/usr/bin/env python3
"""t12_select_split20.py — 从 bench2drive220.xml 分层抽 20 条冒烟子集(T1.2 阶段 A)。

bench2drive 官方 tools/split_xml.py 只做顺序等分(多卡并行用),无分层子集范式,
故按任务要求自建:town 全覆盖 + 权重偏向 Town12/13(220 全量里 LargeMap 占 75%,
外推精度主要由它们决定),镇内等间距抽样(确定性),输出保持官方相对顺序
(官方序大致按 town 聚簇,子集同样聚簇,地图加载次数与全量同构)。

抽样配额(合计 20):
  Town01:1 Town02:1 Town03:2 Town04:2 Town05:1 Town06:1 Town07:1 Town10HD:1
  Town11:1 Town12:5 Town13:3 Town15:1

用法: python3 tools/t12_select_split20.py
输出: external/bench2drive/leaderboard/data/bench2drive_split20.xml
"""
import xml.etree.ElementTree as ET
from collections import defaultdict
from xml.dom import minidom

SRC = "external/bench2drive/leaderboard/data/bench2drive220.xml"
DST = "external/bench2drive/leaderboard/data/bench2drive_split20.xml"

QUOTA = {
    "Town01": 1, "Town02": 1, "Town03": 2, "Town04": 2, "Town05": 1,
    "Town06": 1, "Town07": 1, "Town10HD": 1,
    "Town11": 1, "Town12": 5, "Town13": 3, "Town15": 1,
}


def linspace_indices(n, k):
    """n 个里等间距取 k 个(含两端),返回索引列表。"""
    if k >= n:
        return list(range(n))
    return sorted({round(i * (n - 1) / (k - 1)) for i in range(k)}) if k > 1 else [n // 2]


def main():
    tree = ET.parse(SRC)
    root = tree.getroot()
    routes = root.findall("route")

    by_town = defaultdict(list)
    for r in routes:
        by_town[r.get("town")].append(r)

    picked_ids = set()
    for town, k in QUOTA.items():
        cand = by_town[town]
        assert len(cand) >= k, f"{town} 只有 {len(cand)} 条,配额 {k}"
        for i in linspace_indices(len(cand), k):
            picked_ids.add(cand[i].get("id"))
    assert len(picked_ids) == 20, f"抽到 {len(picked_ids)} 条 != 20(镇内等间距去重撞车)"

    # 保持官方相对顺序
    new_root = ET.Element("routes")
    for r in routes:
        if r.get("id") in picked_ids:
            new_root.append(r)

    raw = ET.tostring(new_root, encoding="utf-8")
    pretty = minidom.parseString(raw).toprettyxml(indent="   ", encoding="utf-8")
    with open(DST, "wb") as f:
        f.write(pretty)

    # 摘要
    print(f"written {DST} ({len(picked_ids)} routes)")
    for r in new_root.findall("route"):
        sc = r.find("scenarios")[0]
        print(f"  id={r.get('id'):>6} town={r.get('town'):<10} scenario={sc.get('type')}")


if __name__ == "__main__":
    main()
