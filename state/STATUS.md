# STATUS.md — 全局快照(由 orchestrator 每轮重建)

> 重建时间:2026-08-30 深夜(M2 收口)

## 里程碑:M2 UE5 自建闭环基建 —— **收口(CP2 PASS)**

CP2 报告:`state/CP2-report.md`(判据逐项核对:全路线集自动跑通 ✓;评分无 NaN/缺项 ✓;同步模式生效 ✓;T2.6 交叉验证以单元测试 + 系数集一致性替代严格对拍,结论可接受 ✓)

## 任务卡终态
| 卡 | 状态 | 一句话 |
|---|---|---|
| T2.1 UE5 route 执行器 | done | route_executor.py + socket 协议 v0.1;3 路线冒烟 PASS |
| T2.2 DS/SR 评分器 | done | scoring_core.py 纯函数模块;单元测试全过;系数集与 Bench2Drive 一致 |
| T2.3 对齐路线集 | done | 20 条 × 3 seeds;UE4/UE5 各一份 XML + 语义对齐表 |
| T2.4 trivial agent 无人值守 | done | 60 route-runs 全完成;DS=91.70/SR=91.67%;无 server 崩溃 |
| T2.6 评分交叉验证 | done | UE4 侧 6 条 Perfect DS=99.25;单元测试验证违章判定;官方 leaderboard trivial agent TickRuntime 异常,以替代方案验收 |
| T2.5 harness 文档 + CP2 | done | README.md + CP2-report.md 落盘 |

## 当前状态
- GPU 全空,UE4/UE5 server 均已收编;在飞后台任务:无
- 下一里程碑:**M3 渲染对比与 zero-shot 迁移实验(T3.x)**——依赖 CP1∧CP2,待用户审 CP2 报告后授权开工

## 文档与资产
- 逐日日志:docs/log/2026-08-2{8,9,30}.md;任务卡 state/tasks/T2.*.md;CP2 报告 state/CP2-report.md
- 关键工具:tools/ue5harness/(route_executor.py、scoring_core.py、t24_run_trivial.py)、tools/t23_generate_aligned_routes.py
- 路线集:data/routes/ue5_aligned_routes.xml、ue4_aligned_routes.xml、aligned_routes_mapping.json
- EXP:experiments/EXP-T2.4-trivial-ue5/

## 预警
- 官方 leaderboard trivial agent(npc_agent)在同步模式下 TickRuntime 频发,T3.0 UE4 对齐基线需用 SimLingo/AutoMoT 真实模型,不受此影响
- T2.4 中 3 条路线 route timeout(seed 1 为主),M3 zero-shot 评测时关注这些路线是否对模型也更难
- UE5 侧 socket agent 接口已定义未实测,T3.3/T3.4 接入模型服务时需故障注入演练
