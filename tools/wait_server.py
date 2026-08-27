#!/usr/bin/env python3
"""等 CARLA server RPC 就绪 + 校验 5090 被占用。用法: wait_server.py <port> [timeout_s]"""
import subprocess, sys, time

port = int(sys.argv[1]); timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 180
host = subprocess.check_output("ip route show | awk '/default/{print $3}'", shell=True).decode().strip()

import carla
t0 = time.time()
while time.time() - t0 < timeout:
    try:
        c = carla.Client(host, port); c.set_timeout(5.0)
        c.get_world().get_actors()
        break
    except Exception:
        time.sleep(5)
else:
    print("TIMEOUT waiting RPC"); sys.exit(1)

# 5090 占用校验:server 渲染后显存应明显超基线
out = subprocess.check_output(
    ["powershell.exe", "nvidia-smi.exe", "--query-gpu=memory.used", "--format=csv,noheader"],
    text=True).strip()
print(f"RPC ready in {time.time()-t0:.1f}s; nvidia-smi mem.used={out}")
used_mb = int(out.replace("MiB", "").strip())
if used_mb < 4000:
    print("WARN: 显存未明显上升,可能选错卡(5090 未被 server 占用)")
    sys.exit(2)
sys.exit(0)
