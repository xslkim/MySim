#!/bin/bash
# tools/t12_eval_guardian.sh — T1.2 双实例全量评测的 evaluator 停滞看门狗。
#
# 背景:2026-08-29 07:31 halfA 的 CARLA server 挂起,evaluator 600s 超时后本进程
# 死锁在清理段(futex_wait)不退,harness 的 while 自愈只在进程退出后触发 → 白停 3.5h。
# 本脚本每 5min 检查各 half 最新 eval_attempt*.log 的写入间隔,>25min 无写入则杀对应
# evaluator(按 --port 匹配,不碰 server),harness 循环随即 ensure+--resume 续跑。
# 两侧 harness 都打印"全部路线完成"后自动退出。
#
# 合法停顿上界:路线间切图/模型 setup 实测 <5min;25min 阈值有 5× 余量,不误杀。

cd /home/xsl/MySim || exit 1

while true; do
    alldone=1
    for spec in "halfA 2031" "halfB 2041"; do
        read -r h port <<< "$spec"
        harness=logs/t12-220-$h-harness.log
        dir=logs/t12-220-$h
        [ -f "$harness" ] || continue
        if grep -q '全部路线完成' "$harness"; then continue; fi
        alldone=0
        latest=$(ls -t "$dir"/eval_attempt*.log 2>/dev/null | head -1)
        [ -n "$latest" ] || continue
        idle=$(( $(date +%s) - $(stat -c %Y "$latest") ))
        if [ "$idle" -gt 1500 ]; then
            # conda run 包装进程的 cmdline 也含 evaluator 参数,pgrep 会双双匹配——
            # 必须全部杀掉(只杀 head -1 会杀到包装进程,真 evaluator 漏杀,tee 管道不关,harness 卡死)
            pids=$(pgrep -f "leaderboard_evaluator.py.*--port=$port")
            if [ -n "$pids" ]; then
                echo "[guardian] $(date '+%F %T') $h eval 停滞 ${idle}s,杀 evaluator 进程组:$(echo $pids | tr '\n' ' ')触发 harness 自愈"
                kill $pids 2>/dev/null; sleep 5; kill -9 $pids 2>/dev/null
            fi
        fi
    done
    [ "$alldone" -eq 1 ] && { echo "[guardian] 两侧均已完成,退出"; exit 0; }
    sleep 300
done
