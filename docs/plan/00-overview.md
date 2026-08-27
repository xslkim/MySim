# 00 — 总体架构:多 agent 全自动开发方案

> 版本 v5(终稿)· 2026-08-27 · 第 5 轮(依据 `docs/plan/_reviews/round-4.md` 修订)
> v5 变更:新增执行摘要(用户拍板用);CP3 增"MDE vs 预期效应"显式决策项 + stretch 扩容预算分支(R4-N1);T3.0 初步 MDE 前移回填(R4-N1);KID-vs-ΔDS 相关性分析与 limitation 条款化(R4-N2);T4.5 选优规则终稿(R4-N3);T2.2/T2.6 tick 记录字段清单与核心模块同源性(R4-N4);T4.0 增量模式判据(R4-N5)。
> 范围:MySim 项目 M0–M5 的多 agent 编排。执行细节见 `01-infra.md`(基建)、`02-execution.md`(任务卡)、`03-risks.md`(风险)。

---

## 0. 执行摘要(一页,给用户拍板)

**做什么**:在本机(RTX 5090 / Win11+WSL2)回答一个研究问题——**UE5 渲染保真度对端到端自动驾驶模型是帮助还是伤害?微调能回收多少?** 方法:SimLingo(CVPR'25,纯视觉 1B)主模型 + AutoMoT(ICML'26)第二模型,UE4(CARLA 0.9.15,Bench2Drive)做基线,UE5(CARLA 0.10,闭环基建全部自建)做实现侧;三档对比 {UE4 对齐基线 / UE5 zero-shot / UE5 微调} + 成对渲染域差距(KID)。

**怎么跑(多 agent 全自动)**:主会话 orchestrator 以 goal 模式推进里程碑,长任务(130GB 下载、采数、训练、评测)全部后台 worker 执行;状态全部落 `state/` 文件(原子 GPU 锁 + 心跳 + 任务卡),任何新 agent 按固定协议接管;server 崩溃/模型服务崩溃/训练中断全部自动恢复。**人类只在 6 个 checkpoint 出现**:

| CP | 拍板内容 |
|---|---|
| CP0 | 环境登记确认(含宿主 RAM 量化门禁)——约第 2–3 天 |
| CP1 | UE4 基线分数核对(对照官方)——约第 2 周 |
| CP2 | UE5 自建闭环基建验收(含评分公式双实现交叉验证)——约第 2–3 周 |
| CP3 | **最关键决策点**:审域差距/zero-shot 掉分/MDE 检验力,签采数规模与是否扩容路线集——约第 3–4 周 |
| CP4 | 自采数据质检 + 微调方式(全量/LoRA)——约第 4–5 周 |
| CP5 | 终审对比报告(含 limitation 与 LiDAR 稀释声明)——约第 5–8 周 |

**资源账**:GPU 串行 101–214h(CP3 扩容分支另 +15–35h);磁盘已分配 ~372GB / 585GB(峰值 ~502GB 闭合);日历总量 **5–8 周**,关键路径 M0 → M2 → M3 → M4 → M5。

**结论强度边界(事先说清,CP5 验收口径)**:本设计产出的是**受控对齐条件下的存在性案例证据**——"UE4→UE5 迁移对 SimLingo 闭环 DS 产生 X ± CI 的影响,渲染域差距(KID)客观存在且与掉分[有/无]相关性"。**已知边界**:单一 Town10、锁白天、纯驾驶路线(无场景触发器)、主模型单一个(AutoMoT 大概率 N/A 或附 LiDAR 稀释声明)、专家为 TM autopilot、微调数据 ≈ 官方 9%;渲染/物理(PhysX→Chaos)/地图重制为复合差异,渲染归因只有相关性层面的间接证据。**不支持**"高保真渲染普遍提升/损害 E2E"的一般性结论。若 MDE 检验力不足,结论降级为"在检验力 X 下未观察到显著差异"——CP3 是最后一个治理点。

---

## 1. 设计原则

1. **单机单卡是硬约束**:5090 32GB 同供 CARLA 渲染与训练/推理,GPU 任务经统一原子锁串行化(`01-infra.md` §4)。
2. **训练与仿真器解耦**(调研 §8.3):模型/训练管线复用 SimLingo 官方(经 T1.0 移植),自建仅 0.10 侧采数与闭环评测。
3. **状态即文件**:全部经 `state/` 交接;orchestrator 每轮从任务卡**重建**状态,不信任增量。
4. **人类只在 checkpoint 出现**:CP0–CP5(§0/§6);BLOCKED 按升级路径处理,不擅自扩大动作范围。
5. **Windows 侧动作单列**:写入 `state/windows-actions.md`,能走 `powershell.exe` interop 的自动走。
6. **变量控制前置到任务卡**:跨仿真器对比只在"对齐路线集 + 同一评分公式(T2.6 验证)+ 同一 dt + 同交通配置"上进行;Bench2Drive 220 全量只做 M1 sanity,不进对比表。
7. **训练侧无人值守三件套**:logging 本地落盘(N4)、中断可恢复(N3)、选模只用离线 val(N5)。
8. **结论强度治理前置**(v5):MDE 在 CP3 显式对账并联动扩容预案(R4-N1);渲染归因以 KID-vs-ΔDS 相关性为间接证据,limitation 条款化进报告模板(R4-N2)。

## 2. Agent 角色拓扑

角色是"职能",不是常驻进程;每个 worker = 一张任务卡 + 一段后台执行。

```
                ┌─────────────────────────────┐
                │  Orchestrator(主会话,goal 模式)│
                │  派发任务卡 / GPU 锁仲裁 /      │
                │  重建 STATUS.md / CP 处等人     │
                └──────────────┬──────────────┘
        ┌──────────┬───────────┼───────────┬──────────────┐
        ▼          ▼           ▼           ▼              ▼
   env-agent   eval-agent  datagen-agent train-agent  analysis-agent
   (M0 装机/   (UE4/UE5   (0.10 采数,   (M4 微调,    (KID/MDE/
    冒烟登记)   闭环评测)    经 T4.0 转换) 类 A 独占)   相关性/报告)
        └──────────┴───────────┴───────────┴──────────────┘
```

- **Orchestrator**:主会话,goal 模式逐里程碑推进;不亲自跑长任务。
- **env-agent**(M0 为主):server 安装/启动脚本化、conda 环境(按模型分)、冒烟、登记。
- **eval-agent**:UE4 侧(官方 vendored leaderboard)+ UE5 侧(自建 harness);评测内置崩溃重启 + 断点续跑 + 同步模式 + 模型服务监管。
- **datagen-agent**:0.10 采数,产出经 T4.0 转换器对齐 SimLingo 格式。
- **train-agent**:M4 微调,GPU 独占;早停/选模只看离线 val;闭环选优在训练后(T4.5);中断按 resume 协议拉起。
- **analysis-agent**:成对渲染数据集、KID、MDE 估算、**KID-vs-ΔDS 相关性(R4-N2)**、汇总报告。
- **review-agent**(方案层面):每轮挑刺,orchestrator 据以修订版本。

## 3. 任务 DAG(依赖与并行流)

```
M0 环境验证 ── CP0
   ├────────────────────┐
   ▼                    ▼
M1 UE4 基线          M2 UE5 闭环基建(T2.1→T2.2→T2.3→T2.4→T2.6 交叉验证)
(T1.0 移植→T1.1→T1.2/T1.3)        │
   └─────────┬──────────┘
             ▼
        CP1 + CP2
             ▼
M3: T3.0 UE4 对齐基线(+初步 MDE 前移回填)──┐
    T3.1/T3.2 成对渲染 + KID(并行)         │
    T3.3/T3.4 UE5 zero-shot(同口径)◀───────┘
    T3.5 汇总:MDE 终版 + KID-vs-ΔDS 相关性(初版)
             ▼
   CP3(含"MDE vs 预期效应"决策项 + 扩容分支签批)
             ▼
M4: T4.1 冒烟 → T4.0 转换器+dataloader 门禁 → T4.2 全量采数
    → CP4 → T4.4 微调(类 A 独占,resume 协议,本地 logging)
    → T4.5 闭环评测(val 最佳默认进全量,R4-N3 规则)
             ▼
M5 报告(含 limitation 固定节)→ CP5
```

并行规则:M1 ∥ M2 主并行轴;M3/M4 内各卡经 GPU 锁串行;MindDrive 旁支挂 M1,timebox 2 天可砍;同一时刻最多一个 GPU 类任务(A/B/C),D 类不限。

## 4. 状态与交接机制(文件约定)

```
state/
  STATUS.md            # 全局快照 —— 每轮 goal 循环从任务卡强制重建
  orchestrator-cursor.md # orchestrator 游标:当前里程碑、在飞任务、等待中的 CP/锁
  gpu.lock.d/          # mkdir 原子锁,holder.json 含 heartbeat(5min 续,15min stale)
  gpu-queue.md         # GPU 排队(CP 任务可插队)
  env-registry.md      # 路径/端口/conda env/实测帧率显存 RAM;CP 时合入 AGENTS.md
  windows-actions.md   # 待宿主执行动作队列
  tasks/T<x.y>.md      # 任务卡:status、gpu_class、依赖、progress
experiments/
  EXP-<id>/            # config.yaml + metrics.json + notes.md;训练类加 train_metrics.jsonl
logs/<task-id>.log     # 崩溃现场不覆盖,追加 .1 .2
```

**并发与心跳**:取锁 = `mkdir state/gpu.lock.d`;stale 按心跳判(pid 二次确认)。长任务每路线/epoch 回写 `progress`。`STATUS.md`/`orchestrator-cursor.md` 由 orchestrator 独占写;worker 只写自己的任务卡与 `experiments/`。

**接管协议**(任务卡头部):1. `AGENTS.md` → 2. `STATUS.md` + cursor → 3. 任务卡(含 progress)→ 4. 输入文件/上游 EXP → 5. status=running → 6. 执行(心跳)→ 7. 结果块 + done/blocked。

**BLOCKED 升级**:worker 重试 → 失败写"事实+已试+建议" → orchestrator 判定:(a) 改派替代卡;(b) 触及关键决策/资源硬约束 → 挂起该流,提前人工确认。

**实验记录**:产生指标必建 `EXP-<id>/`;config.yaml 必含 `dt`/`sync_mode`/交通配置;对比实验须能证明变量控制;`EXP-id` 由 orchestrator 统一分配。

## 5. 长任务与后台纪律

- 下载、全量评测、对齐路线集评测、采数、训练:一律后台,主会话只轮询状态文件。
- GPU 任务先取锁,结束/崩溃必释放(stale 按心跳回收)。
- 评测/采数:`--resume-from`,单路线重试 ≤3 次;模型服务崩溃 → watchdog 重启续跑。
- **训练中断恢复(N3)**:ckpt 含完整训练态;中断自动从最近 resume ckpt 拉起;损失上限 = ckpt 间隔(≤0.5 epoch 或 2h);OOM 降档从最近 ckpt 重启记 notes(禁热切换)。详见 T4.4。

## 6. 人类 checkpoint 清单(v5 终稿)

| CP | 时机 | 人类要做什么 | 放行判据(量化) |
|---|---|---|---|
| CP0 | M0 末 | 确认 env-registry 合入 AGENTS.md;执行 windows-actions | 双冒烟达成;登记含盘位/vhdx、实测 FPS/显存/RAM、同步跟随结论、API 探测报告;**RAM 门禁:stress-ng 压 WSL 至 28–32GB + UE5 server 运行态下宿主空闲 ≥6GB,不满足降 28GB 重测;告警线 = 实测稳态 −2GB** |
| CP1 | M1 末 | 核对本地 vs 官方分数 | Bench2Drive v0.0.3 钉死;SimLingo 参考 85.07±0.95/67.27±2.11(论文 Table 2,3 seeds);AutoMoT 参考 87.34(README)/89.42(HF 卡);本地 ±3 DS 内或解释 |
| CP2 | M2 末 | 看 trivial 全程日志 + DS/SR + **T2.6 交叉验证报告** | 全路线集自动跑通;评分无 NaN/缺项;同步模式生效;**T2.6:无违章路线双侧一致 + 违章注入跑(同一 tick 原始记录,双实现独立重判)逐分项完全一致,路线级 mean \|ΔDS\| < 0.5** |
| CP3 | M3 末 | 审域差距/掉分/MDE;**签采数档位 + 扩容决策** | ① KID:跨侧显著大于同侧内部(bootstrap 95% CI 不重叠);② DS 中位掉落 > 双侧重跑噪声,配对 bootstrap 95% CI 下界 > 0;③ 方向 sanity:HiDrive 已在 UE5 观察到 SimLingo 明显掉分(口径不同仅定性)——掉落≈0 先查实验错误;④ **MDE vs 预期效应对账(R4-N1):MDE ≤ 5 DS 或 ≤ 观测掉落 → 维持 20×3;MDE > 5 DS 且吃掉观测掉落 → 触发扩容分支(seeds 3→5 零设计成本,或 stretch 50 条路线集,+15–35h GPU,与 T2.3 stretch 联动);zero-shot 掉分 <MDE 时的报告口径与微调回收同标准("不显著"分支)**;⑤ 采数档位 + 磁盘签字 |
| CP4 | M4 中 | 抽看自采数据;定全量 vs LoRA | 质检通过(坏帧率 <1%、字段清单全覆盖、T4.0 实读已过);训练方式落笔 |
| CP5 | M5 末 | 终审对比报告 | 三档 DS/SR 齐全可溯;AutoMoT LiDAR 声明(或 N/A)正确;回收对照 MDE 下结论;ckpt 选择规则(R4-N3)可溯;**limitation 固定节存在(渲染/物理/地图混杂不可分、相关性仅间接归因、外推限缩本对齐路线集,R4-N2)**;0.10 固有限制注明 |

任何 checkpoint 不通过 → 回对应里程碑生成修复卡,不跳级。

## 7. 总时长与关键路径(v5)

- **关键路径**:M0 → M2 → M3 → M4 → M5;T1.0 是 T3.3/T4.4 隐性上游;T4.0 是 T4.2 门禁。
- **GPU 串行墙钟**(与 `02-execution.md` 附录同源):基准 **101–214h**(T1.2 8–18 + T1.3 10–20 + T2.4 4–10 + T2.6 2–4 + T3.0 8–14 + T3.1/T3.2 ~6 + T3.3 6–14 + T3.4 8–16 + T4.2 24–28 + T4.4 15–60 + T4.5 12–28);**CP3 扩容分支另 +15–35h**(仅触发时计入,R4-N1)。
- **日历总量 5–8 周**;全局超支条款:任一里程碑超预算 30% → 挂起该流人工重估(砍 scope 顺序:MindDrive → M4 采数降档 → AutoMoT UE5 降级 → 路线集收缩)。

## 8. 不在本方案内(明确排除)

- 不实现代码、不改环境、不下载数据(本轮纪律)。
- 不做世界模型/RL 专家;不承诺 0.9→0.10 迁移;UE5 侧基建按自建估。
- Bench2Drive 220 分数不进对比表;对齐路线集不对标 Bench2Drive 难度。
- 训练中不做中途闭环评测(类 A 互斥);闭环选优统一在训练后。
- 不声称渲染的一般性结论(边界见 §0 执行摘要,CP5 以此验收)。
