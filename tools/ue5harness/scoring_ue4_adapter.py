#!/usr/bin/env python3
"""scoring_ue4_adapter.py — UE4 侧 DS/SR 评分适配层（T2.2/T2.6）。

消费 leaderboard 运行的 tick 原始记录(从 RouteScenario criteria 事件重建),独立重判重算 DS。
与 UE5 侧 scoring.py 共享同一 scoring_core 模块,确保同源性(R4-N4)。

用法:
  PYTHONPATH=/home/xsl/MySim/tools/ue5harness python tools/ue5harness/scoring_ue4_adapter.py \
    --leaderboard-result logs/t26-ue4/result.json --out logs/t26-ue4/rescored.json
"""
import argparse
import json
import sys
from typing import List

sys.path.insert(0, "/home/xsl/MySim/tools/ue5harness")
import scoring_core


def load_leaderboard_result(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def extract_ticks_from_record(record: dict) -> List[dict]:
    """从 leaderboard route record 重建 tick 原始记录。

    leaderboard 的 result.json 只保存聚合结果,不含逐 tick 原始记录。
    本适配器需要配合修改过的 leaderboard_evaluator 使用——在运行时将 tick 原始记录落盘。

    若输入为普通 result.json,则只能用聚合信息近似重判(精度受限);
    若输入为含 ticks 的扩展格式,则直接读取。
    """
    if "ticks" in record:
        return record["ticks"]
    #  fallback: 无 tick 级数据,返回空列表(调用方需处理)
    return []


def rescore_route(record: dict) -> scoring_core.RouteScore:
    """对单条 leaderboard route record 重算 DS。"""
    route_id = int(record["route_id"].split("_")[-1]) if "_" in record["route_id"] else int(record["route_id"])
    ticks = extract_ticks_from_record(record)
    if not ticks:
        raise ValueError(f"route {route_id} 无 tick 原始记录,无法重判")

    timeout = "timeout" in record.get("status", "").lower()
    return scoring_core.compute_route_score(
        route_id=route_id,
        ticks=ticks,
        route_length=record["meta"]["route_length"],
        timeout=timeout,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leaderboard-result", required=True, help="leaderboard result.json(需含 ticks 扩展)")
    ap.add_argument("--out", required=True, help="重判结果输出")
    args = ap.parse_args()

    data = load_leaderboard_result(args.leaderboard_result)
    records = data.get("_checkpoint", {}).get("records", [])

    rescored = []
    for record in records:
        if record.get("index", -1) == -1:
            continue
        try:
            rs = rescore_route(record)
            rescored.append(vars(rs))
            print(f"[ue4-adapter] route {rs.route_id}: 官方 DS={record['scores']['score_composed']:.2f} "
                  f"vs 重算 DS={rs.score_composed:.2f}", flush=True)
        except ValueError as e:
            print(f"[ue4-adapter] {e},跳过", flush=True)

    with open(args.out, "w") as f:
        json.dump(rescored, f, indent=2, ensure_ascii=False, default=str)
    print(f"[ue4-adapter] 重判结果保存 {args.out}", flush=True)


if __name__ == "__main__":
    main()
