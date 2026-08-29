#!/usr/bin/env python3
"""t11_ensure_server.py — 确保 CARLA server 就绪且在 5090 上(run_eval_ue4.sh 的服务端保障步)。

逻辑复用 tools/server_watchdog.py 的 SIDES/kill_side/launch_once/restart:
- server 活着且 5090 显存 ≥ GPU_FLOOR_MB → exit 0
- server 活着但显存平躺(选错卡特征,T0.6)→ 杀掉重启
- server 失联 → kill_side + adapter 轮询 [0,2,1,3] 重启,每次 launch 内置显存增量校验

用法: python3 tools/t11_ensure_server.py [ue4|ue5]
exit: 0 就绪;2 全部 adapter 候选失败
"""
import sys

sys.path.insert(0, "/home/xsl/MySim/tools")
import server_watchdog as w

GPU_FLOOR_MB = 5000  # Epic 720p UE4 server 实测 +8.1GB;低于此判错卡/半死不活


def main():
    side = sys.argv[1] if len(sys.argv) > 1 else "ue4"
    port = w.SIDES[side]["port"]

    if w.server_alive(port):
        used = w.gpu_used_mb()
        if used >= GPU_FLOOR_MB:
            print(f"[ensure] {side} 就绪(port={port}, 5090 显存 {used} MiB)", flush=True)
            return 0
        print(f"[ensure] {side} RPC 通但 5090 显存仅 {used} MiB(<{GPU_FLOOR_MB}),判错卡,重启", flush=True)
    else:
        print(f"[ensure] {side} 失联,清理 + adapter 轮询重启", flush=True)

    ok = w.restart(side)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
