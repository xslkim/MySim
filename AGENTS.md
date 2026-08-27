# AGENTS.md — MySim(UE5 端到端自动驾驶仿真)

## 项目目标

**核心命题:渲染保真度对端到端自动驾驶的影响** —— 选一个 UE4(CARLA 0.9.x)上成熟的开源 E2E 模型,在 UE5(CARLA 0.10)上实现,做 UE4 vs UE5 的系统对比,**重点是渲染效果(Lumen/Nanite 高保真画面)对模型的影响**。
先读 `docs/01-research-report.md`(选型依据,注意 §8/§9 更新)和 `docs/02-roadmap.md`(里程碑与完成判据)。

## 关键决策(不要轻易推翻,推翻需用户确认)

- 模型:主模型 **SimLingo**(CVPR'25,纯视觉 InternVL2-1B,权重/数据/训练代码全开,5090 可微调)——渲染研究最敏感。第二模型 **AutoMoT**(ICML'26,Qwen3-VL 异步双专家,权重在架,torch2.7.1+cu128 与 5090 天然兼容)——**只用于 UE4 基线 + UE5 zero-shot,不微调**(训练需 80GB);注意其动作分支含 LiDAR,渲染结论须注明。备选 MindDrive-3B(6 目环视纯视觉,需 torch 移植)。
- 双仿真器并行:CARLA 0.9.15(UE4,基线侧,跑 Bench2Drive 复现)+ CARLA 0.10.0(UE5,实现侧)。**两台 server 都跑 Windows 原生**,Python 全在 WSL2。
- 闭环基建(UE5 侧)**自建**:route 执行器 + DS/SR 评分(参照 Bench2Drive + HiDrive UE5 先例)+ Scenic 3 场景。
- 专家数据:0.10 侧先 TrafficManager autopilot 冒烟,设计向 LEAD(CVPR'26)对齐。
- 排除:2025 年前的方案(TransFuser/TCP/UniAD 等只作历史参照);世界模型/RL 专家训练(Raw2Drive 等,单机跑不动);含 LiDAR 的主模型(渲染变量被几何传感器稀释)。

## 本机环境事实

- Windows 11 宿主 + WSL2 Ubuntu 22.04;RTX 5090 32GB(sm_120,Windows 驱动 577.00 / CUDA 12.9)。
- 16 核 CPU / 54GB 内存(`.wslconfig` 须调 ≥40GB);磁盘可用 ~585GB(0.10 包 130GB + 0.9.15 包 ~30GB,数据集按需下载)。
- WSL2 内训练栈:PyTorch ≥2.7 + cu128;**原生 Windows 不装训练栈**(flash-attn/triton 受限)。
- WSL2 内**不要**装 Linux NVIDIA 驱动(用 Windows 驱动透传);数据放 WSL2 ext4,不放 `/mnt/c`。
- CARLA 安装路径、端口、conda 环境名:M0 完成后在此登记。

## 硬性规则

1. **三个 conda 环境严格分离**:UE5 客户端(py≥3.11 + `carla-ue5-api`)/ UE4 客户端(py3.8 + `carla==0.9.15`,Bench2Drive/SimLingo 评测用)/ 训练(py≥3.10 + torch≥2.7)。`carla` 与 `carla-ue5-api` 永不装在同一环境。
2. CARLA 易崩:所有评测/采数脚本内置 server 崩溃自动重启;选卡用 `-graphicsadapter=N`。
3. 大型下载/采数/训练/评测用后台任务跑,主会话不阻塞。
4. 对比实验必须控制变量:同模型架构、同路线设计、同指标体系;UE4/UE5 差异只保留渲染/物理。
5. 新踩的坑(报错+解法)追加到本文"已知坑"一节。

## 已知坑

(M0 起开始记录。预备:0.10 Windows 启动可能 EXCEPTION_ACCESS_VIOLATION #9439 / 黑窗 #9409;Scenic 3 需 shapely==2.0.0 #8906;`-RenderOffScreen` 在 Windows 有崩溃记录,优先窗口模式;5090 需 torch≥2.7+cu128,老 torch 报 `no kernel image`。)
