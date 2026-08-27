# 开发路线图(多 agent 长周期开发)

> v3(2026-08-27):需求聚焦——**UE4 成熟模型(SimLingo)→ UE5 实现 → UE4/UE5 对比,核心关注渲染保真度**。
> 双仿真器:0.9.15(UE4,基线)+ 0.10(UE5,实现),server 均 Windows 原生(落位 `C:\carla\`),Python 均在 WSL2。
> 每个里程碑有明确完成判据,适合用 goal 模式逐段推进。
> **执行细节(任务卡/资源调度/统计口径)与人工门禁(CP0–CP5)以 `docs/plan/` v5 为准**;环境勘误见 `docs/04-doc-review.md`。

## M0 环境验证(一切的前提)

- Windows 原生安装两个 server 到 `C:\carla\`:CARLA 0.10.0 zip(~130GB)+ 0.9.15 包(~30GB,含 Town10)。
- WSL2 建客户端环境(拓扑以 plan 01-infra §3 为准:UE5 客户端 py3.11 + `carla-ue5-api==0.10.0`;模型/UE4 侧 py3.10 + `carla==0.9.15`),经**宿主 IP(脚本动态获取,禁硬编码 localhost)**连通 :2000(UE5)/ :2010(UE4,端口错开)。
- 验证:两侧各 spawn 车辆 + RGB 相机取帧 + autopilot 5 分钟不崩;记录两侧帧率。
- 基建:`.wslconfig` **降档 56→32GB**(processors 16→14、swap 32→16GB;闭合算术见 plan 01-infra §4.3);防火墙放行;路径/端口登记 AGENTS.md;CP0 冒烟含"远程会话断开后 server 存活"项。
- 完成判据:UE4、UE5 两侧客户端脚本均能 spawn + 取相机帧 + autopilot 5 分钟无崩溃。

## M1 UE4 基线复现(成熟侧)

- 装 Bench2Drive + SimLingo;用 SimLingo **官方权重**在 Bench2Drive 上评测,对齐官方分数(DS ~85)。
- 同环境跑 **AutoMoT 官方权重**评测(仓内自带 leaderboard harness),对齐 DS ~87。
- 目的:确认 UE4 侧全链路可信,产出两模型的基线 DS/SR。
- 完成判据:本地评测分数落在官方分数合理误差内。

## M2 UE5 闭环基建(本项目核心工作量)

- Route 执行器 + DS/SR 评分(违章项参照 Bench2Drive;指标设计参照 HiDrive UE5 先例);场景用 Scenic 3 或裸 API。
- 路线设计与 UE4 侧对齐:Town10 在两侧都有(0.10 为重制版),设计可对照的路线集(≥20 条,训练/验证分离)。
- 完成判据:trivial agent(autopilot)无人值守跑完全部路线并输出 DS/SR,含崩溃自动重启。

## M3 渲染对比与 zero-shot 迁移实验(核心实验一)

- **渲染对比**:在两侧 Town10 布置对齐的相机位姿,成对采集画面;计算图像域差距指标(FID / 感知相似度),定性对比光照/材质/反射差异。
- **zero-shot**:SimLingo 与 AutoMoT 官方权重(UE4 数据训练)分别在 UE5 闭环评测 → 量化"渲染升级带来的域差距";两模型对照(AutoMoT 含 LiDAR,其 DS 变化预期更小,本身就是渲染敏感度的对照组)。
- 完成判据:成对渲染数据集 + 域差距指标报告;两模型 zero-shot DS/SR。

## M4 UE5 数据与微调(核心实验二)

- 0.10 侧专家采数(先 TM autopilot 冒烟,设计向 LEAD 对齐),数据格式对齐 SimLingo 训练代码。
- 在 0.10 数据上**微调** SimLingo(单卡 5090),出 UE5 适配版权重。
- 完成判据:微调后 UE5 闭环 DS/SR 相比 zero-shot 的提升幅度(对照 MDE 下结论,口径见 plan)。

## M5 综合对比与报告

- 对比矩阵:UE4基线 / UE5-zero-shot / UE5-微调 三档 DS/SR + 渲染域差距指标,控制变量(同架构、同路线设计、同指标)。
- 回答问题:UE5 渲染保真度对 E2E 模型是帮助还是伤害?微调能回收多少?
- 完成判据:可重复的对比实验报告(数据版本/模型版本/分数齐全)。

## 0.10 固有限制(全程伴随,实验结论须注明)

- 仅 Town10(重制版);天气锁死白天;~25 FPS(采数/评测慢,后台任务);车辆 11 款。
- UE4/UE5 的 Town10 布局有血缘但非逐像素对齐,成对渲染对比以"语义对齐"为度。

## 多 agent 协作约定

- 每个 M 拆独立任务用 goal 模式推进;长时任务(下载、采数、训练、评测)放后台 agent。
- 环境事实、坑、路径/端口全部记录到 AGENTS.md,新 agent 进项目先读它。
- 对比实验严守变量控制(AGENTS.md 硬性规则 #4)。
