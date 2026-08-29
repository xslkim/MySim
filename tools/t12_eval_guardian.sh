#!/bin/bash
# tools/t12_eval_guardian.sh — 评测 evaluator 停滞看门狗(通用化:任意路数任意 harness)。
#
# 背景:2026-08-29 07:31 halfA 的 CARLA server 挂起,evaluator 600s 超时后本进程
# 死锁在清理段(futex_wait)不退,harness 的 while 自愈只在进程退出后触发 → 白停 3.5h。
# 本脚本每 5min 检查各监视对象最新 eval_attempt*.log 的写入间隔,>25min 无写入则杀对应
# evaluator(按 --port 匹配,不碰 server),harness 循环随即 ensure+--resume 续跑。
# 全部对象的 harness 都打印"全部路线完成"后自动退出。
#
# 用法: tools/t12_eval_guardian.sh [name:port:outdir:harnesslog ...]
#   不带参数 = 兼容默认(T1.2 双 half);每路一个四元组,如:
#   tools/t12_eval_guardian.sh t13full:2031:logs/t13-full220:logs/t13-full220-harness.log
#
# 合法停顿上界:路线间切图/模型 setup 实测 <5min;25min 阈值有 5× 余量,不误杀。

cd /home/xsl/MySim || exit 1

if [ "$#" -eq 0 ]; then
    set -- "halfA:2031:logs/t12-220-halfA:logs/t12-220-halfA-harness.log" \
           "halfB:2041:logs/t12-220-halfB:logs/t12-220-halfB-harness.log"
fi

while true; do
    alldone=1
    for spec in "$@"; do
        IFS=: read -r name port dir harness <<< "$spec"
        [ -f "$harness" ] || { alldone=0; continue; }
        if grep -q '全部路线完成' "$harness"; then continue; fi
        alldone=0
        latest=$(ls -t "$dir"/eval_attempt*.log 2>/dev/null | head -1)
        [ -n "$latest" ] || continue
        idle=$(( $(date +%s) - $(stat -c %Y "$latest") ))
        if [ "$idle" -gt 1500 ]; then
            # conda run 包装进程的 cmdline 也含 evaluator 参数,pgrep 会双双匹配——
            # 必须全部杀掉(只杀 head -1 会杀到包装进程,真 evaluator 漏杀,tee 管道不关,harness 卡死);
            # 同时排除本脚本自身($$,cmdline 含模式串)
            pids=$(pgrep -f "leaderboard_evaluator.py.*--port=$port" | grep -vx $$)
            if [ -n "$pids" ]; then
                echo "[guardian] $(date '+%F %T') $name eval 停滞 ${idle}s,杀 evaluator 进程:$(echo $pids | tr '\n' ' ')触发 harness 自愈"
                kill $pids 2>/dev/null; sleep 5; kill -9 $pids 2>/dev/null
            fi
        fi
    done
    [ "$alldone" -eq 1 ] && { echo "[guardian] 全部对象已完成,退出"; exit 0; }
    sleep 300
done
