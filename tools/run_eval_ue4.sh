#!/bin/bash
# tools/run_eval_ue4.sh — SimLingo agent × Bench2Drive leaderboard(UE4 CARLA 0.9.15)评测运行脚本。
#
# 用法:
#   tools/run_eval_ue4.sh [routes_xml] [out_dir] [port] [max_restarts]
# 默认:
#   routes_xml = external/bench2drive/leaderboard/data/bench2drive_smoke3.xml
#   out_dir    = logs/t11-smoke3
#   port       = 2031(UE4 server,winNAT 坑见 AGENTS.md)
#   max_restarts = 3
#
# 崩溃自愈:server 失联/错卡 → 杀进程 → adapter [0,2,1,3] 轮询 + nvidia-smi 显存校验
# (tools/t11_ensure_server.py,逻辑复用 tools/server_watchdog.py)→ leaderboard --resume 续跑。
# 断点续跑:再次执行同一命令即可(result json 已有记录时自动 --resume=True)。
# 双实例并发(T1.2 起):SIDE=ue4b + 端口 2041 + TM_PORT=8010 起第二路,路线 XML 对半分,
# 两侧 watchdog 按命令行端口区分同名进程,互不干扰。
#
# 已知细节(勿改):
# - evaluator 里 get_weather_id 用相对路径 'leaderboard/data/weather.xml',必须 cd external/bench2drive 跑。
# - --resume 是 type=bool,传 "False" 也是 True(bool 坑)——首轮运行必须整个省略该参数。
# - evaluator 自动把 agent_config 拼成 "<ckpt>+<save_name>",agent 据此建 viz 目录。
# - SAVE_PATH 必须结尾带 '/',agent 里是字符串拼接不是 os.path.join。

set -uo pipefail

ROOT=/home/xsl/MySim
B2D=$ROOT/external/bench2drive
SIMLINGO=$ROOT/external/simlingo
CARLA_API=/home/xsl/carla0915-pythonapi
CONDA_ENV=mysim-simlingo

ROUTES_XML=$(readlink -f "${1:-$B2D/leaderboard/data/bench2drive_smoke3.xml}")
OUT_DIR=$(readlink -f "${2:-$ROOT/logs/t11-smoke3}")
PORT=${3:-2031}
MAX_RESTARTS=${4:-3}
TM_PORT=${TM_PORT:-8000}
SIDE=${SIDE:-ue4}   # ue4=2031 主实例;ue4b=2041 第二实例(并发)

RESULT_JSON=$OUT_DIR/result.json
DEBUG_CKPT=$OUT_DIR/live_results.txt
CKPT=$ROOT/data/checkpoints/simlingo_eval/checkpoints/epoch=013.ckpt/pytorch_model.pt

mkdir -p "$OUT_DIR" "$OUT_DIR/viz"

export PYTHONPATH="$CARLA_API:$CARLA_API/carla:$B2D/leaderboard:$B2D/scenario_runner:$SIMLINGO:$SIMLINGO/team_code"
export LEADERBOARD_ROOT=$B2D/leaderboard
export SCENARIO_RUNNER_ROOT=$B2D/scenario_runner
export B2D_EXTERNAL_SERVER=1
export SAVE_PATH="$OUT_DIR/viz/"
export ROUTES="$ROUTES_XML"
export HF_ENDPOINT=https://hf-mirror.com
export WANDB_MODE=offline
export TOKENIZERS_PARALLELISM=false
# T1.2b:SimLingo 推理提速路径开关(1=kv-cache+LoRA merge,默认;0=官方原路径,闭环 A/B 对照用)
export SIMLINGO_FASTPATH=${SIMLINGO_FASTPATH:-1}

HOST_IP=$(ip route show | awk '/default/{print $3}')
echo "[run_eval] routes=$ROUTES_XML out=$OUT_DIR host=$HOST_IP port=$PORT tm=$TM_PORT side=$SIDE"

attempt=0
while true; do
    # 1) server 保障(失联/错卡自愈)
    conda run --no-capture-output -n "$CONDA_ENV" python3 "$ROOT/tools/t11_ensure_server.py" "$SIDE"
    if [ $? -ne 0 ]; then
        echo "[run_eval] server 全部 adapter 候选失败,BLOCKED"
        exit 2
    fi

    # 2) 续跑判定:已有有效 result json → --resume=True(首轮无 result.json 自然省略,见头注 bool 坑;
    #    T1.2 修正:去掉原 attempt>0 条件,否则脚本整体退出后重跑同命令会从零覆盖进度)
    RESUME_ARG=""
    if [ -s "$RESULT_JSON" ] && grep -q '"records"' "$RESULT_JSON" ]; then
        RESUME_ARG="--resume=True"
        echo "[run_eval] 检测到已有 checkpoint,续跑(--resume=True)"
    fi

    # 3) 跑 leaderboard(cwd 必须在 bench2drive 根,weather.xml 相对路径)
    LOG=$OUT_DIR/eval_attempt${attempt}.log
    echo "[run_eval] attempt=$attempt log=$LOG"
    ( cd "$B2D" && conda run --no-capture-output -n "$CONDA_ENV" python3 -u \
        leaderboard/leaderboard/leaderboard_evaluator.py \
        --routes="$ROUTES_XML" \
        --repetitions=1 \
        --track=SENSORS \
        --checkpoint="$RESULT_JSON" \
        --debug-checkpoint="$DEBUG_CKPT" \
        --timeout=600 \
        --agent="$SIMLINGO/team_code/agent_simlingo.py" \
        --agent-config="$CKPT" \
        --traffic-manager-seed=0 \
        --host="$HOST_IP" \
        --port="$PORT" \
        --traffic-manager-port="$TM_PORT" \
        --gpu-rank=0 \
        $RESUME_ARG ) 2>&1 | tee "$LOG"
    rc=${PIPESTATUS[0]}
    echo "[run_eval] evaluator exit rc=$rc"

    if [ "$rc" -eq 0 ]; then
        echo "[run_eval] 全部路线完成 → $RESULT_JSON"
        break
    fi

    attempt=$((attempt + 1))
    if [ "$attempt" -gt "$MAX_RESTARTS" ]; then
        echo "[run_eval] 连续 $MAX_RESTARTS 次非零退出,BLOCKED"
        exit 3
    fi
    echo "[run_eval] 第 $attempt 次重启续跑(server 可能已崩,下一轮 ensure 会处理)"
    sleep 10
done
