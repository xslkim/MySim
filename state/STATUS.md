# STATUS.md — 全局快照(由 orchestrator 每轮重建)

> 重建时间:2026-08-27 (M0 启动)

## 当前里程碑:M0 环境验证(目标 2–3 天)

## 任务卡状态
| 卡 | 状态 | 备注 |
|---|---|---|
| T0.1 基座准备 | running | orchestrator 直接执行(轻量) |
| T0.2 下载 0.10.0 | pending→running | 后台下载任务(BunnyCDN 直链,10.2GB) |
| T0.3 下载 0.9.15+AdditionalMaps | pending→running | 同一下载任务内顺序执行(7.8+7.2GB) |
| T0.4 三 conda 环境 | pending→running | env-agent 后台 |
| T0.5 UE5 冒烟+探测 | blocked | 依赖 T0.2/T0.4 |
| T0.6 UE4 冒烟 | blocked | 依赖 T0.3/T0.4,与 T0.5 经锁串行 |
| T0.7 登记+CP0 | blocked | 依赖全部 |

## 在飞后台任务
(登记任务 id 与日志路径)

## GPU 锁
空闲。锁约定:`state/gpu.lock.d`(mkdir 原子),holder.json 含心跳(5min 续/15min stale)。

## 待人工
见 `state/windows-actions.md`(`.wslconfig` 降档落盘 + 防火墙放行,均 CP0 前置)。

## 预警
- 初步 MDE:未回填(T3.0 产出)。
- 磁盘:WSL vhdx 在 G: 盘(与 C: 不同盘,无同盘 I/O 竞争,04-review §6.3 坑排除)。
