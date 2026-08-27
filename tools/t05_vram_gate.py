#!/usr/bin/env python3
"""T0.5 显存门禁:torch 在 GPU 上驻留 N GiB buffer。
用法: conda run -n mysim-simlingo python tools/t05_vram_gate.py --gb 8 --hold-s 180
"""
import argparse, time

ap = argparse.ArgumentParser()
ap.add_argument("--gb", type=float, required=True)
ap.add_argument("--hold-s", type=int, default=180)
args = ap.parse_args()

import torch
assert torch.cuda.is_available(), "CUDA unavailable"
free_b, total_b = torch.cuda.mem_get_info()
print(f"[vram-gate] free={free_b/2**30:.1f}GiB total={total_b/2**30:.1f}GiB", flush=True)
need = args.gb * (1 << 30)
assert need < free_b * 0.9, f"refusing: want {args.gb}GiB but only {free_b/2**30:.1f}GiB free"
n = int(need // 4)
buf = torch.empty(n, dtype=torch.float32, device="cuda")
buf.fill_(1.0)
torch.cuda.synchronize()
used = torch.cuda.memory_allocated() / 2**30
print(f"[vram-gate] resident {used:.1f} GiB; holding {args.hold_s}s", flush=True)
t0 = time.time()
while time.time() - t0 < args.hold_s:
    buf += 1e-9  # 保持活跃,防释放优化
    torch.cuda.synchronize()
    time.sleep(10)
print("[vram-gate] done", flush=True)
