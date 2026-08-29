#!/bin/bash
# tools/run_eval_automot_ue4.sh — AutoMoT agent × vendored leaderboard(UE4 CARLA 0.9.15)评测运行脚本。
#
# 用法:
#   tools/run_eval_automot_ue4.sh [routes_xml] [out_dir] [port] [max_restarts]
# 默认:
#   routes_xml = external/AutoMoT/leaderboard/data/bench2drive_smoke3.xml(25975/26401/28154,抽自 220)
#   out_dir    = logs/t13-smoke3
#   port       = 2031(UE4 server,winNAT 坑见 AGENTS.md)
#   max_restarts = 3
#
# 崩溃自愈:server 失联/错卡 → 杀进程 → adapter [0,2,1,3] 轮询 + nvidia-smi 显存校验
# (tools/t11_ensure_server.py,必须用 mysim-simlingo env 调,它依赖该 env 的 carla 包探活;
#  裸 python3 会让 server_alive 恒 False → 兜底按名杀进程团灭,见 AGENTS.md"T1.2 全量"坑录)
# → leaderboard --resume 续跑。断点续跑:再次执行同一命令即可。
#
# 与 SimLingo 侧(run_eval_ue4.sh)差异:
# - 评测走 AutoMoT 仓 vendored leaderboard(已打 B2D_EXTERNAL_SERVER + importlib.metadata 两补丁),
#   无 cwd 约束(weather.xml 走 __file__ 相对路径)。
# - conda env 为 mysim-automot;模型加载全走 env(AUTOMOT_MODEL_PATH 与 QWEN3VL_PATH 必须同设,
#   eval 侧 qwen3vl_path 不回退 AUTOMOT_MODEL_PATH)。
# - --timeout 用 vendored 默认 1200(b2d 侧 600);TM_SEED=3407(对齐官方脚本)。
# - GPU 选择全走 CUDA_VISIBLE_DEVICES(模型内 cuda:0 硬编码,单卡设 0);--gpu-rank 仅 crash 分支用。
#
# 已知细节(勿改):
# - --resume 是 type=bool,传 "False" 也是 True(bool 坑)——首轮运行必须整个省略该参数;
#   官方 run_evaluation.sh 恒传 --resume=${RESUME}=恒 True,不要抄那个行为。
# - SAVE_PATH 必须结尾带 '/',agent 里是字符串拼接不是 os.path.join。
# - evaluator 把 agent_config 拼成 "<TEAM_CONFIG>+<route>_<town>_<scenario>_<weather>_<time>",仅作 viz 标记。
# - evaluator 崩溃分支 ps -ef|grep graphicsadapter 在 WSL 摸不到 Windows 进程,无效但无害。

set -uo pipefail

ROOT=/home/xsl/MySim
AM=$ROOT/external/AutoMoT
CARLA_API=/home/xsl/carla0915-pythonapi
CONDA_ENV=mysim-automot          # 评测 env
ENSURE_ENV=mysim-simlingo        # ensure_server/watchdog 专用(依赖其 carla 包探活,勿改)

ROUTES_XML=$(readlink -f "${1:-$AM/leaderboard/data/bench2drive_smoke3.xml}")
OUT_DIR=$(readlink -f "${2:-$ROOT/logs/t13-smoke3}")
PORT=${3:-2031}
MAX_RESTARTS=${4:-3}
TM_PORT=${TM_PORT:-8000}
SIDE=${SIDE:-ue4}                # 只用 ue4 主实例(2031);ue4b/ue5 不动
TM_SEED=${TM_SEED:-3407}         # 官方脚本默认(SimLingo 侧为 0)

RESULT_JSON=$OUT_DIR/result.json
DEBUG_CKPT=$OUT_DIR/live_results.txt
CKPT=$ROOT/data/checkpoints/automot

mkdir -p "$OUT_DIR" "$OUT_DIR/viz"

export PYTHONPATH="$CARLA_API:$CARLA_API/carla:$AM/leaderboard:$AM/leaderboard/team_code:$AM/scenario_runner:$AM/Automot:$AM/Automot/mot"
export LEADERBOARD_ROOT=$AM/leaderboard
export SCENARIO_RUNNER_ROOT=$AM/scenario_runner
export B2D_EXTERNAL_SERVER=1
export IS_BENCH2DRIVE=True
export PLANNER_TYPE=only_traj
export AUTOMOT_MODEL_PATH=$CKPT
export QWEN3VL_PATH=$CKPT        # 必须与 AUTOMOT_MODEL_PATH 同指(eval 侧不回退)
export SAVE_PATH="$OUT_DIR/viz/"
export ROUTES="$ROUTES_XML"
export HF_ENDPOINT=https://hf-mirror.com
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TORCH_COMPILE_DISABLE=1
export CUDA_VISIBLE_DEVICES=0    # 模型内 cuda:0 硬编码,单卡

HOST_IP=$(ip route show | awk '/default/{print $3}')
echo "[run_eval] routes=$ROUTES_XML out=$OUT_DIR host=$HOST_IP port=$PORT tm=$TM_PORT side=$SIDE"

attempt=0
while true; do
    # 1) server 保障(失联/错卡自愈)——必须 mysim-simlingo env(见头注)
    conda run --no-capture-output -n "$ENSURE_ENV" python3 "$ROOT/tools/t11_ensure_server.py" "$SIDE"
    if [ $? -ne 0 ]; then
        echo "[run_eval] server 全部 adapter 候选失败,BLOCKED"
        exit 2
    fi

    # 2) 续跑判定:已有有效 result json → --resume=True(首轮无 result.json 自然省略,见头注 bool 坑)
    RESUME_ARG=""
    if [ -s "$RESULT_JSON" ] && grep -q '"records"' "$RESULT_JSON" ]; then
        RESUME_ARG="--resume=True"
        echo "[run_eval] 检测到已有 checkpoint,续跑(--resume=True)"
    fi

    # 3) 跑 leaderboard(vendored,无 cwd 约束)
    LOG=$OUT_DIR/eval_attempt${attempt}.log
    echo "[run_eval] attempt=$attempt log=$LOG"
    conda run --no-capture-output -n "$CONDA_ENV" python3 -u \
        "$AM/leaderboard/leaderboard/leaderboard_evaluator.py" \
        --routes="$ROUTES_XML" \
        --repetitions=1 \
        --track=SENSORS \
        --checkpoint="$RESULT_JSON" \
        --debug-checkpoint="$DEBUG_CKPT" \
        --timeout=1200 \
        --agent="$AM/leaderboard/team_code/mot_b2d_agent.py" \
        --agent-config="$CKPT" \
        --traffic-manager-seed="$TM_SEED" \
        --host="$HOST_IP" \
        --port="$PORT" \
        --traffic-manager-port="$TM_PORT" \
        --gpu-rank=0 \
        $RESUME_ARG 2>&1 | tee "$LOG"
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
