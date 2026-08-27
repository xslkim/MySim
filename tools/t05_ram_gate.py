#!/usr/bin/env python3
"""T0.5 RAM 门禁兜底:分配并逐页触碰 N GB,驻留到收到回车/信号。
用法: python3 tools/t05_ram_gate.py --gb 30
"""
import argparse, os, sys, time

ap = argparse.ArgumentParser()
ap.add_argument("--gb", type=float, required=True)
ap.add_argument("--hold-s", type=int, default=600, help="驻留秒数(默认 600)")
args = ap.parse_args()

nbytes = int(args.gb * (1 << 30))
print(f"[ram-gate] allocating {args.gb} GiB ...", flush=True)
buf = bytearray(nbytes)  # 分配
# 逐页触碰(4K 一页,步进 4MiB 足够让每页都 commit——bytearray 已 zero-fill 实际已触碰;
# 为保险起见再走一遍 4K 步进写入,防止惰性分配)
step = 4096
mv = memoryview(buf)
for off in range(0, nbytes, step):
    mv[off] = 1
print(f"[ram-gate] touched {nbytes} bytes; holding {args.hold_s}s", flush=True)
t0 = time.time()
while time.time() - t0 < args.hold_s:
    time.sleep(5)
print("[ram-gate] done", flush=True)
