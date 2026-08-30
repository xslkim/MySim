# CP1 报告 — M1 UE4 基线复现收口(2026-08-30)

> 判据来源:`docs/plan/00-overview.md` §6 CP1 行。过程记录:`docs/log/2026-08-2{8,9,30}.md`。任务卡:`state/tasks/T1.*.md`。

## 1. CP1 判据逐项核对

| 判据项 | 结果 | 判定 |
|---|---|---|
| Bench2Drive v0.0.3 钉死 | 仓 README L141 "V0.0.3(Currently in use)",基 commit `2645714`(本地补丁 `c82e5b8` 仅接线/子集,不动评分语义);两侧(SimLingo 用 external/bench2drive、AutoMoT 用 vendored)220 xml diff IDENTICAL 已核 | ✓ |
| SimLingo 对官方 85.07±0.95 / SR 67.27±2.11(±3 内或解释) | **DS=86.18 / SR=68.2%**(220 全量) | ✓ 双带内 |
| AutoMoT 对官方 87.34(README)/89.42(HF 卡)(±3 内或解释) | **DS=89.17**(56 路线分层 1/4 子集,town 等比;D16 用户拍板先打通流程) | ✓ 对两个参考均在 ±3 内(子集口径,见 §4 声明) |
| 解释项 | 见 §3(AutoMoT v1 事故与修复)、§5(失败路线归因)、§4(口径与声明) | ✓ |

**CP1 结论:PASS。M1(UE4 基线复现)收口。**

## 2. 分数明细与证据路径

### SimLingo(主模型,220 全量,FASTPATH 数值路径)

- **DS=86.18 / RC=96.94 / pen=0.886 / SR(DS=100)=68.2% / Completed 207/220**
- 产物:`logs/t12-220-halfA|halfB/result.json`;合并 `state/tasks/T1.2-220-merged.json`(logs 副本 `logs/t12-220-merged.json`)
- 提速与并发:FASTPATH(kv-cache+LoRA merge,eval-only)经 split20 DS 闸(94.39 vs orig 92.54 不降)采纳,wall 2.24×;双实例并发再 ~1.45×;净耗时 ~22.5h
- 任务卡:`state/tasks/T1.2.md` 阶段 B;提速与 A/B 全链:`state/tasks/T1.2b-profile.md` + T1.2b-*.json

### AutoMoT(第二模型,56 路线分层子集)

- **DS=89.17 / RC=98.89 / pen=0.898 / SR(满分率)=73.2% / Completed 54/56**
- 产物:`logs/t13-full220/result.json`(注:目录名沿用,实为 quarter56 子集 `external/AutoMoT/leaderboard/data/bench2drive_quarter56.xml`,`tools/t13_select_quarter56.py`)
- 失败 2 条:2091 TickRuntime(DS=24.8)、23930 AgentBlocked(DS=29.3)
- 接线/冒烟/诊断/修复:`state/tasks/T1.3.md`;关键发现:双专家 5.6B 推理 0.32–0.43s/帧 ≈ SimLingo FASTPATH,显存峰 19.5GB/侧(单实例约束)

### 基建与其他模型

- T1.0 训练栈:SimLingo bs=6 峰值 19.6GiB,32GB 全量微调可行;flash-attn 2.8.3 在 sm_120 实测通过
- T1.1 接线:B2D_EXTERNAL_SERVER 补丁链 + 三坑修复(`state/tasks/T1.1.md`)
- T1.4 MindDrive:CPU+GPU 段 PORTED(GPU 前向 0.34s/帧、14.62GiB),闭环接线/RL 链 open(第三模型,后续里程碑再用)

## 3. AutoMoT v1 低分事故(解释项)

v1 18 路线 meanDS=27.5 系**官方 release ckpt 与代码跨代际改名**(`transfuser_proj.*`→`bev_encoder_proj.*`)致唯一投影层随机初始化,BEV token 全垃圾。修复(`_CKPT_KEY_RENAMES`)后冒烟 DS 25/59/13→全 100,v2 全量(子集)89.17 正常。作废数据归档 `logs/t13-full220-broken-bev*` 作修复前后对照证据。坑录:T1.3(2026-08-30)。

## 4. 口径与声明(CP5 终审需继承)

1. **SimLingo 评测数值路径与官方有 bf16 级差异**(FASTPATH kv-cache+merge 非 bit 等价,DS 闸验证不降分;行为扰动混沌但双侧同路径,UE4/UE5 对比可控)。对外引绝对 DS 须声明
2. **AutoMoT 动作分支含 LiDAR**(BEV 输入),渲染结论须注明 LiDAR 稀释;本次根因修复恰证明其 LiDAR/BEV 依赖之重(一层投影坏即全毁)
3. **AutoMoT 分数为 56 路线分层子集口径**(town 等比、官方序),非 220 全量;需要时同目录换 220 xml `--resume` 续跑补齐(v2 已跑的与 220 重叠 2 条会保留,15 条被子集化丢弃需重跑)
4. AutoMoT MinSpeedTest FAILURE 为模型固有谨慎驾驶特征(修复前后一致),不进 DS 罚分乘积
5. SR 口径:官方 SR 未直接产出,按满分(DS=100)路线占比计(SimLingo 68.2% vs 67.27±2.11、AutoMoT 73.2% 均带内,口径推断获数值佐证)

## 5. SimLingo 220 失败路线归因(静态分析)

13 条非 Completed(全清单 `state/tasks/T1.2-220-merged.json`):

- **TickRuntime×9**(路线预算耗尽):静止/慢速障碍规避类主导——AccidentTwoWays×3(3410/25845/25857)、ConstructionObstacleTwoWays(1825)、StaticCutIn(25358)、ParkingExit(26393)、MergerIntoSlowTrafficV2(26408)、SignalizedJunctionLeftTurn(4468)、ParkingCrossingPedestrian(24294)
- **AgentBlocked×2**(23670 HighwayExit、23918 InterurbanActorFlow)、**Deviated×2**(23658/24098,均高速/车流场景)
- **模式结论:SimLingo 弱于绕行静止/慢速障碍**——遇事故车/施工障碍倾向停车等待,stuck 恢复机制(creep)在 200s 预算内不足以完成绕行,与 25845 的逐帧分析(物理卡死+force_move 无效)一致。镇分布与路线集构成一致(Town12/13 占 75%),无城镇偏科
- 建议(M3 对照用):UE5 zero-shot 侧同路线集复跑时,这 13 条是域差距的敏感探针,优先逐条对照

## 6. M1 遗留与 M2 移交

- UE4 侧双 server 基建(2031/2041)+ 容错链(harness 自愈 + ensure_server + 停滞看门狗)实战验证 6 起事故零成绩损失,M2 UE5 侧直接复用范式
- mysim-minddrive env 保留(闭环接线待办 open)
- 13 条失败路线 viz 在 `logs/t12-220-half*/viz/` 供人工抽看
- 下一里程碑:M2 UE5 自建闭环基建(T2.x,CP2 判据:全路线集自动跑通 + T2.6 评分双实现交叉验证 mean |ΔDS|<0.5)
