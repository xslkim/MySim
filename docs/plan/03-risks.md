# 03 — 风险登记册

> 版本 v5(终稿)· 2026-08-27 · 第 5 轮(依据 `docs/plan/_reviews/round-4.md` 修订)
> v5 变更:R8 显著性口径扩到 zero-shot 对比(R4-N1);新增 R16(检验力不足/MDE 治理,R4-N1)与 R17(渲染归因混杂,R4-N2)——终局推演的两大结论强度威胁条款化;联动表更新。编号跨轮次稳定。
> 每条:概率 / 影响 / 早期信号 / 自动缓解 / 兜底人工。

## R1 WSL2 ↔ Windows 网络链路(部署形态根基)

- 概率:中 | 影响:高
- 说明:server 在 Windows 原生,Vulkan 风险已绕开;残余:WSL→Windows 方向须用宿主 IP(NAT 的 localhost 转发只有 Windows→WSL 默认开,[Microsoft 文档](https://learn.microsoft.com/en-us/windows/wsl/networking))。
- 早期信号:T0.1 宿主 IP 脚本失败;T0.5 连接超时/间歇断开。
- 自动缓解:动态取宿主 IP 禁硬编码;mirrored 备选(命令在 windows-actions 模板,CP0 人定);watchdog 断连重连。
- 兜底人工:mirrored/防火墙;终极退路双系统 Ubuntu,须用户确认。

## R2 RTX 5090(sm_120)编译兼容性(仅算子/编译层)

- 概率:中 | 影响:中
- 说明:torch≥2.7+cu128 硬要求;flash-attn 2.8.x 对 sm_120+WSL2 有失败记录([flash-attention#2168](https://github.com/Dao-AILab/flash-attention/issues/2168))。
- 早期信号:T0.4/T1.0 编译报错、`get_device_capability()` 非 `(12,0)`。
- 自动缓解:**T1.0 第一步 flash-attn 冒烟**,失败立即 `sdpa` 回退记坑;训练先 30 步冒烟再长跑。
- 兜底人工:钉替代算子组合;极端回退形态 (a),须用户确认。

## R3 MindDrive-3B 移植失败(可选旁支)

- 概率:高 | 影响:低
- 说明:官方栈 py3.8+torch2.4.1+魔改 mmcv,5090 必须移植;env 归属临时 `mysim-minddrive`。
- 早期信号:T1.4 中 mmcv 算子无 wheel、自编译失败。
- 自动缓解:**timebox 2 天**,超时即砍;降级:只保 0.5B 或仅 UE4 基线;归档后删临时 env。
- 兜底人工:无(可砍项)。

## R4 AutoMoT 许可与使用边界

- 概率:中(已成事实)| 影响:低
- 说明:HF 权重 Apache-2.0,GitHub 仓无 LICENSE——只作学术对照。
- 早期信号:M5/对外材料引用其代码时。
- 自动缓解:只引用 commit 散列与官方分数,代码不拷入本仓。
- 兜底人工:公开复现材料的引用方式由用户确认。

## R5 磁盘耗尽(585GB 硬预算)

- 概率:中 | 影响:高
- 说明:瞬态峰值口径:已分配 ~372 + 0.10 zip ≤130 ≈ **502GB 峰值**,仍在 585 内但吃掉大半缓冲;计划外数据集是最大变量;盘位(vhdx 位置)未验证。
- 早期信号:T0.1 盘位登记错配;`df` ≥80%。
- 自动缓解:任务前置预算检查;Windows 侧下载解压、即解压即删 zip;80% 告警/90% 硬停并生成清理卡(禁清 EXP);不下载清单。
- 兜底人工:vhdx 迁移(CP0);追加存储或砍数据规模(M4 降档)。

## R6 CARLA 崩溃常态化(两侧皆是)

- 概率:高(设计预期内)| 影响:中
- 说明:0.10 有 #9439/#9409 记录;长评测/采数必然撞崩。
- 早期信号:watchdog 重启 >1 次/10 路线;同一路线反复崩。
- 自动缓解:自动重启 + `--resume-from`;单路线 3 败跳过;崩溃率超阈值降 quality-level(config 留痕);禁 `-RenderOffScreen`;模型服务监管见 R14;**训练中断损失上限 = ckpt 间隔(≤0.5 epoch 或 2h,T4.4 协议)**。
- 兜底人工:特定路线持续致崩 → 人审剔除(留痕)。

## R7 CARLA 0.10 API 缺失(基建天花板)

- 概率:中 | 影响:高
- 说明:ScenarioRunner/Leaderboard 不兼容;传感器有黑屏 bug;**LiDAR 未证实**(T3.4 命门,且"可用"还须过参数对齐关);depth/seg 未证实(T4.1 依赖);无特权专家(M4 默认纯驾驶分支)。
- 早期信号:**T0.5 API 探测报告**(全传感器/交通灯标志/TM/天气/sync-dt)。
- 自动缓解:全部按"裸 API + 自建"兜底;LiDAR 缺失或不匹配 → T3.4 N/A(R12);depth/seg 缺失 → T4.1 前置核对调范围;HiDrive 为参照(学术研究免费)。
- 兜底人工:最低闭环残缺 → 挂起 M2,用户决策(必须人工)。

## R8 训练超时 / 微调收益不显著

- 概率:中 | 影响:高
- 说明:官方 14 epochs × 650k,8×A100 24h([论文 §4.2](https://arxiv.org/html/2503.09594v1)),单 A100 ≈ 47k 样本/h;5090 估 19–38k(30 步冒烟实测);M 档 × 2–4 epochs → 15–60h,48h 软顶。收益无严格先验(M 档 ≈ 官方 9%)。**显著性口径(v5 扩展):zero-shot 掉分与微调回收同标准——幅度 <MDE 只能报"在检验力 X 下未观察到显著差异"(R4-N1);MDE 治理见 R16。**选模规则:早停/候选只用离线 val;闭环选优在 T4.5(默认 val 最佳进全量,筛选仅 sanity,R4-N3)。
- 早期信号:冒烟吞吐推算超软顶;val loss 平台期早;T4.5 sanity 筛选各候选差异 <MDE。
- 自动缓解:每 ≤0.5 epoch 落 resume ckpt;超软顶早停;OOM 降 batch/LoRA(从最近 ckpt 重启);**不显著是有效结论**,禁止为凑显著性改口径。
- 兜底人工:CP4 定全量 vs LoRA;早停后用户决定是否追加采数(R5 博弈)。

## R9 显存顶格:B 类任务 32GB 边界

- 概率:中 | 影响:中
- 说明:官方建议 0.10 最低 16GB VRAM([0.10.0 发布页](https://carla.org/2024/12/19/release-0.10.0/));AutoMoT 13GB 叠加余量 ~3GB。观测以 `powershell.exe nvidia-smi.exe` 为准;同存实测两段法(M0 合成负载,T1.2/T3.4 真实模型)。
- 早期信号:T0.5 合成负载同存即顶格;T3.4 OOM/掉帧。
- 自动缓解:T3.4 降 server 分辨率/画质(config 留痕);取锁前 Windows 侧核查;实测回填修订预算。
- 兜底人工:Epic 无法同存 → 用户决策降画质或 AutoMoT 走 N/A。

## R10 Windows 宿主不可控因素(更新重启/杀进程/内存挤压)

- 概率:中 | 影响:中
- 说明:Update 重启、Defender、睡眠;窗口模式 server 依赖交互会话。宿主 RAM 最坏情形已由 §4.3 闭合(CP0 门禁含 stress-ng 压力注入;降档 28GB 预案;告警线 = 实测稳态 −2GB)。
- 早期信号:server 整批消失且非崩溃特征;宿主空闲内存趋势走低。
- 自动缓解:宿主检查清单;**恢复 runbook**:① 开机自启 server 任务计划(CP0 人装);② orchestrator 检测全灭 → 挂起队列 + 报警;③ 评测/采数断点续跑(损失 ≤1 条路线),训练按 resume 协议拉起(损失 ≤ ckpt 间隔)。
- 兜底人工:用户执行清单与任务计划安装(CP0/CP3 各确认一次)。

## R11 SimLingo 依赖钉死旧栈

- 概率:高(必然发生的工程量)| 影响:高
- 说明:官方锁 py3.8.18/torch2.2.0/flash-attn 2.7.0.post2/transformers 4.46.3([environment.yaml](https://raw.githubusercontent.com/RenzKa/simlingo/main/environment.yaml));torch 2.2 在 sm_120 无 kernel。可行锚点:AutoMoT 官方栈(py3.10+torch2.7.1+cu128+flash-attn 2.8.3,[requirements.txt](https://raw.githubusercontent.com/OscarHuangWind/AutoMoT/release/requirements.txt))。
- 早期信号:T1.0 中 InternVL2 remote code 报错、deepspeed/lightning API 不兼容。
- 自动缓解:**T1.0 独立任务卡(1–2 天)**,范围含 logging 离线化(wandb "Login is required" → offline/CSV-JSONL);第一步 flash-attn 冒烟;判据 = ckpt 加载干净 + 前向数值有限 + 单 batch 训练步无 OOM + train_metrics.jsonl 落盘;功能正确性由 T1.2 兜底;M4 env 随 T1.0 落定。
- 兜底人工:超 2 天未通 → 人工评估(极端换主模型——必须用户确认)。

## R12 AutoMoT LiDAR 稀释限制的流程化

- 概率:中 | 影响:低-中
- 说明:动作分支依赖 LiDAR BEV 特征([README](https://github.com/OscarHuangWind/AutoMoT));渲染敏感度被稀释(调研 §10.1)。
- 早期信号:T0.5 LiDAR 栏;T3.4 前置参数对齐检查。
- 自动缓解:不可用或参数不匹配 → N/A + M5 单模型分支;可用且匹配 → 结论强制附稀释声明;CP5 含声明检查。
- 兜底人工:无(流程闭环)。

## R13 Bench2Drive CC-BY-NC-ND 对产出的约束

- 概率:低 | 影响:低
- 说明:ND 禁止公开再分发修改后的路线/数据衍生品;内部实验无碍。
- 早期信号:M5/对外材料准备阶段。
- 自动缓解:产物默认内部使用;对外只报分数;T2.3 路线集声明自研。
- 兜底人工:对外发布前用户过许可清单。

## R14 socket 分离架构的双进程失败模式

- 概率:中 | 影响:中(无人值守"无声卡死")
- 说明:UE5 评测 = harness + 模型服务两进程;模型服务崩溃时同步模式 harness 永远等待(server 心跳仍正常)。
- 早期信号:progress 停更但无报错;推理心跳停更。
- 自动缓解:T2.1 socket 规范(payload 含 run_step 全输入、超时可配置、连续 N 次才 fail-fast、心跳、崩溃恢复)经故障注入演示;watchdog 双进程监管;T3.3/T3.4 前置崩溃注入测试;回退预案(py3.11 per-model env)。
- 兜底人工:注入测试反复失败 → 人工审协议,必要时切回退架构(提前升级)。

## R15 0.10 数据 → SimLingo 训练格式不兼容

- 概率:中 | 影响:高(无门禁则"采数+训练全部作废"的无人发现路径)
- 说明:SimLingo 按 data buckets 采样(自建数据需 `carla_get_buckets.py` 生成,[README](https://github.com/RenzKa/simlingo)/论文 §3.4);0.10 格式与 carla_garage 布局之间有转换器缺口。
- 早期信号:T4.0 的 dataloader 实读报错;bucket 脚本依赖 0.10 没有的字段;增量追加后索引错乱(R4-N5 判据)。
- 自动缓解:**T4.0 门禁承载**(转换器 + bucket 结论 + dataloader 实读 1 step + 增量幂等判据),排在 T4.2 之前;T4.2 边采边转;T4.4 只认 T4.0 验证过的管线。
- 兜底人工:T4.0 超 1.5 天未通 → 提前人工(不等 CP4):评估 bucket 绕过补丁或训练代码改造范围。

## R16 检验力不足:MDE 大于真实效应(R4-N1,终局推演威胁一)

- 概率:中(CARLA 闭环 DS 路线间方差大,20 路线配对样本小,MDE 达 5–10 DS 不意外)| 影响:高(核心命题只能报"不显著",且样本量在 M2 锁定)
- 说明:MDE 在 T3.5(M3 末)才首次可量化,而 eval 集规模在 T2.3 已定;v5 前的缺口:无条款规定"MDE 吃掉效应时怎么办"。
- 早期信号:**T3.0 初步 MDE(仅 UE4 侧噪声)前移回填 STATUS.md(R4-N1 前移)**——初步 MDE >5 DS 即预警,orchestrator 提前备扩容方案。
- 自动缓解(v5 条款):**CP3 ④ "MDE vs 预期效应"显式决策项**——MDE ≤5 DS 或 ≤ 观测掉落 → 维持 20×3;MDE >5 DS 且吃掉观测掉落 → 触发扩容分支:seeds 3→5(零设计成本)或 stretch 50 条路线集(T2.3 已备设计草案),预算 +15–35h GPU(已入求和附录);**zero-shot 掉分 <MDE 的报告口径与微调回收同标准**("在检验力 X 下未观察到显著差异",R8 已同步)。CP3 是最后一个治理点,过了 CP3 样本量锁死。
- 兜底人工:CP3 上用户三选一:扩容(批预算)/ 维持并接受弱结论 / 收缩命题(只报域差距 + 定性)。

## R17 渲染归因混杂:渲染+物理+地图复合体(R4-N2,终局推演威胁二)

- 概率:高(设计固有,不可消除)| 影响:中-高(决定结论措辞强度)
- 说明:UE4→UE5 迁移同时换物理引擎(PhysX→Chaos)与地图(Town10 重制,仅语义对齐)——DS 掉分在设计上**无法单独归因渲染**;不做处理则 M5 只能陈述"UE4 与 UE5 不同",与命题错位。
- 早期信号:T3.5 相关性分析结果弱/方向反(掉分大的场景组 KID 反而小 → 指向物理/几何因素)。
- 自动缓解(v5 条款):**KID-vs-ΔDS 相关性分析**——T3.1 采图带场景组标签;T3.2 出分组 KID(粒度对齐掉分表);T3.5 初版 + T5.1 终版:场景组级 Spearman 相关 + bootstrap CI(本设计内唯一的间接归因证据);**T5.2 报告模板 limitation 固定节**:显式声明复合混杂不可分、相关性仅为间接证据、外推限缩(完整五条见 T5.2);CP5 检查该节存在性。
- 兜底人工:无(归因边界是设计固有;用户能做的是接受该边界或在立项层改研究问题——触及关键决策,必须人工)。

---

## 风险—任务卡联动表(v5)

| 风险 | 主要暴露任务 | 早期信号产物 |
|---|---|---|
| R1 | T0.1/T0.5 | 宿主 IP 探测、连通性日志 |
| R2 | T0.4/T1.0/T4.4 | flash-attn 冒烟、30 步冒烟 |
| R3 | T1.4 | 移植日志(timebox 内) |
| R5 | T0.1/T0.2/T4.2 | 盘位登记、水位记录 |
| R6 | T1.2/T2.4/T4.2/T4.4 | watchdog 重启计数、训练 ckpt 间隔 |
| R7 | T0.5 → M2 全系 | **API 探测报告** |
| R8 | T4.4/T4.5 | 吞吐实测、val 曲线、MDE 对照 |
| R9 | T0.5/T1.2/T3.4 | 合成负载 + 真实同存两段实测 |
| R10 | 所有 GPU 长任务 | 宿主清单回执、runbook 演练、RAM 水位 |
| R11 | T1.0(承载)→ M1/M3/M4 | 移植记录、训练步冒烟、本地 logging 验证 |
| R12 | T0.5/T3.4/T5.1 | LiDAR 栏 + 参数对齐、CP5 检查项 |
| R13 | T2.3/T5.2 | 自研声明、对外材料审查 |
| R14 | T2.1/T3.3/T3.4 | socket 故障注入演示、推理心跳 |
| R15 | T4.0(承载)→ T4.2/T4.4 | dataloader 实读门禁、增量幂等判据 |
| R16 | T3.0(前移)/T3.5/CP3 | 初步 MDE 预警、MDE 对账结论 |
| R17 | T3.1/T3.2/T3.5/T5.1/T5.2 | 分组 KID、相关性分析、limitation 节 |
