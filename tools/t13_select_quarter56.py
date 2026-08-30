#!/usr/bin/env python3
"""t13_select_quarter56.py — bench2drive220.xml 分层抽 1/4 子集(AutoMoT 侧,用户 08-30 拍板:先打通流程,全量缓跑)。

切法复用 t12_select_split20.py 范式:town 全覆盖 + 镇内等间距(确定性)+ 保持官方相对顺序。
配额 = round(镇总量/4)(min 1):Town12:26 Town13:12 Town03:3 Town04:3 Town05:2 Town06:2
Town07:1 Town11:2 Town15:2 Town01/02/10HD 各 1,合计 56。

已跑路线兼容:harness 以 --resume 续跑时 evaluator 按 route_id 跳过 result.json 已有记录,
v2 已完成的 17 条(Town12 簇)与本子集重叠部分自动跳过,不重复烧时。

用法: python3 tools/t13_select_quarter56.py
输出: external/AutoMoT/leaderboard/data/bench2drive_quarter56.xml
"""
import xml.etree.ElementTree as ET
from collections import defaultdict
from xml.dom import minidom

SRC = "external/AutoMoT/leaderboard/data/bench2drive220.xml"
DST = "external/AutoMoT/leaderboard/data/bench2drive_quarter56.xml"


def linspace_indices(n, k):
    if k >= n:
        return list(range(n))
    return sorted({round(i * (n - 1) / (k - 1)) for i in range(k)}) if k > 1 else [n // 2]


def main():
    routes = ET.parse(SRC).getroot().findall("route")
    by_town = defaultdict(list)
    for r in routes:
        by_town[r.get("town")].append(r)

    picked = set()
    for town, rs in by_town.items():
        k = max(1, round(len(rs) / 4))
        for i in linspace_indices(len(rs), k):
            picked.add(rs[i].get("id"))

    new_root = ET.Element("routes")
    for r in routes:
        if r.get("id") in picked:
            new_root.append(r)
    raw = ET.tostring(new_root, encoding="utf-8")
    pretty = minidom.parseString(raw).toprettyxml(indent="   ", encoding="utf-8")
    with open(DST, "wb") as f:
        f.write(pretty)

    n = len(new_root.findall("route"))
    towns = defaultdict(int)
    for r in new_root.findall("route"):
        towns[r.get("town")] += 1
    print(f"written {DST} ({n} routes) {dict(towns)}")


if __name__ == "__main__":
    main()
