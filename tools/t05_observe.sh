#!/usr/bin/env bash
# T0.5 观测循环:每 15s 记宿主 RAM 空闲(KB)与 GPU 显存占用(MiB)
# 用法: bash tools/t05_observe.sh logs/t05-observe.log
OUT="${1:-logs/t05-observe.log}"
echo "# ts host_ram_free_kb gpu_mem_used_mib" > "$OUT"
while true; do
  TS=$(date -Is)
  RAM=$(powershell.exe -NoProfile -Command "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory" 2>/dev/null | tr -d '\r')
  GPU=$(powershell.exe -NoProfile -Command "& 'C:\Windows\System32\nvidia-smi.exe' --query-gpu=memory.used --format=csv,noheader" 2>/dev/null | tr -d '\r')
  echo "$TS $RAM $GPU" >> "$OUT"
  sleep 15
done
