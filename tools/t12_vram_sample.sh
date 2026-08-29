#!/bin/bash
# tools/t12_vram_sample.sh — 评测期间 5090 显存峰值采样(后台跑,评测结束后停)。
# 用法: tools/t12_vram_sample.sh <out_file> [interval_s]
OUT=${1:-/tmp/t12_vram_peak.log}
INT=${2:-30}
echo "# ts vram_used_mib host_free_gib" > "$OUT"
peak=0
while true; do
    line=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
    free_gib=$(awk '/MemAvailable/{printf "%.1f", $2/1048576}' /proc/meminfo)
    ts=$(date +%s)
    echo "$ts $line $free_gib" >> "$OUT"
    [ "${line:-0}" -gt "$peak" ] && peak=$line
    echo "# peak_so_far_mib $peak" > "$OUT.peak"
    sleep "$INT"
done
