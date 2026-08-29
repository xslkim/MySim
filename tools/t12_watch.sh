#!/bin/bash
# tools/t12_watch.sh — T1.2 全量 220(或其他评测目录)一键巡检。
#
# 用法: tools/t12_watch.sh [out_dir] [routes_xml]
#   默认 out_dir=logs/t12-full220,routes_xml=bench2drive220.xml
#
# 输出:评测进程/server 存活、进度(N/220)、最近路线分数、按 town 外推剩余墙钟、显存/内存。
# 巡检节奏建议:前期每 1–2h 一次;日志在 $out_dir/eval_attempt*.log,崩溃自愈由
# run_eval_ue4.sh 内置(ensure_server + --resume)。
ROOT=/home/xsl/MySim
OUT_DIR=$(readlink -f "${1:-$ROOT/logs/t12-full220}")
XML=$(readlink -f "${2:-$ROOT/external/bench2drive/leaderboard/data/bench2drive220.xml}")

echo "=== $(date '+%F %T') 巡检 $OUT_DIR ==="

# 1) 进程树
if pgrep -af "leaderboard_evaluator" | head -3; then :; else echo "[!] leaderboard_evaluator 不在跑"; fi
pgrep -af "run_eval_ue4.sh" | head -2 || echo "[!] run_eval_ue4.sh harness 不在跑"

# 2) server 状态(只读探测;重启由 run_eval_ue4.sh harness 负责,此处不干预)
conda run --no-capture-output -n mysim-simlingo python3 - "$ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1] + "/tools")
import server_watchdog as w
alive = w.server_alive(w.SIDES["ue4"]["port"])
print(f"[server] ue4 RPC alive={alive}, 5090 显存 {w.gpu_used_mb()} MiB")
EOF

# 3) 进度 + 外推
if [ -s "$OUT_DIR/result.json" ]; then
    python3 "$ROOT/tools/t12_progress.py" "$OUT_DIR" "$XML" | tail -40
else
    echo "[!] result.json 尚未生成(首条路线还在跑)"
fi

# 4) 资源
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader
awk '/MemAvailable/{printf "WSL MemAvailable: %.1f GiB\n", $2/1048576}'
echo "最近日志: $(ls -t "$OUT_DIR"/eval_attempt*.log 2>/dev/null | head -1)"
tail -3 "$(ls -t "$OUT_DIR"/eval_attempt*.log 2>/dev/null | head -1)" 2>/dev/null
