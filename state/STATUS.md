# STATUS.md — 全局快照(由 orchestrator 每轮重建)

> 重建时间:2026-08-29 深夜(T1.2 收口后)

## 当前里程碑:M1 UE4 基线复现(目标:至 CP1;用户授权全自动)

## 任务卡状态
| 卡 | 状态 | 备注 |
|---|---|---|
| T1.0 SimLingo 训练栈 | done | bs=6 峰值 19.6GiB,32GB 可全量微调 |
| T1.1 Bench2Drive 接线 | done | B2D_EXTERNAL_SERVER 补丁链 |
| **T1.2 SimLingo 220 基线** | **done PASS** | **DS=86.18(官方 85.07±0.95)/ SR=68.2%(官方 67.27±2.11)/ RC=96.94**,207/220 Completed;明细 state/tasks/T1.2.md 阶段 B,logs/t12-220-merged.json |
| T1.2b 推理提速 | done | FASTPATH(kv-cache+LoRA merge)采纳,2.24×;SIMLINGO_FASTPATH/SIMLINGO_MERGE 开关 |
| T1.3 AutoMoT 评测装配 | prep-done | 权重 sha256 核验落盘 13GB;接线方案在卡内,待写 run_eval_automot_ue4.sh + vendored 补丁 + 3 路线冒烟 |
| T1.4 MindDrive 移植 | GPU 冒烟中 | CPU 段 PORTED(import/config/构建/ckpt 键全过);agent-21 跑 GPU 前向冒烟 |
| T1.5 CP1 汇总 | pending | 依赖 T1.3/T1.4 收尾 |

## 在飞后台任务
- agent-21 = T1.4 MindDrive GPU 前向冒烟(tools/t14_gpu_smoke.py)

## GPU / server
- GPU 空闲(5090,显存 ~1.5GB 基线);UE4 双 server(2031/2041)与 UE5(2021)均已收编未启动
- 双实例基建:watchdog SIDES ue4/ue4b/ue5;**一切 watchdog 操作必须 conda run -n mysim-simlingo**(裸 python3 探活恒 False 坑)
- 端口:UE5 2021–2023 / UE4 2031–2033 / UE4b 2041–2043;winNAT 保留段 2756–3989+50000–50059(大重启后复查)

## 锁与约定
- GPU 锁:空闲(`state/gpu.lock.d` mkdir 原子,holder.json 5min 心跳)
- 评测容错链:harness while 重启 + ensure_server(adapter 轮询+显存校验)+ t12_eval_guardian.sh(停滞 25min 杀 evaluator)+ leaderboard --resume 断点续跑
- 长任务脚本运行期间禁改(字节偏移坑);改完任何脚本必须 bash -n / py_compile

## 文档
- 日志:docs/log/2026-08-28.md、docs/log/2026-08-29.md(逐日)
- 任务卡:state/tasks/T1.*.md;编排游标:state/orchestrator-cursor.md

## 预警
- 13 条 220 失败路线归因未做(TickRuntime 卡死为主),CP1 材料
- evaluator 死锁刺激源(RDP device-lost)嫌疑未坐实,T1.3 复跑观察
- 磁盘:WSL vhdx(G:)剩 ~582GB 数据预算;data/ 已 51GB(checkpoints 4 套)
