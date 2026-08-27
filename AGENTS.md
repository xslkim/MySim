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
- 内存:宿主物理 **64GiB(可见 63.4GiB)**;`.wslconfig` **已降档 memory=32GB / processors=16 / swap=16GB**(2026-08-28 A1 执行;processors 用户保留 16 未降 14)。
- 磁盘三盘口径:C: 剩 ~741GB(CARLA server 已落位 `C:\carla\`,0.10 21GB + 0.9.15 29GB);D: 剩 ~62GB(已评估弃用);WSL vhdx 所在盘(1.5T)剩 ~582GB = 数据预算(数据集按需下载,禁一次拉 Bench2Drive Full 4TB)。
- WSL2 内训练栈:PyTorch ≥2.7 + cu128;**原生 Windows 不装训练栈**(flash-attn/triton 受限)。
- WSL2 内**不要**装 Linux NVIDIA 驱动(用 Windows 驱动透传);数据放 WSL2 ext4,不放 `/mnt/c`。
- 端口:UE5 server **2021/2022/2023**,UE4 server **2031/2032/2033**(2026-08-28 CP0 用户拍板;原约定 2000–2002/2010–2012 被 winNAT 保留段 1921–2020 吞掉,见已知坑;TM 两侧均默认 8000);WSL→Windows 用**宿主 IP 动态获取**(`ip route show | awk '/default/{print $3}'`),禁硬编码 localhost。conda 环境名见硬性规则 #1;其余登记 M0 完成后补。

## 硬性规则

1. **conda 环境拓扑以 `docs/plan/01-infra.md` §3 为准**:常驻 3 个 —— `mysim-ue5`(py3.11 + `carla-ue5-api==0.10.0`)/ `mysim-simlingo`(py3.10 + torch2.7.1+cu128 + `carla==0.9.15`,推理+评测+微调同 env)/ `mysim-automot`(py3.10 + AutoMoT 官方栈);临时 `mysim-minddrive`(T1.4,归档即删)。`carla` 与 `carla-ue5-api` 永不装在同一环境。
2. CARLA 易崩:所有评测/采数脚本内置 server 崩溃自动重启;选卡用 `-graphicsadapter=N`。
3. 大型下载/采数/训练/评测用后台任务跑,主会话不阻塞。
4. 对比实验必须控制变量:同模型架构、同路线设计、同指标体系;UE4/UE5 差异只保留渲染/物理。
5. 新踩的坑(报错+解法)追加到本文"已知坑"一节。
6. **下载资源优先国内镜像/加速**:HF 数据集与模型用 `HF_ENDPOINT=https://hf-mirror.com`;pip 用清华源(`-i https://pypi.tuna.tsinghua.edu.cn/simple`);conda 用清华源;GitHub release 大文件优先代理加速(可用性实测后登记到"已知坑")。镜像失效立即回退官方源并记录。

## 已知坑

(M0 起开始记录。预备:0.10 Windows 启动可能 EXCEPTION_ACCESS_VIOLATION #9439 / 黑窗 #9409;Scenic 3 需 shapely==2.0.0 #8906;`-RenderOffScreen` 在 Windows 有崩溃记录,优先窗口模式;5090 需 torch≥2.7+cu128,老 torch 报 `no kernel image`;~~远程会话断开后 server 存活~~ **已验证存活,2026-08-28 A3 通过**;WSL vhdx 在 G: 与 C: 不同盘,无同盘 I/O 竞争,T0.1 已坐实。)

- **T0.4(2026-08-27)**:SimLingo 官方 `environment.yaml` 锁 py3.8 —— 不可用(torch≥2.7 不支持 py3.8,且 carla==0.9.15 无 cp38 以外适配),env 按 §3 拓扑 py3.10 自建;SimLingo 依赖移植归 **T1.0**。
- **T0.4(2026-08-27)**:shapely==2.0.0 与 numpy≥2 二进制不兼容(`AttributeError: _ARRAY_API not found`,shapely 2.0.0 按 numpy 1.x 编译)——`mysim-ue5` 内钉 `numpy==1.26.4`;同时 opencv-python-headless 5.x 元数据要求 numpy≥2,钉 `opencv-python-headless==4.10.0.84`(与 numpy 1.26 两全)。
- **T0.4(2026-08-27)**:download.pytorch.org 直连实测 ~1.4MB/s(torch cu128 全套 ~3.3GB 约 40min);TUNA 无 cu128 镜像(404),aliyun/sjtu 同名路径不可用——torch cu128 只能走官方索引,多 env 复用靠 pip 本地缓存(第二个 env 秒装)。
- **T0.5(2026-08-28)**:**winNAT TCP 排除段 1921–2020 吞掉端口 2000–2002/2010–2012**(netsh excludedportrange 实测;另有 2269–4289、50000–50059 多段)——CARLA server bind 抛 WSAEACCES 未捕获直接崩(0xe06d7363)。**端口约定已修订为 UE5 2021–2023 / UE4 2031–2033(CP0 用户拍板)**;winNAT 保留段会动态漂移,大重启后复查 `netsh int ipv4 show excludedportrange tcp`。
- **T0.5(2026-08-28)**:0.10 Shipping 版不写 CarlaUnreal.log(加 -log 也无效),Saved 目录在 `%LOCALAPPDATA%\CarlaUnreal\Saved`;adapter 坐实改用崩溃 XML 的 `RHI.AdapterName` + nvidia-smi 进程列表。IddCx 虚拟显示适配器(Todesk/Oray)**不进 DXGI 枚举**,`-graphicsadapter=2` 实测选中 5090(=0 亦可,=2 更稳)。
- **T0.5(2026-08-28)**:carla-ue5-api 0.10.0 客户端结束时"恢复异步 apply_settings"会 C++ abort(exit 134,server 无感)——脚本先落盘 JSON 再恢复;WSL→Windows 起 server 用 `Start-Process <exe> -PassThru`(cmd /c 包装首试静默失败);宿主 RAM 压测无 stress-ng(sudo 要密码),走 python 兜底 tools/t05_ram_gate.py。
- **T0.5(2026-08-28) 实测**:UE5 server Epic 1280×720 占显存 ~9GB、宿主 RAM ~10GB;同步 42.3 FPS(2.1× 实时);RGB 720p 40.4 FPS 零丢帧;+8GB/+13GB torch 同存 PASS(29.5GB/32.6GB 显存,43 FPS);**56GB 口径 RAM 门禁 FAIL**(压 30GB 时宿主空闲仅 2.9–3.2GiB),A1 降档 32GB 必要性坐实。
- **T0.6(2026-08-28)**:`-graphicsadapter` 索引 **UE4/UE5 两侧不通用**——UE5 侧 =2 选 5090;UE4.26 侧枚举含 Intel 核显+IddCx 虚拟卡,**=0 才是 5090**(=2 时 5090 显存平躺、同步仅 13.9 FPS、丢帧 729,数据作废特征明显)。判卡手段:nvidia-smi 显存/util 突变(0.9.15 Shipping 窗口模式也不写 CarlaUE4.log)。watchdog SIDES 已按此修正。
- **T0.6(2026-08-28)**:0.9.15 的 `CarlaUE4.exe` 是引导壳,真进程 `CarlaUE4\Binaries\Win64\CarlaUE4-Win64-Shipping.exe`,清理杀两个;PowerShell 里 `taskkill //IM` 不可用在 ps 直接调,用 `Stop-Process -Name`。
- **T0.6(2026-08-28) 实测**:UE4 侧(Epic 720p/Town10HD_Opt)同步 97.6 FPS(4.9× 实时)、RGB 110 FPS 零丢帧、server 显存 +8.1GB;UE4 97.6 vs UE5 42.3 FPS 为渲染管线真实差异,作对比实验 FPS 基线。carla==0.9.15 客户端退出时同有 C++ abort(server 无感)。
- **CP0 复测(2026-08-28)**:`-graphicsadapter` 索引**随重启/会话漂移**——T0.5 UE5 侧 =2 选 5090,WSL 重启后同参数选到 Microsoft Basic Render Driver 直接崩(AV 0x18),改 =0 才选中。**任何启动流程必须带 nvidia-smi 显存增量校验**(server 起来后显存应比基线 +4GB 以上;watchdog 已内置 adapter 轮询 [0,2,1,3] + 校验,tools/wait_server.py 可单独用)。另:`conda run ... python3 - <<EOF` 的 stdin heredoc 会被 conda run 吞掉(python 收到空输入静默 exit 0),等就绪脚本必须走文件。
- **CP0 复测(2026-08-28)实测**:32GB 降档生效后,UE5 server + WSL 压 28GB 驻留 4min,宿主空闲稳定 12.9–14.5GB(≥6GB **PASS**),server 全程存活;释压后 60s 冒烟回归 PASS(同步 41.9 FPS、RGB 零丢帧)。重启后 winNAT 保留段已漂移(1921–2020 段消失,新增 2756–3355),2021/2031 当前均空闲。
