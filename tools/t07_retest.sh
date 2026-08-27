#!/bin/bash
# CP0 收口复测 v2(A1 降档 32GB 生效后):
#   1) 起 UE5 server(2021, adapter 从 $1 起试,默认 0)→ 2) WSL 压 28GB 驻留 240s,期间每 15s 采宿主空闲 RAM
#   3) 释压 → 4) server 存活检查 → 5) 60s 冒烟回归 → 6) 杀 server
# 用法: bash tools/t07_retest.sh [adapter_index]
set -u
cd /home/xsl/MySim
ADAPTER=${1:-0}
HOST_IP=$(ip route show | awk '/default/{print $3}')
PS="powershell.exe -NoProfile -Command"

echo "[$(date '+%T')] 启动 UE5 server (2021, adapter=$ADAPTER)"
$PS "Start-Process -FilePath 'C:\carla\CARLA_0.10.0\Carla-0.10.0-Win64-Shipping\CarlaUnreal.exe' -ArgumentList '-carla-rpc-port=2021','-graphicsadapter=$ADAPTER','-quality-level=Epic','-windowed','-ResX=1280','-ResY=720' -WorkingDirectory 'C:\carla\CARLA_0.10.0\Carla-0.10.0-Win64-Shipping' -PassThru | Select-Object Id" 2>&1 | tr -d '\r'

echo "[$(date '+%T')] 等 RPC 就绪 + 5090 占用校验"
conda run -n mysim-ue5 python3 tools/wait_server.py 2021 180
rc=$?
if [ $rc -ne 0 ]; then
  echo "[$(date '+%T')] wait_server rc=$rc,杀 server 退出(换 adapter 重跑)"
  $PS "Stop-Process -Name CarlaUnreal -Force -ErrorAction SilentlyContinue; exit 0" 2>&1 | tr -d '\r'
  exit $rc
fi

echo "[$(date '+%T')] 压 WSL 28GB 驻留 240s + 采宿主 RAM"
python3 tools/t05_ram_gate.py --gb 28 --hold-s 240 &
GATE=$!
sleep 60
for i in $(seq 1 12); do
  free_kb=$($PS "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory" 2>/dev/null | tr -d '\r' | tr -d ' ')
  vram=$(powershell.exe nvidia-smi.exe --query-gpu=memory.used --format=csv,noheader 2>/dev/null | tr -d '\r')
  echo "$(date '+%F %T') host_free_KB=$free_kb vram=$vram" | tee -a logs/t07-ram-observe.log
  sleep 15
done
wait $GATE

echo "[$(date '+%T')] 释压完成,server 存活检查"
conda run -n mysim-ue5 python3 -c "
import carla; c=carla.Client('$HOST_IP',2021); c.set_timeout(10.0)
print('server alive, actors:', len(c.get_world().get_actors()))" || echo "SERVER_DIED"

echo "[$(date '+%T')] 60s 冒烟回归"
conda run -n mysim-ue5 python3 tools/smoke_carla.py --port 2021 --minutes 1 --frames 50 --out logs/smoke-ue5-rerun.json

echo "[$(date '+%T')] 收尾杀 server"
$PS "Stop-Process -Name CarlaUnreal -Force -ErrorAction SilentlyContinue; exit 0" 2>&1 | tr -d '\r'
echo "[$(date '+%T')] RETEST_DONE"
