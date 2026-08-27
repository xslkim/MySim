# 01 — 环境与基建自动化

> 版本 v5(终稿)· 2026-08-27 · 第 5 轮(依据 `docs/plan/_reviews/round-4.md` 修订)
> v5 变更:本文档内容无实质修订(v4 的 §4.3 门禁/§5 预算/§6 规范经 round-4 复核闭环);仅升版对齐。相关新条款位置:MDE 治理与扩容预算见 `00-overview.md` CP3/§7 与 `02-execution.md` 附录(R4-N1);limitation 条款见 `02-execution.md` T5.2(R4-N2)。
> v4 变更:§4.3 CP0 门禁测试负载定义 + 告警线锚定规则(N6);§5 磁盘预算重算(ckpt 40→45GB 训练态口径、envs 28→36GB MindDrive 临时 env,N5/N10);§6 增训练过程指标本地落盘规范(N4)。
> 读者:env-agent 与 orchestrator。目标:"照此文档即可装出双仿真器环境",不留自由发挥空间。

## 1. 部署形态与网络(已定,勿推翻)

Windows 11 宿主跑两台原生 CARLA server;WSL2(Ubuntu 22.04)跑全部 Python。依据:调研 §8.4 形态 (b),绕开 WSL2 Vulkan 风险(issue #9209),训练侧保留 Linux 生态。

**网络**:
- **默认方案 = 宿主 IP**:NAT 模式 localhost 转发只有 Windows→WSL 默认开;WSL 访问 Windows 服务必须用宿主 IP([Microsoft WSL networking 文档](https://learn.microsoft.com/en-us/windows/wsl/networking))。客户端/watchdog 启动时动态获取:`ip route show | awk '/default/{print $3}'`,**禁止硬编码 localhost**。
- localhost 双向互通仅 mirrored 模式成立(需 Win11 22H2+ 与 `Set-NetFirewallHyperVVMSetting`);启用命令预置 `windows-actions.md`,CP0 人定,v4 默认不依赖。
- 传感器流开销:1280×720 RAW ~2.7MB/帧,20Hz ≈ 55MB/s 跨 WSL 边界。T0.5 必须记录 5 分钟 RGB 流吞吐/丢帧/RPC 延迟,据此定采数期压缩配置(RAW vs JPEG),登记 env-registry。

## 2. Windows 侧:CARLA server 安装与守护

### 2.1 安装(任务卡 T0.2/T0.3,人工半参与)

| 项 | 值(提议,CP0 登记为准) |
|---|---|
| UE5 server | `D:\carla\CARLA_0.10.0\`(官方 `[Windows 11] CARLA_0.10.0.zip`) |
| UE4 server | `D:\carla\CARLA_0.9.15\`(Town10HD 由 T0.3 `get_available_maps()` 坐实,缺则补 AdditionalMaps) |
| 端口 | UE5: 2000/2001/2002;UE4: 2010/2011/2012(错开,禁改) |
| 数据盘 | WSL2 ext4(`~/data/`),不放 `/mnt/c`;Windows 侧只放 server;harness 需要的 `PythonAPI` 纯 Python 目录**拷入 WSL ext4 再设 PYTHONPATH**(G5) |

**盘位前置(T0.1)**:登记 C:/D: 可用空间、WSL vhdx 位置与上限;错配则 vhdx 迁移步骤进 `windows-actions.md`。

**下载纪律**:**下载解压一律 Windows 侧**(`powershell.exe curl.exe -C -` + 7z;`/mnt/*` 9P 吞吐差);WSL 仅校验。校验分支:**官方公布 sha256 则校验散列;无散列则以文件大小 + 启动冒烟替代**(G4)。流程:下载 → 校验 → 解压 → **立即删 zip** → 登记。水位超 80% 暂停上报。

### 2.2 启动与崩溃重启(产物 `tools/win/`)

- 启动(窗口模式,**禁用 `-RenderOffScreen`**):
  - UE5: `CarlaUE5.exe -carla-rpc-port=2000 -graphicsadapter=0 -quality-level=Epic -windowed -ResX=1280 -ResY=720`
  - UE4: `CarlaUE4.exe -carla-rpc-port=2010 -graphicsadapter=0 -quality-level=Epic`
  - 实验一律 Epic 并记 config;开发冒烟可用 Low。
  - 同步模式由客户端 world settings 设置,默认 `fixed_delta_seconds=0.05`(20Hz);T0.5 判定跟不上则两侧统一 0.1(10Hz)并记录。
- 守护 `tools/server_watchdog.py`,监管三类对象:
  1. **CARLA server**:RPC 端口 + `world.get_actors()` 心跳;失联 >30s → taskkill 清尸 → 重启 → 等 world ready(≤120s)→ 断点续跑;连 3 败 → BLOCKED 停队列。
  2. **模型服务进程**:pid 存活 + **推理心跳**(harness 每 N tick 写时间戳,超时判卡死);恢复 = 重启模型服务(ckpt 重载)→ harness 断点续跑。
  3. **训练进程(N3)**:训练任务心跳(每 epoch/落 ckpt 回写 progress);中断后从最近 resume ckpt 自动拉起(协议见 T4.4)。
  4. 同时监控宿主 RAM(§4.3)。
- 0.10 启动异常预案:#9439/#9409 → 清洁重装驱动 / 降 Low / 关 overlay;仍败升级人工。
- **宿主重启恢复 runbook**:① 开机自启 server 任务计划(CP0 人装);② orchestrator 检测 server 全灭 → 挂起 GPU 队列 + 报警 + 断点续跑入口;**训练任务按 resume 协议拉起(损失上限 = ckpt 间隔,N3)**。

### 2.3 WSL2 ↔ Windows 互操作约定

- 可用 `powershell.exe -Command ...`:进程查杀、启动 exe、查磁盘、**查显存(`nvidia-smi.exe`,Windows 侧为准;WSL 内 NVML 查询不全,[NVIDIA CUDA on WSL 指南](https://docs.nvidia.com/cuda/wsl-user-guide/index.html))**。**禁止**:改注册表、装 Windows 软件、动防火墙。
- `.wslconfig` 模板由 env-agent 生成(§4.3),人落盘并 `wsl --shutdown` 生效(CP0 前置)。

## 3. WSL2 环境拓扑(按模型分 env)

`carla==0.9.15` PyPI 只有 cp27/cp37/cp38/cp39/**cp310** wheel([PyPI JSON 已核实](https://pypi.org/pypi/carla/0.9.15/json));torch≥2.7 不支持 py3.8。官方先例:**py3.10 + torch 2.7.1+cu128 + carla==0.9.15 + flash-attn==2.8.3 + transformers==4.57.3**([AutoMoT requirements.txt 原文已核实](https://raw.githubusercontent.com/OscarHuangWind/AutoMoT/release/requirements.txt),文件标题即 "AutoMoT + Bench2Drive requirements"——官方同 env 同居 harness 依赖)。

| conda env | Python | 关键包 | 用途 | 估体积 |
|---|---|---|---|---|
| `mysim-ue5` | 3.11 | `carla-ue5-api==0.10.0`(仅 cp311/cp312)、scenic(shapely==2.0.0)、numpy/opencv | UE5 harness/采数/scoring(纯 sim 侧) | ~4GB |
| `mysim-simlingo` | **3.10** | torch 2.7.1+cu128、carla==0.9.15、SimLingo 移植依赖(T1.0 落定) | SimLingo 推理 + UE4 评测 + **M4 微调** | ~12GB |
| `mysim-automot` | **3.10** | torch 2.7.1+cu128、carla==0.9.15、AutoMoT 官方栈(按 requirements.txt 钉版) | AutoMoT 推理 + UE4 评测 | ~12GB |
| `mysim-minddrive`(临时,N10) | 3.10 | torch 2.7 移植尝试栈(T1.4 自建) | MindDrive 旁支专用;**成功/失败归档后即删**,不进长期登记 | ~8GB |

- **按模型分 env**:SimLingo 锁 transformers==4.46.3,AutoMoT 要 4.57.3(`qwen3_vl`),同 env 共存风险高。
- **UE5 侧模型评测 = harness↔模型 socket 分离**(Bench2Drive-VL 同构先例);模型代码/ckpt 与 UE4 侧完全同源;socket 规范与崩溃监管见 §2.2-2 与 T2.1;回退预案:py3.11 per-model env。
- flash-attn:sm_120+WSL2 有失败记录([flash-attention#2168](https://github.com/Dao-AILab/flash-attention/issues/2168))——T1.0 第一步即冒烟,失败走 `sdpa`,回退条款不可删。
- 硬性规则 #1 保持:`carla` 与 `carla-ue5-api` 永不同 env;装完 `conda env export` 登记;新坑追加"已知坑";WSL2 内不装 Linux NVIDIA 驱动。

## 4. 资源调度(单卡 32GB + 宿主 RAM)

### 4.1 GPU 任务分级与互斥

| 类 | 内容 | 显存预算(M0 实测回填前按官方口径) | 互斥 |
|---|---|---|---|
| A | 训练/微调 | ≤30GB,独占 | 与一切互斥;开训前确认无 CARLA server 存活;**训练持锁期间不安排任何中途闭环评测(N5)** |
| B | UE5 server + 客户端推理 | server 独占 12–16GB(官方建议最低 16GB,[0.10.0 发布页](https://carla.org/2024/12/19/release-0.10.0/));+ SimLingo ~6–8GB 可行;+ AutoMoT 13GB 余量仅 ~3GB,紧张 | 与 A/C 互斥 |
| C | UE4 server(估 4–6GB)+ 客户端推理 | 合计 ≤22GB | 与 A/B 互斥 |
| D | 纯 CPU | 0 | 不互斥 |

- 同一时刻最多一个 A/B/C 持有者;锁见 `00-overview.md` §4。
- AutoMoT + UE5 顶格预案:server 降分辨率/画质,config 留痕;仍 OOM 按 R9 升级。

### 4.2 显存观测与同存实测(两段法)

取锁核查走 `powershell.exe nvidia-smi.exe`。**同存实测两段**:M0(T0.5/T0.6)用合成显存负载(torch 分配 8GB/13GB 常驻 buffer 模拟 SimLingo/AutoMoT);真实模型同存下沉 T1.2(UE4)与 T3.4(UE5 AutoMoT 顶格)首跑冒烟。两段数据回填 §4.1。

### 4.3 宿主 RAM 预算与 CP0 门禁(N6 闭合)

- 概念:`memory=32GB` 是 WSL2 **占用上限**非预留;宿主可用 = 54 − WSL 实际占用。
- 最坏情形算术:宿主需求 = Win11 6–8GB + UE5 server 主机内存 8–16GB = **14–24GB**;WSL 顶满 32GB 时宿主余 22GB < 24GB —— 不闭合,闭合手段:
  1. `.wslconfig`:`memory=32GB`、`processors=14`、`swap=16GB`(swap 兜 WSL 尖峰,不救宿主);
  2. **CP0 门禁(负载定义,N6)**:WSL 侧内存压力注入至 **28–32GB**(`stress-ng --vm` 或等效,模拟采数/训练 dataloading 顶满态)+ UE5 server 运行态,测宿主空闲 ≥6GB;不满足则 WSL memory 降 28GB(顶满时宿主余 26GB > 24GB,闭合)并重冒烟;
  3. **告警线锚定**:降档/实测后记录最坏稳态宿主空闲 S,watchdog 告警线 = **S − 2GB**(替代静态 4GB,避免最坏稳态下告警疲劳);<2GB 硬停写盘任务不变。
  4. T0.5 的 server RAM 实测值直接对门禁做判定;实测 >16GB 时门禁余量同步上调。

### 4.4 排队优先级

CP 关联 > 关键路径 > 可选旁支(MindDrive)> 重跑/补数。orchestrator 每轮处理一次队列。

## 5. 磁盘预算表(585GB 硬预算;v4 重算,N5/N10)

| 项 | 预算 GB | 说明 |
|---|---|---|
| CARLA 0.10.0 server(zip 已删) | 130 | 瞬态峰值见下 |
| CARLA 0.9.15 server(+ 可能 AdditionalMaps) | 30(最多 50) | T0.3 坐实 Town10HD |
| conda envs ×3 + MindDrive 临时 env | 36 | N10:临时 env +8GB,归档后即删 |
| HF/torch 缓存 | 20 | — |
| SimLingo 仓库 + 官方 ckpt | 10 | — |
| AutoMoT 权重 | 13 | — |
| MindDrive 权重(可选) | 8 | — |
| Bench2Drive v0.0.3 Mini + 仓库 + Zoo ckpt | 10 | — |
| M3 成对渲染数据集 | 10 | 两侧各 ≥5k 张 |
| M4 0.10 自采数据(M 档 20h ≈ 288k 帧) | 50 | 算术见 T4.2 |
| M4 微调 ckpt | **45** | N3/N5 口径:2 份 resume 全态(1B 全量微调 + AdamW 状态 ≈12–14GB/份 ≈ 24–28GB)+ 1 份 best model-only + T4.5 候选 2–3 份 model-only(≈2–4GB/份)|
| experiments/ logs/ state/ | 10 | — |
| **已分配小计** | **~372(上限 392)** | |
| **缓冲** | **~193–213** | 下载瞬态:372 + 0.10 zip ≤130 ≈ **502GB 峰值**,仍在 585 内 |

**明确不下载**:Bench2Drive Base/Full、carla_garage 全量、LEAD、SimLingo 全量数据;SimLingo 子集调试单批 ≤10GB 经 CP3 批准。

水位线:≥80% 告警停新下载;≥90% 硬停写盘,生成清理任务卡(禁清 EXP)。

## 6. 日志与实验记录规范(N4 增训练过程指标)

- 每个后台任务:`logs/T<x.y>.log`;崩溃现场改名 `.log.1` 不覆盖。
- 结果指标:`experiments/EXP-<id>/{config.yaml, metrics.json, notes.md}`;config.yaml 必含:模型/数据版本、仿真器版本、画质、`dt`/`sync_mode`、交通配置、相机对齐清单、GPU、种子;对比三件套 EXP 互链。
- **训练过程指标(N4)**:训练 logging 一律本地——wandb 改 `mode=offline` 或直接禁用,替换为 CSV/JSONL logger(T1.0 移植项;wandb 离线模式为官方支持,见 [wandb environment variables 文档](https://docs.wandb.ai/guides/track/environment-variables);SimLingo 默认在线 wandb 且 "Login is required",[README · Training](https://github.com/RenzKa/simlingo));loss/lr/grad norm/吞吐按 step 落 `EXP-<id>/train_metrics.jsonl`,**随训练实时落盘**(M5 曲线数据源);T4.4 判据含此文件存在且持续追加。
- `state/STATUS.md` 每轮从任务卡强制重建。
