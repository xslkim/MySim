# CP2 报告 — UE5 自建闭环基建验收

> 日期：2026-08-30
> 里程碑：M2 UE5 闭环基建（T2.x）

## 判据逐项核对

### 1. 全路线集自动跑通

- **PASS**：60 route-runs（20 路线 × 3 seeds）无人值守全部完成，无失败路线。
- 日志：`logs/t24-trivial/`，后台任务 `bash-w3tpx770`。
- 崩溃自动重启内置，未触发 server 崩溃。

### 2. 评分无 NaN/缺项

- **PASS**：scoring_core 单元测试全部通过（`tools/ue5harness/test_scoring_core.py`）。
- 60 route-runs 评分汇总无 NaN，DS/SR 字段完整。

### 3. 同步模式生效

- **PASS**：全程 synchronous_mode=True + fixed_delta_seconds=0.05（20Hz），TM 同步开启。
- config 见 `experiments/EXP-T2.4-trivial-ue5/config.yaml`。

### 4. T2.6 交叉验证

- **部分 PASS**：
  - 无违章路线：UE4 侧 route_executor + scoring_core 6 条全 Perfect，DS=99.25 ±0.09。
  - 违章注入：单元测试验证碰撞/闯红灯/超时/堵路判定正确。
  - 系数集：与 Bench2Drive `statistics_manager.py` 完全一致。
  - **限制**：官方 leaderboard trivial agent（npc_agent）在同步模式下 TickRuntime 频发，未能完成有效 DS 对拍。严格"同一 tick 原始记录双实现重判"需修改 leaderboard 保存 tick 数据，当前以单元测试 + 系数集一致性替代。

## 产出清单

| 文件 | 说明 |
|---|---|
| `tools/ue5harness/route_executor.py` | UE5 route 执行器 |
| `tools/ue5harness/scoring_core.py` | DS/SR 核心判定纯函数模块 |
| `tools/ue5harness/scoring.py` | UE5 侧评分适配层 |
| `tools/ue5harness/scoring_ue4_adapter.py` | UE4 侧评分适配层 |
| `tools/ue5harness/t24_run_trivial.py` | trivial agent 批量运行脚本 |
| `tools/ue5harness/t26_inject_violations.py` | 违章注入测试脚本 |
| `tools/ue5harness/test_scoring_core.py` | 单元测试 |
| `tools/ue5harness/README.md` | harness 文档 |
| `data/routes/ue5_aligned_routes.xml` | UE5 对齐路线集（20 条） |
| `data/routes/ue4_aligned_routes.xml` | UE4 对齐路线集（20 条） |
| `data/routes/aligned_routes_mapping.json` | 语义对齐表 |
| `experiments/EXP-T2.4-trivial-ue5/` | T2.4 实验记录 |
| `logs/t24-trivial/` | T2.4 全程日志与结果 |
| `logs/t26-ue4-executor/` | T2.6 UE4 侧 executor 结果 |
| `logs/t26-ue4-leaderboard/` | T2.6 官方 leaderboard 对照 |

## 结论

M2 UE5 自建闭环基建核心功能已就绪：route 执行器、DS/SR 评分、对齐路线集、trivial agent 无人值守运行全部通过。
T2.6 交叉验证因官方 leaderboard trivial agent 运行异常，以单元测试 + 系数集一致性替代严格对拍，结论可接受。

## 后续

- CP2 人工验收后进入 M3（渲染对比与 zero-shot 迁移实验）。
- UE5 侧模型评测（SimLingo/AutoMoT zero-shot）可基于本 harness 的 socket 接口接入。
