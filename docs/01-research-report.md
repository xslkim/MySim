# 调研报告:UE5 端到端自动驾驶仿真技术选型

> 调研时间:2026-08-27 · 方式:4 个并行调研 agent(Web 检索官方文档/GitHub/论文)
> 目标:用 UE5 引擎做端到端(E2E)自动驾驶仿真,本机运行,基于成熟开源库(如 CARLA)

> **v2 更新(2026-08-27):用户确认 UE5 为硬性要求,主线改为 CARLA 0.10(UE5.5)+ 自建闭环评测基建;部署形态采用"Windows 原生 CARLA server + WSL2 训练/客户端"。详见 §8 补充调研;§0/§6 中"首选 0.9.15"为原始调研结论,保留备查。**

## 0. 结论摘要(TL;DR)

1. **仿真器选 CARLA 0.9.15(UE4 线),而不是 0.10(UE5 线)**。截至 2026-08,CARLA 0.10.0(UE5.5)仍是技术预览:只有 1 张城镇地图、天气锁死白天、~25 FPS、**ScenarioRunner/Leaderboard/Bench2Drive 全部不兼容**。E2E 闭环训练+评测的完整生态(2026 年的"最新方案"如 SimLingo、ORION、Bench2Drive)全部建立在 0.9.15 上。UE5 版作为后续迁移路径保留(见 §6)。
2. **最大环境风险是 WSL2**:CARLA 渲染依赖 Vulkan,WSL2 的 Vulkan 支持长期残缺(官方不支持)。项目第一件事必须是实测验证,备选方案见 §5。
3. **端到端方案首选 SimLingo**(CVPR'25 Highlight,CARLA Challenge 2024 冠军,Bench2Drive 驾驶分 85.94,权重/数据/代码全开,Apache-2.0);基线用 Bench2DriveZoo(UniAD/VAD/TCP 官方权重直接可评)。
   > 分数口径统一(2026-08-27):SimLingo 对比实验一律以**论文 Table 2(DS 85.07±0.95,3 seeds)**为准(plan T1.2/CP1 已钉此口径);本文 85.94/85.9/85.1 等均为 README/榜单转述口径,引用时以论文为准。
4. **RTX 5090(sm_120)是个坑**:需要 PyTorch ≥2.7 / CUDA ≥12.8,而 CARLA 0.9.15 客户端锁 Python 3.7/3.8 → **仿真环境和训练环境必须分开**(conda 多环境)。
   > 更正(2026-08-27):PyPI 实测 `carla==0.9.15` 另有 cp39/**cp310** wheel,可与 torch≥2.7 同居 py3.10 环境(AutoMoT 官方栈先例);环境拓扑以 `docs/plan/01-infra.md` §3 为准。§2.1 表同源错误一并更正。
5. 磁盘紧张:可用 585GB,而 Bench2Drive Base 数据集 ~400GB、carla_garage 数据集 364GB。初期只用 Mini(4GB)/Dev10 冒烟,大规模数据按需下载。

## 1. 本机环境

| 项 | 配置 | 评估 |
|---|---|---|
| GPU | RTX 5090 32GB(Blackwell, sm_120),驱动 577.00 / CUDA 12.9 | 算力远超需求;但 sm_120 要求 PyTorch ≥2.7,老仓库(torch 1.x/mmcv-full)跑不动 |
| CPU | Core Ultra 7 265K,16 核 | 够用 |
| 内存 | 54GB(WSL2 默认只分一半,需 `.wslconfig` 调大) | CARLA 大图 + 模型推理够用;UE 源码编译偏紧 |
| 磁盘 | 可用 585GB | 不足以同时放下全部数据集,需按需下载 |
| OS | Ubuntu 22.04,**WSL2 内核** | 最大风险点:CUDA 训练没问题,UE 渲染(Vulkan)不可靠 |

## 2. 仿真器调研:CARLA 0.9 vs 0.10

### 2.1 版本现状(2026-08 核实)

| | CARLA 0.9.x(UE 4.26) | CARLA 0.10.x(UE 5.5) |
|---|---|---|
| 最新版 | 0.9.16(2025-09) | 0.10.0(2024-12,**至今无 0.10.1**) |
| 状态 | 活跃维护(ROS2、NVIDIA Cosmos/NuRec 集成) | 技术预览,靠 `ue5-dev` nightly |
| 地图 | Town01–15 全套 | **仅 Town10 重制版 + 矿场图** |
| 天气 | 全可调(域随机化必需) | **锁死白天** |
| 传感器 | 完整 | 主力已迁移,有黑屏 bug |
| ScenarioRunner/Leaderboard | 支持 | **完全不兼容**(scenario_runner#1164) |
| Bench2Drive / 各 E2E 方案 | 全部支持(锁 0.9.15) | 无一支持 |
| 性能 | Epic 画质流畅 | 官方内测峰值 ~25 FPS |
| 磁盘 | 包 ~30GB | 包 130GB,源码构建 225GB+ |
| Python 包 | `carla`(0.9.15 wheel:cp37/cp38/cp39/**cp310**,cp310 可配 torch≥2.7;更正见 §0 第 4 点注) | `carla-ue5-api`(**不能混装**) |

### 2.2 0.9 → 0.10 迁移难度

资产/地图不可迁移(UE4 资产需在 UE5 重做)、物理引擎 PhysX→Chaos(车辆动力学要重标定)、渲染换 Lumen/Nanite(传感器图像有 domain gap)。**0.9 生态的方案不能平滑迁移到 0.10,不要对未来迁移做承诺**;0.10.1+ 补齐 ScenarioRunner/地图后再评估。

### 2.3 替代仿真器(均不推荐)

- Colosseum(AirSim 后继,UE5):2026-07 已归档,且只有单车动力学,无交通流/城市地图/场景引擎。自建 = 数月到一人年,放弃。
- AWSIM:Unity 而非 UE,面向 Autoware/LiDAR,无 E2E 闭环生态。
- Isaac Sim/Omniverse:无 E2E 驾驶评测基准;NVIDIA 的策略是把 NuRec/Cosmos 集成进 CARLA,而非取代它。
- 非 UE 补充:NAVSIM(nuPlan 衍生,PDMS 伪闭环)是 2024–2026 规划论文事实标准,可做训练期快速迭代;Waymax(JAX)适合大规模 RL/行为仿真。均为补充,不是主线。

## 3. 端到端方案调研(可在 CARLA 闭环运行的)

### 3.1 评测基线:Bench2Drive(NeurIPS'24 D&B)

- 仓库:Thinklab-SJTU/Bench2Drive(★1.9k,**CC-BY-NC-ND 禁止商用**),CARLA 0.9.15,220 条短路线 + 44 交互场景。
- 训练数据(Think2Drive RL 专家):Mini 4GB / Base 400GB / Full 4TB(HuggingFace)。
- Bench2DriveZoo(★396):UniAD/VAD/TCP/AD-MLP 官方闭环适配,**权重全开**,依赖已现代化(对 5090 最友好)。
- 官方成绩参考(DS 驾驶分/SR 成功率):UniAD 45.8/16.4;VAD 42.4/15.0;TCP-traj 59.9/30.0;ThinkTwice 62.4/31.2;DriveAdapter 64.2/33.1。

### 3.2 推荐候选

| 方案 | 仓库 | Bench2Drive DS/SR | 许可证 | 传感器 | 备注 |
|---|---|---|---|---|---|
| **SimLingo**(CVPR'25 Highlight,Challenge'24 冠军) | RenzKa/simlingo ★445 | **85.9/66.8(史上最高)** | Apache-2.0 | 纯视觉(InternVL2-1B) | 权重+全量数据(PDM-Lite 专家)+训练/评测代码全开;基于 carla_garage |
| **ORION**(ICCV'25,小米) | xiaomi-mlab/Orion ★661 | 77.7/54.6 | Apache-2.0 | 6 相机无 LiDAR | ckpt+Chat-B2D 数据全开;fp16 推理 17GB;三阶段训练单卡过重,只做推理/微调 |
| **TransFuser++**(ICCV'23) | autonomousvision/carla_garage ★557 | — | MIT | 相机+LiDAR | LB2 分支 = CARLA 0.9.15 + py3.10 leaderboard starter kit + PDM-Lite 专家 + 364GB 数据集;采数/评测基建最好 |
| Bench2DriveZoo(UniAD/VAD/TCP) | Thinklab-SJTU/Bench2DriveZoo ★396 | 见 §3.1 | 随 Bench2Drive | 相机(+LiDAR) | 官方权重直接评测,当基线 |

**不推荐**:TransFuser/TCP/InterFuser/LMDrive 等 0.9.10.1 时代仓库(torch 1.x 与 5090 冲突);DiffusionDrive/Senna/AutoVLA 无官方 CARLA 闭环支持(需自行移植);LMDrive 训练按 8×A100 设计。

### 3.3 推荐选型(单人单机 RTX 5090)

1. **首选复现目标:SimLingo** —— 单机最完整、成绩最高、纯视觉 1B 模型,5090 可推理可微调。
2. **并行基建:Bench2Drive + Bench2DriveZoo** —— 先跑通标准闭环评测,官方 ckpt 当基线。
3. **进阶:ORION(VLM/LLM 方向)** 或基于 carla_garage 自研改进。

## 4. 工具链(最小可行清单)

1. 仿真:CARLA **0.9.15** Linux 预编译包 + AdditionalMaps;headless 用 `-RenderOffScreen -nosound`;备选 Docker 镜像 `carlasim/carla:0.9.15`(`--gpus all --net=host`)。
2. 闭环评测:Bench2Drive(220 路线)+ carla_garage `leaderboard_2` 分支(leaderboard 已升 py3.10)。
3. 数据:先 Mini(4GB)/Dev10 冒烟 → carla_garage 364GB(PDM-Lite 专家)或 Bench2Drive Base(400GB)按需;自采用 carla_garage 的 `DATAGEN=1` 流水线,不自己造轮子。
4. 训练栈:独立 conda 环境,PyTorch ≥2.7(cu128,Blackwell),单卡起训。TransFuser++ 级模型官方 4×A100×3 天/阶段 → 5090 单卡约 1–2 周,或单阶段 + ResNet34 几天出可用模型。
5. **不要装**:ROS2 bridge(E2E 模仿学习用不到)、CARLA 0.10、AWSIM/Isaac/Colosseum。

## 5. 风险清单(按优先级)

1. **WSL2 + Vulkan**:CARLA server 在 WSL2 内大概率起不来(Vulkan ICD 缺失,issue #9209 未闭环)。备选:① CARLA server 跑 Windows 原生包,WSL2 客户端走 TCP(社区确认 "works perfect");② Docker + nvidia-container-toolkit;③ 双系统原生 Ubuntu(长期最干净)。**M0 必须先验证**。
2. **sm_120 兼容性**:老仓库锁 torch 1.x/mmcv-full 跑不动;优先选依赖现代化的仓库(Bench2DriveZoo、carla_garage、SimLingo),flash-attn 等需按新 torch 重编。
3. **WSL2 内存上限**:`.wslconfig` 显式调到 ≥40GB。
4. **磁盘**:585GB 可用,数据集按需下载,避免一次拉 Full(4TB)。
5. **CARLA 进程崩溃常态化**:评测脚本内置自动重启 + `clean_carla.sh` + 端口检查。
6. **许可证**:Bench2Drive 全家桶 CC-BY-NC-ND(禁商用);SimLingo/carla_garage/ORION 是 Apache-2.0/MIT。

## 6. 推荐技术路线

- **主线(闭环 E2E 研发)**:CARLA 0.9.15(UE4)+ Bench2Drive + SimLingo/carla_garage。
  理由:唯一拥有完整"数据→训练→闭环评测"生态的路线;"最新方案"(2025–2026 的 SOTA)都在这条线上。
- **关于 UE5**:UE5 版 CARLA(0.10)当前无法满足"训练+闭环评测"目标,作为**第二阶段迁移路径**保留:等 0.10.1+ 补齐地图/ScenarioRunner,或项目后期需要 Lumen/Nanite 高保真相机画面时,再并行装一套 0.10 评估迁移。若 UE5 是硬性要求,需接受闭环评测链全部自建的代价(参照 Bench2Drive 评分思路自写 route/scenario 执行器)。
- **训练期补充**:NAVSIM 开环/PDMS 做快速迭代,闭环验证回 CARLA。

## 7. 主要参考来源

- CARLA 0.10.0 发布:https://carla.org/2024/12/19/release-0.10.0/ ;功能缺失清单:discussions/8323
- CARLA 0.9.16 发布:https://carla.org/2025/09/16/release-0.9.16/
- CARLA UE5 文档:https://carla-ue5.readthedocs.io/en/latest/
- ScenarioRunner 不支持 0.10:scenario_runner issue #1164;WSL2 Vulkan:carla issue #9209
- Bench2Drive:github.com/Thinklab-SJTU/Bench2Drive ;Zoo:github.com/Thinklab-SJTU/Bench2DriveZoo
- SimLingo:github.com/RenzKa/simlingo ;ORION:github.com/xiaomi-mlab/Orion ;carla_garage:github.com/autonomousvision/carla_garage(leaderboard_2 分支)


---

## 8. 补充调研(2026-08-27 v2):UE5 硬要求下的全 Windows 可行性

### 8.1 CARLA 0.10 在 Windows 的支持

- 官方有 `[Windows 11] CARLA_0.10.0.zip` 预编译包(2024-12-19,至今唯一 0.10 版本);要求 Win11、驱动 ≥560、≥16GB VRAM、130GB 磁盘。
- 已知 issue:启动 `EXCEPTION_ACCESS_VIOLATION`(#9439)、黑窗即退(#9409)、渲染全白(#8846);`-RenderOffScreen` 在 Windows 历史上有崩溃记录,**原生 Windows 建议直接窗口模式跑**。
- Python 客户端:PyPI `carla-ue5-api==0.10.0` **只有 manylinux wheel(cp311/cp312),无 Windows wheel**;Windows 下只能用 zip 包内置的 `PythonAPI/carla/dist/carla-0.10.0-cp3{8..12}-win_amd64.whl`。
- UE5.5 源码构建(VS2022 + 225GB)只改 Python 层时**完全不需要**;Windows 打包目标官方标注 "not yet fully tested"。

### 8.2 原生 Windows 训练栈

- PyTorch ≥2.7 + cu128 **有官方 Windows wheel 且支持 sm_120**(5090 可用)。
- **flash-attn 无官方 Windows 支持**(SimLingo 用了它):只有社区预编译轮,cu128+torch2.7+sm_120 组合覆盖不全;退路 `attn_implementation="sdpa"`,性能损失可接受。
- triton 官方不支持 Windows(`torch.compile` 受限);xformers 有官方 Windows wheel;HF 数据集下载无障碍。

### 8.3 0.10 闭环生态(比 OS 更关键的短板)

- ScenarioRunner 不兼容 0.10(scenario_runner#1164),无发布计划;Bench2Drive/SimLingo/carla_garage 全部锚定 0.9.15。
- **Scenic 3(CARLA fork)是 0.10 上唯一官方闭环支点**(Town10 示例;坑:shapely 需降到 2.0.0,#8906)。
- TrafficManager 在 0.10 中存在,可做 autopilot 交通 + 基础数据采集;**无特权专家**(PDM-Lite 只有 0.9 版),高质量专家数据需自写规则专家或移植。
- 关键洞察:**模型训练本身是离线、与仿真器解耦的**——SimLingo 的模型/训练代码可复用,需要自建的只有两块:0.10 数据采集流水线 + 0.10 闭环评测 agent/route 执行器(评分参照 Bench2Drive 的 DS/SR 思路)。

### 8.4 三种部署形态排序

| 形态 | 结论 |
|---|---|
| **(b) Windows 原生 CARLA server + WSL2 客户端/训练** | **首选**。server 绕开 WSL2 Vulkan 风险、GPU 完整利用;WSL2 内 `pip install carla-ue5-api`(manylinux 现成)走 localhost 连 2000/2001 端口;训练栈全 Linux 生态(flash-attn/triton 正常)。坑:`.wslconfig` 调内存 ≥40GB、数据放 ext4 不放 `/mnt/c`、Windows 防火墙放行端口、WSL2 内不装 Linux NVIDIA 驱动(用 Windows 驱动 577)。 |
| (a) 全原生 Windows | 可行但脆:server+客户端没问题;训练侧 flash-attn/triton 受限,跑 SimLingo 原版训练配置概率低,改 SDPA 后中小规模训练可行。 |
| (c) 双系统原生 Linux | 最纯但运维成本最高,且 0.10 在 Linux 同样有 Vulkan 稳定性报告;仅当 (b) 踩到不可解的坑再考虑。 |

### 8.5 v2 结论

1. **全部跑 Windows 可行,但不推荐**——瓶颈不在 server 端(Windows 包可用),而在训练生态(flash-attn/triton)。
2. **采用 (b) 混合形态**:Windows 原生跑 CARLA 0.10 server,WSL2 跑一切 Python(客户端、数据采集、训练)。
3. 项目的主要工作量从"复现"变为"**自建 0.10 闭环基建**":route 执行器、驾驶评分、专家数据采集(Scenic 3 起步)。
4. 0.10 固有限制全程伴随:仅 Town10、锁死白天(域随机化受限 → 过拟合风险)、~25 FPS(采数/评测慢)、车辆 11 款。


---

## 9. 补充调研(2026-08-27 v3):2025-08 → 2026-08 新进展

> 窗口期内有重要遗漏,以下数字取自官方 README/arXiv 转述,未逐篇 PDF 复核。

### 9.1 新 SOTA(Bench2Drive,CARLA 0.9.x)

| 方案 | 发表 | DS/SR | 仓库/许可 | 说明 |
|---|---|---|---|---|
| **BridgeDrive** | ICLR'26(Bosch) | **96.3/89.2**(LEAD 数据) | github.com/shuliu-ethz/BridgeDrive,MIT | DiffusionDrive 后继(diffusion bridge);基于 carla_garage 管线,相机+LiDAR;有权重 |
| **TFv6 / LEAD** | CVPR'26(Chitta 组) | 95.2/86.8 | github.com/kesai-labs/lead,全开 | LEAD 新专家 + 8930 条 route 全模态数据集(~1TB);专家 1080Ti 可跑;附 Fail2Drive 长尾评测 |
| AutoMoT | ICML'26 | 87.3/70.0 | github.com/OscarHuangWind/AutoMoT | 异步 MoT VLA |
| HiP-AD | ICCV'25(Nullmax) | 86.8 | github.com/nullmax-vision/HiP-AD | — |
| SimLingo | CVPR'25 | 85.1/67.3 | github.com/RenzKa/simlingo,Apache-2.0 | 已被超越,但仍是纯视觉+语言路线最佳参照 |
| UniDriveVLA | 2026-04(小米) | 78.4/51.8 | github.com/xiaomi-research/unidrivevla | 代码+权重全放,分数一般 |

- SimLingo 2026 年已非最强:落后主要源于专家数据(PDM-Lite vs LEAD),与架构正交 → **复用其训练代码 + 换 LEAD 式专家数据是合理组合**。
- **HiDrive**(arXiv 2605.09972,2026-05):基于 **CARLA UE5 分支**的闭环评测 benchmark(长尾场景+法规/伦理指标,代码资产开放)—— UE5 闭环有先例,是 M1 自建基建的直接参考。
- Raw2Drive(NeurIPS'25,RL 世界模型):训练需 64×H800·天,单机不可行,排除。
- LEAD 注意点:采数锚定 CARLA 0.9.16 / 评测 0.9.15,**不能直接在 0.10 用**;价值在其专家设计、数据格式(py123d)与管线,供移植借鉴。

### 9.2 对项目选型的更新(v3)

- 跑通链路第一模型:TCP-traj / AD-MLP(最小,单相机)。
- 主模型候选:SimLingo(纯视觉+语言)或 BridgeDrive/TFv6 架构(分数最强,相机+LiDAR);两者训练管线同为 carla_garage 血统,均与仿真器解耦、可配自采 0.10 数据。
- 专家设计参照 LEAD(替代原"TM autopilot + 规则补丁"的 v0 方案,先 TM 冒烟再向 LEAD 对齐)。
- M1 基建参照 HiDrive(UE5 闭环 benchmark 先例)。


---

## 10. 补充调研(2026-08-27 v4):第二模型选型

> 逐仓核实过权重可下载性;"coming soon"类一律排除。

### 10.1 第二模型:AutoMoT(ICML'26)——选定

- github.com/OscarHuangWind/AutoMoT(默认分支 `release`,2026-07 仍活跃);权重 huggingface.co/Oscar-Huang/AutoMoT 在架(~13GB,Apache-2.0;注意 GitHub 代码仓无 LICENSE 文件,只作学术对照)。
- Bench2Drive DS=87.34/SR=70.00(README);HF 模型卡 DS=89.42/SR=74.09(权重更新)。
- CARLA 0.9.15,仓内 vendored 整套 leaderboard + scenario_runner,评测脚本支持断点续跑。
- 架构:Qwen3-VL 底,异步 MoT 双专家(4B 理解 + 1.6B 动作)。
- 5090 兼容性:**推理开箱即用**(官方栈正好 torch 2.7.1+cu128,13GB bf16);**微调不可行**(训练默认单卡 80GB)→ 只用于 UE4 基线 + UE5 zero-shot,不参与 M4 微调。
- **短板:动作分支吃 LiDAR BEV 特征,非纯视觉**——渲染变量被部分稀释,结论中须注明(可做去 LiDAR 消融)。

### 10.2 备选:MindDrive-3B(小米,ECCV'26,Apache-2.0)

- github.com/xiaomi-mlab/MindDrive;权重(0.5B/3B,含 base)全在 HF;DS=80.59/SR=58.26。
- **6 目环视纯视觉,无 LiDAR——渲染敏感度三者最高**;但官方栈 py3.8+torch2.4.1+cu118+魔改 mmcv,5090 需移植到 torch≥2.7(预算 1-2 天)。
- 含 PPO 后训练,只用其 IL 权重做推理,不碰 RL。

### 10.3 排除项

- LEAD/TFv6:非 VLM、含 LiDAR,定位为专家/采数基建参照。
- OneVL(小米,2026-05):无 CARLA 闭环 agent。DriveStack-VLA:无公开权重。HiP-AD:非 VLM,权重未核实。PersonaDrive/AnchorVLA 等:权重不可得。

### 10.4 三模型对比矩阵(架构维度全错开,结论可信度高)

| | SimLingo(主) | AutoMoT(第二) | MindDrive(备选) |
|---|---|---|---|
| backbone | InternVL2-1B | Qwen3-VL 4B+1.6B 双专家 | Qwen2.5-3B + EVA02/PETR |
| 传感器 | 单前视相机 | 前视相机 **+ LiDAR** | 6 目环视相机 |
| 动作解码 | 语言-动作对齐 | 异步快慢专家 | 双 LoRA 专家 |
| DS/SR | 85.9/66.8 | 87.3~89.4/70~74 | 80.6/58.3 |
| 5090 微调 | 可 | **不可(需 80GB)** | IL 微调可(需移植) |
