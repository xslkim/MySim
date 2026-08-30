# tools/ue5harness — UE5 闭环 harness

## 组件

- `route_executor.py` — route 执行器：解析路线 XML、spawn ego、同步模式运行、TM autopilot / socket agent 控制、tick 原始记录采集。
- `t24_run_trivial.py` — trivial agent 批量运行脚本（60 route-runs，崩溃自动重启 + 断点续跑）。
- `t26_inject_violations.py` — T2.6 违章注入测试脚本。
- `test_scoring_core.py` — scoring_core 单元测试。
- `scoring_core.py` — DS/SR 核心判定纯函数模块（不依赖 CARLA API）。
- `scoring.py` — UE5 侧适配层：消费 route_executor 的 tick 记录，调用 scoring_core 计算 DS/SR。
- `scoring_ue4_adapter.py` — UE4 侧适配层：消费 leaderboard 运行的 tick 原始记录，独立重判重算 DS（T2.6 对拍用）。

## Agent Socket 协议（v0.1）

- 传输：JSON over TCP，harness 为 server（默认 127.0.0.1:5555），agent 为 client。
- 每 tick harness 发送：

```json
{
  "tick": 1,
  "speed": 3.14,
  "target_points": [[x1, y1], [x2, y2]],
  "timestamp": 1234567890.123
}
```

- agent 回复：

```json
{"throttle": 0.5, "brake": 0.0, "steer": 0.1}
```

- 心跳：harness 每 100 tick 发送 `{"heartbeat": true}`，agent 回复 `{"alive": true}`。
- 超时：单步推理超时 2s，连续 3 次超时 fail-fast。
- 故障注入：启动 route_executor 时不连 agent，60s 后回退 TM autopilot；或 agent 故意不回复验证超时链。

## 运行 trivial agent（TM autopilot）

单条路线冒烟：

```bash
PYTHONPATH=/home/xsl/MySim/tools conda run -n mysim-ue5 python tools/ue5harness/route_executor.py \
  --routes data/routes/ue5_aligned_routes.xml \
  --route-id 10000 \
  --out logs/t21-smoke \
  --dt 0.05
```

60 route-runs 批量无人值守：

```bash
PYTHONPATH=/home/xsl/MySim/tools conda run -n mysim-ue5 python tools/ue5harness/t24_run_trivial.py \
  --routes data/routes/ue5_aligned_routes.xml \
  --out logs/t24-trivial \
  --max-game-time 120
```

评分汇总：

```bash
PYTHONPATH=/home/xsl/MySim/tools conda run -n mysim-ue5 python tools/ue5harness/scoring.py \
  --dir logs/t24-trivial/seed_0 \
  --out logs/t24-trivial/seed_0/scores.json
```

单元测试：

```bash
PYTHONPATH=/home/xsl/MySim/tools conda run -n mysim-ue5 python tools/ue5harness/test_scoring_core.py
```

## 同源性说明

`scoring_core.py` 是两侧唯一事实源；UE5 侧 `scoring.py` 与 UE4 侧 `scoring_ue4_adapter.py` 均调用同一核心模块。T2.6 在 UE4 侧用官方 leaderboard 与 scoring_core 对拍，验证通过后结论可传递至 UE5 侧。
