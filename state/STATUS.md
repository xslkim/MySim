# STATUS.md — 全局快照(由 orchestrator 每轮重建)

> 重建时间:2026-08-30 傍晚(M1 收口)

## 里程碑:M1 UE4 基线复现 —— **收口(CP1 PASS)**

CP1 报告:`state/CP1-report.md`(判据逐项核对:Bench2Drive v0.0.3 钉死 ✓;SimLingo 220 全量 DS=86.18/SR=68.2% 对官方 85.07±0.95/67.27±2.11 ✓;AutoMoT 56 子集 DS=89.17 对 87.34/89.42 ✓)

## 任务卡终态
| 卡 | 状态 | 一句话 |
|---|---|---|
| T1.0 SimLingo 训练栈 | done | 32GB 可全量微调(bs=6 峰 19.6GiB) |
| T1.1 Bench2Drive 接线 | done | B2D_EXTERNAL_SERVER 补丁链 |
| T1.2 SimLingo 220 基线 | done PASS | DS=86.18/SR=68.2%;13 条失败归因=静止障碍绕行弱 |
| T1.2b 推理提速 | done | FASTPATH 2.24× 采纳(eval-only,声明义务见 CP1 §4) |
| T1.3 AutoMoT 基线 | done PASS | 56 子集 DS=89.17;ckpt 改名根因已修;220 全量缓跑可 --resume 补齐 |
| T1.4 MindDrive 移植 | done | CPU+GPU 前向过;闭环接线/RL 链 open |
| T1.5 CP1 汇总 | done | 本报告即产出 |

## 当前状态
- GPU 全空,UE4/UE5 server 均已收编;在飞后台任务:无;巡检 cron 已停(M1 全自动授权期满)
- 下一里程碑:**M2 UE5 自建闭环基建(T2.x)**——CP2 判据:全路线集自动跑通 + T2.6 评分双实现交叉验证 mean |ΔDS|<0.5;**待用户审 CP1 报告后授权开工**

## 文档与资产
- 逐日日志:docs/log/2026-08-2{8,9,30}.md;任务卡 state/tasks/T1.*.md;游标 state/orchestrator-cursor.md(含 36 班巡检记录)
- git:主仓至 d73e614+(本次收口提交见最新);外仓本地补丁:simlingo ca98921、bench2drive c82e5b8、minddrive 69f850c、AutoMoT f86e40a
- 关键工具:tools/run_eval_ue4.sh、run_eval_automot_ue4.sh、t11_ensure_server.py、server_watchdog.py(ue4/ue4b/ue5 三侧)、t12_eval_guardian.sh(通用停滞看门狗)、t12/t13 路线子集生成器

## 预警
- AutoMoT 220 全量补跑(~30h 单实例)未做,D16 决策缓跑;UE5 zero-shot 用同 ckpt/同补丁链
- 13 条 SimLingo 失败路线是 M3 域差距敏感探针(CP1 §5)
- 评测期 RDP 连接或诱发 server 停顿(嫌疑未坐实);M2 UE5 侧沿用"断 RDP 跑评测"惯例
