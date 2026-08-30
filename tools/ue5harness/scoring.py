#!/usr/bin/env python3
"""scoring.py — UE5 侧 DS/SR 评分适配层（T2.2）。

消费 route_executor 的 tick 记录文件,调用 scoring_core 计算 DS/SR。
用法:
  python tools/ue5harness/scoring.py --ticks logs/t24-trivial/route_10000_ticks.json --route-length 101.7
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, "/home/xsl/MySim/tools/ue5harness")
import scoring_core


def load_ticks(ticks_path: str):
    with open(ticks_path) as f:
        return json.load(f)


def load_result(result_path: str):
    with open(result_path) as f:
        return json.load(f)


def score_route_from_files(result_path: str, ticks_path: str) -> scoring_core.RouteScore:
    result = load_result(result_path)
    ticks = load_ticks(ticks_path)
    timeout = "timeout" in result.get("status", "").lower()
    return scoring_core.compute_route_score(
        route_id=result["route_id"],
        ticks=ticks,
        route_length=result["route_length"],
        timeout=timeout,
    )


def score_directory(out_dir: str) -> dict:
    """对目录下所有 route_*_result.json 评分并汇总。"""
    pattern = os.path.join(out_dir, "route_*_result.json")
    files = sorted(glob.glob(pattern))
    route_scores = []
    for result_path in files:
        rid = os.path.basename(result_path).replace("route_", "").replace("_result.json", "")
        ticks_path = os.path.join(out_dir, f"route_{rid}_ticks.json")
        if not os.path.exists(ticks_path):
            print(f"[scoring] 警告: 缺少 {ticks_path},跳过", flush=True)
            continue
        rs = score_route_from_files(result_path, ticks_path)
        route_scores.append(rs)
        print(f"[scoring] route {rs.route_id}: DS={rs.score_composed:.2f} RC={rs.score_route:.1f}% "
              f"penalty={rs.score_penalty:.3f} status={rs.status}", flush=True)

    global_scores = scoring_core.compute_global_scores(route_scores)
    print(f"[scoring] 全局: DS={global_scores['score_composed']:.2f} ±{global_scores['score_composed_std']:.2f} "
          f"SR={global_scores['success_rate']:.1f}% ({global_scores['num_completed']}/{global_scores['num_routes']})", flush=True)
    return global_scores


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", help="单条路线 ticks JSON")
    ap.add_argument("--result", help="单条路线 result JSON")
    ap.add_argument("--dir", help="目录模式:评分目录下所有路线")
    ap.add_argument("--out", help="输出汇总 JSON 路径")
    args = ap.parse_args()

    if args.dir:
        scores = score_directory(args.dir)
        if args.out:
            with open(args.out, "w") as f:
                json.dump(scores, f, indent=2, ensure_ascii=False)
            print(f"[scoring] 汇总保存 {args.out}", flush=True)
    elif args.ticks and args.result:
        rs = score_route_from_files(args.result, args.ticks)
        print(json.dumps(vars(rs), indent=2, ensure_ascii=False, default=str))
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
