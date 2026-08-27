# AGENTS.md — MySim(UE5 端到端自动驾驶仿真)

## 项目目标

**核心命题:渲染保真度对端到端自动驾驶的影响** —— 选一个 UE4(CARLA 0.9.x)上成熟的开源 E2E 模型,在 UE5(CARLA 0.10)上实现,做 UE4 vs UE5 的系统对比,**重点是渲染效果(Lumen/Nanite 高保真画面)对模型的影响**。
先读 `docs/01-research-report.md`(选型依据,注意 §8/§9/§10 更新)、`docs/02-roadmap.md`(里程碑与完成判据)、`docs/plan/00-overview.md`(执行方案 v5);环境勘误以 `docs/04-doc-review.md`(2026-08-27 实测)为准。

## 关键决策(不要轻易推翻,推翻需用户确认)

- 模型:主模型 **SimLingo**(CVPR'25,纯视觉 InternVL2-1B,权重/数据/训练代码全开,5090 可微调)——渲染研究最敏感。第二模型 **AutoMoT**(ICML'26,Qwen3-VL 异步双专家,权重在架,torch2.7.1+cu128 与 5090 天然兼容)——**只用于 UE4 基线 + UE5 zero-shot,不微调**(训练需 80GB);注意其动作分支含 LiDAR,渲染结论须注明。第三模型 MindDrive-3B(6 目环视纯视觉,需 torch 移植,可砍旁支)。
- 双仿真器并行:CARLA 0.9.15(UE4,基线侧,跑 Bench2Drive 复现)+ CARLA 0.10.0(UE5,实现侧)。**两台 server 都跑 Windows 原生**,落位 `C:\carla\`(2026-08-27 拍板);Python 全在 WSL2。
- 闭环基建(UE5 侧)**自建**:route 执行器 + DS/SR 评分(参照 Bench2Drive + HiDrive UE5 先例)+ Scenic 3 场景。
- 专家数据:0.10 侧先 TrafficManager autopilot 冒烟,设计向 LEAD(CVPR'26)对齐。
- 排除:2025 年前的方案(TransFuser/TCP/UniAD 等只作历史参照);世界模型/RL 专家训练(Raw2Drive 等,单机跑不动);含 LiDAR 的主模型(渲染变量被几何传感器稀释)。

## 本机环境事实(2026-08-27 实测口径,见 docs/04-doc-review.md)

- Windows 11 宿主 + WSL2 Ubuntu 22.04;RTX 5090 32GB(sm_120,Windows 驱动 577.00 / CUDA 12.9);宿主在册 3 个虚拟显示适配器(Todesk / 向日葵 OrayIddDriver / Microsoft Remote Display),**常经远程桌面访问**。
- CPU:20 物理核(Core Ultra 7 265K,Arrow Lake 无超线程);WSL 侧 16 vCPU 是 `.wslconfig` cap,非硬件全量。
- 内存:宿主物理 **64GiB(可见 63.4GiB)**;`.wslconfig` 当前 memory=56GB / processors=16 / swap=32GB,**T0.1 动作为降档 56→32GB**(processors→14、swap→16GB;闭合算术见 `docs/plan/01-infra.md` §4.3)。
- 磁盘三盘口径:C: 剩 ~795GB(CARLA server 落位 `C:\carla\`);D: 剩 ~62GB(已评估弃用);WSL vhdx 所在盘(1.5T)剩 ~582GB = 数据预算(数据集按需下载,禁一次拉 Bench2Drive Full 4TB)。
- WSL2 内训练栈:PyTorch ≥2.7 + cu128;**原生 Windows 不装训练栈**(flash-attn/triton 受限)。
- WSL2 内**不要**装 Linux NVIDIA 驱动(用 Windows 驱动透传);数据放 WSL2 ext4,不放 `/mnt/c`。
- 端口:UE5 server 2000/2001/2002,UE4 server 2010/2011/2012(已定,禁改);WSL→Windows 用**宿主 IP 动态获取**(`ip route show | awk '/default/{print $3}'`),禁硬编码 localhost。conda 环境名见硬性规则 #1;其余登记 M0 完成后补。

## 硬性规则

1. **conda 环境拓扑以 `docs/plan/01-infra.md` §3 为准**:常驻 3 个 —— `mysim-ue5`(py3.11 + `carla-ue5-api==0.10.0`)/ `mysim-simlingo`(py3.10 + torch2.7.1+cu128 + `carla==0.9.15`,推理+评测+微调同 env)/ `mysim-automot`(py3.10 + AutoMoT 官方栈);临时 `mysim-minddrive`(T1.4,归档即删)。`carla` 与 `carla-ue5-api` 永不装在同一环境。
2. CARLA 易崩:所有评测/采数脚本内置 server 崩溃自动重启;选卡用 `-graphicsadapter=N`。
3. 大型下载/采数/训练/评测用后台任务跑,主会话不阻塞。
4. 对比实验必须控制变量:同模型架构、同路线设计、同指标体系;UE4/UE5 差异只保留渲染/物理。
5. 新踩的坑(报错+解法)追加到本文"已知坑"一节。
6. **下载资源优先国内镜像/加速**:HF 数据集与模型用 `HF_ENDPOINT=https://hf-mirror.com`;pip 用清华源(`-i https://pypi.tuna.tsinghua.edu.cn/simple`);conda 用清华源;GitHub release 大文件优先代理加速(可用性实测后登记到"已知坑")。镜像失效立即回退官方源并记录。

## 已知坑

(M0 起开始记录。预备:0.10 Windows 启动可能 EXCEPTION_ACCESS_VIOLATION #9439 / 黑窗 #9409;Scenic 3 需 shapely==2.0.0 #8906;`-RenderOffScreen` 在 Windows 有崩溃记录,优先窗口模式;5090 需 torch≥2.7+cu128,老 torch 报 `no kernel image`;**远程桌面会话(Todesk/向日葵虚拟显示)与窗口模式 CARLA server 的兼容性未验证,CP0 冒烟须含"远程会话断开后 server 存活"项**;若 WSL vhdx 与 C: 同盘,采数期 server 读 + dataloader 读存在同盘 I/O 竞争,T0.1 坐实。)
