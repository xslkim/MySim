# 02 — 执行计划:M0–M5 任务卡

> 版本 v5(终稿)· 2026-08-27 · 第 5 轮(依据第 4 轮评审修订;评审过程记录未入库,发现以正文条款为准)
> 勘误 2026-08-27:依据 `docs/04-doc-review.md` 修正引用与环境事实。
> v5 变更:T2.2/T2.6 tick 记录字段清单 + 双实现共享同一核心判定纯函数模块(R4-N4);T3.0 初步 MDE 前移回填、T3.5 MDE 终版 + KID-vs-ΔDS 相关性初版(R4-N1/N2);T4.5 选优规则终稿(R4-N3);T4.0 增量模式判据(R4-N5);T5.1 相关性终版、T5.2 limitation 固定节(R4-N2);附录增 CP3 扩容分支预算(R4-N1)。
> 每张任务卡:输入 / 输出 / 完成判据 / 预计时长 / 占用资源 / 失败重试 / 串并行 / 人类门禁。执行期实体化为 `state/tasks/T<x.y>.md`。

## 0. 通用条款

- **同步模式**:一切闭环评测/采数/成对采图走 `synchronous_mode=True` + `fixed_delta_seconds`,默认 0.05(20Hz),TM 同步开启;UE5 跟不上(T0.5 判定)两侧统一 0.1(10Hz)并记录。config.yaml 必含 `dt`/`sync_mode`。
- 所有评测/采数支持 `--resume-from`;server 崩溃自动重启,单路线重试 ≤3 次;模型服务崩溃同样自动重启续跑;长任务按心跳回写 progress。
- **训练中断恢复(N3)**:ckpt 含完整训练态;中断从最近 resume ckpt 自动拉起;损失上限 = ckpt 间隔(≤0.5 epoch 或 2h);OOM 降档一律从最近 ckpt 重启记 notes(禁热切换)。
- **训练 logging(N4)**:一律本地落盘(wandb offline 或禁用 → CSV/JSONL),过程指标实时写 `EXP-<id>/train_metrics.jsonl`。
- 凡产出指标的任务,判据必含 `experiments/EXP-<id>/` 三件套。
- 触及 AGENTS.md"关键决策"的偏离一律转人工。
- **对比实验口径**:跨仿真器对比只在 T2.3 对齐路线集 + T2.2 系数集(经 T2.6 交叉验证)+ 同一 dt + 同交通配置下进行;Bench2Drive 220 仅 M1 sanity。
- **统计口径(v5)**:显著性判定一律挂 MDE(T3.5 回填);zero-shot 掉分与微调回收同标准——**幅度 <MDE 时只能报"在检验力 X 下未观察到显著差异"**(R4-N1);ckpt 选择规则预先钉死(T4.5,R4-N3)。

---

## M0 环境验证(env-agent;目标墙钟 2–3 天)

### T0.1 WSL2/Windows 基座准备 [串行,人类半参与]
- 输出:`state/windows-actions.md`(`.wslconfig`:memory=32GB、processors=14、swap=16GB;防火墙;mirrored 备选命令;开机自启任务计划模板);WSL2 `nvidia-smi` 透传验证。
- 判据:WSL2 内存 ≥32GB;双侧 nvidia-smi 读数差异记录;C:/D: 盘位与 vhdx 登记(必要时迁移步骤进 windows-actions);宿主 IP 获取脚本验证;目录骨架建立。时长 0.5 天;资源 D。

### T0.2 下载安装 CARLA 0.10.0 [与 T0.3 并行]
- 输出:`C:\carla\CARLA_0.10.0\`,zip 已删。Windows 侧 `curl.exe -C -` + 7z;WSL 仅校验;**校验分支:有官方 sha256 校验散列,无则文件大小 + 启动冒烟替代**。
- 判据:`CarlaUE5.exe` 存在;瞬态峰值未触发 80% 水位;登记占用。墙钟 2–6h;资源 D。

### T0.3 下载安装 CARLA 0.9.15 [与 T0.2 并行]
- 同 T0.2(含校验分支);判据:`get_available_maps()` 打印登记,Town10HD 缺失则执行 AdditionalMaps 导入步骤。墙钟 1–2h。

### T0.4 三 conda 环境(+ MindDrive 临时 env 约定)[下载期间并行]
- 输出:`state/envs/*.yml`;`mysim-simlingo`/`mysim-automot`(py3.10)内 `(12,0)` + matmul 冒烟;`carla==0.9.15` cp310 安装记录;`mysim-automot` 按官方 requirements.txt 钉版。
- 判据:互不串包;`mysim-ue5` 内 `carla-ue5-api` import 通过;SimLingo 官方 environment.yaml 不可用记入"已知坑"指向 T1.0;MindDrive 旁支归属临时 env `mysim-minddrive`(py3.10,归档即删)。时长 0.5 天;资源 D。

### T0.5 UE5 冒烟 + 0.10 能力探测 [依赖 T0.2、T0.4]
- 探测清单:全传感器(RGB/depth/seg/topdown/**LiDAR**)、交通灯/标志 API、TM 接口、天气接口、sync/dt 可用性。
- 判据:spawn + RGB 100 帧 + autopilot 5min 无崩溃;20Hz 同步跟随测试;5min RGB 流吞吐/丢帧/RPC 延迟;server 独占显存/RAM 实测;同存实测用合成负载法(8GB/13GB buffer);**CP0 门禁实测:stress-ng 压 WSL 至 28–32GB + UE5 server 运行态,对宿主空闲 ≥6GB 判定;降档则重测最坏稳态 S 并登记(告警线 = S−2GB)**;显存以 `powershell.exe nvidia-smi.exe` 为准。时长 1 天;资源 B(短时多次);3 败升级。

### T0.6 UE4 冒烟 [与 T0.5 经锁串行]
- 同构(端口 2010;同步跟随 + 流吞吐 + 显存/RAM 实测含 8GB 合成负载)。时长 0.5 天;资源 C。

### T0.7 登记与 CP0 [人类门禁]
- 输出:env-registry 完整;AGENTS.md diff 草稿;windows-actions 清零。判据见 `00-overview.md` §6。

---

## M1 UE4 基线复现(eval-agent;与 M2 并行;目标 3–5 天)

### T1.0 SimLingo 推理/训练栈移植(关键路径隐性上游)
- 输入:官方 `environment.yaml`(锁 py3.8.18/torch2.2.0/flash-attn 2.7.0.post2/transformers 4.46.3,[原文](https://raw.githubusercontent.com/RenzKa/simlingo/main/environment.yaml));`mysim-simlingo` 骨架。
- 工作内容:依赖升版钉死;**训练 logging 改离线**(wandb `mode=offline` 或禁用 → CSV/JSONL;官方默认在线 wandb 且 "Login is required",[README](https://github.com/RenzKa/simlingo));ckpt 加载;前向 + 单 batch 训练步冒烟。
- **第一步判据:flash-attn 冒烟**(sm_120+WSL2 有失败记录,[flash-attention#2168](https://github.com/Dao-AILab/flash-attention/issues/2168)),失败立即 `sdpa` 回退记坑。
- 完成判据:ckpt 加载无 missing/unexpected keys + 前向维度正确数值有限 + 单 batch 训练步无 OOM + `train_metrics.jsonl` 实时落盘;功能正确性由 T1.2 兜底;移植记录落 notes。时长 1–2 天;资源 D 主 + 短时 C;失败升级 R11。

### T1.1 Bench2Drive + SimLingo 评测 harness 装配 [依赖 T1.0]
- 输入:仓库锁 commit;**Bench2Drive 钉 v0.0.3**。输出:评测入口脚本。
- `PythonAPI` 纯 Python 目录拷入 WSL ext4 再设 PYTHONPATH(不跨 `/mnt/c`)。
- 判据:harness 加载路线并连 UE4 server;**3 条路线 leaderboard 空场景冒烟通过**(T3.0 前置)。时长 0.5–1 天;资源 D。

### T1.2 SimLingo 官方权重评测(sanity check)[GPU 长任务]
- 输入:ckpt(记 HF commit)、Bench2Drive v0.0.3 220 路线。输出:`EXP-…` DS/SR 明细。
- 流程:20 路线冒烟 → 全量 220;**首跑完成真实模型 + UE4 server 同存显存实测回填**。
- 判据:对照 85.07±0.95/67.27±2.11(论文 Table 2,3 seeds);±3 DS 内或解释;**只作 sanity,不进 M5 对比表**。墙钟 8–18h;资源 C。

### T1.3 AutoMoT 官方权重评测 [锁串行]
- 同构;仓内 vendored leaderboard harness;参考值钉 87.34(README)/89.42(HF 卡)注明来源。墙钟 10–20h;资源 C。

### T1.4 (可选旁支)MindDrive torch 2.7 移植 [timebox 2 天,可砍]
- env:临时 `mysim-minddrive`(T0.4 约定),归档后删除。判据 = 5090 前向通过且输出维度正确;失败归档(R3)。

### T1.5 基线汇总 + CP1 [人类门禁]
- 输出:基线表(EXP-id 互链,参考值带方差来源)。

---

## M2 UE5 闭环基建(eval-agent;与 M1 并行;目标 7–9 天)

### T2.1 0.10 route 执行器 + agent socket 接口 [串行;CPU 重]
- 输入:HiDrive 仓库(许可:学术研究免费;参照其 leaderboard 移植层)、T0.5 探测报告。
- 输出:`tools/ue5harness/route_executor.py` + **agent socket 接口规范**:
  - **payload schema 显式含 SimLingo `run_step` 全输入**:RGB、车速、next-2 目标点——含 route 稠密化与前视点计算,对齐 leaderboard RoutePlanner 行为;
  - 每步推理**超时可配置**(默认 2s),**连续 N 次(默认 3)超时才 fail-fast**;
  - 模型服务心跳:harness 每 N tick 向 watchdog 写推理时间戳;
  - 崩溃行为:fail-fast → watchdog 重启模型服务(ckpt 重载)→ 断点续跑;
  - 协议版本号与 schema 落 `tools/ue5harness/README.md`。
- 判据:3 条测试路线无人工干预跑通、记录无 NaN;全程同步模式 + fixed_delta(T0.5 结论),TM 同步;socket 规范经故障注入演示;"复用 HiDrive vs 自写"取舍记录。时长 1.5–2 天;资源 D 主、B 冒烟。

### T2.2 DS/SR 评分器(+ UE4 侧移植;R4-N4 同源性条款)[串行]
- 输出:**单一核心判定/聚合纯函数模块 `scoring_core.py`**(输入为原始量、不依赖任何 CARLA API)+ 两侧 API 适配层(UE5 侧 `scoring.py`、UE4 侧移植版)**共享该核心模块**——T2.6 在 UE4 侧的验证结论由此可传递到 UE5 侧(R4-N4)。
- **tick 记录字段清单(写明,禁走"消费判定结果"捷径)**:碰撞 impulse、交通灯原始状态、车道几何与自车位置、车速、tick 时间戳——两套实现对同一记录**各自从原始量独立判定**违章,才是真对拍。
- 指标:对比主指标统一 Bench2Drive 式 DS(RC × 违章惩罚系数),系数集为跨侧唯一事实源;违章项对齐 Bench2Drive(碰撞/闯红灯/闯停止线/越界/堵路超时,以 T0.5 探测可得项为准,缺项显式列清单);HiDrive LS/ES 仅 UE5 附加报告。
- 判据:注入式单元测试各分项触发正确;trivial 路线 DS=100;UE4 移植版可消费 leaderboard 运行的 tick 原始记录独立重判重算 DS(对拍执行归 T2.6)。时长 1.5 天(含 UE4 适配层);资源 D。

### T2.3 对齐路线集(20 条 × 3 seeds;stretch 50 条与 CP3 联动,R4-N1)[串行]
- 输出:**每侧各一份 XML**(UE4 侧 town=`Town10HD`、UE5 侧重制版 Town10,坐标按侧生成),语义对齐表为唯一映射事实源;eval = 20 条 × 3 交通种子 = 60 route-runs。
- **stretch 条款(R4-N1 联动)**:另备 50 条版本的设计草案(不必建完);**CP3 触发扩容时启用**(判据见 `00-overview.md` §6 CP3 ④);未触发则冻结不建。
- 路线规格:覆盖转弯/变道/路口/直行,单条 ~150m 量级;**声明:纯驾驶路线、无场景触发器**(M5 不对标 Bench2Drive 难度);schema 按 leaderboard/Bench2Drive(T3.0 复用前提);两侧 TM spawn 参与者数量/类型一致并记 config;天气锁白天对齐 preset;声明自研、不衍生 Bench2Drive XML。时长 1 天;资源 D + B/C 冒烟。

### T2.4 trivial agent 全程无人值守(UE5)[GPU 长任务;依赖 T2.1–T2.3]
- 输出:TM autopilot 跑完 eval 全集(60 route-runs),`EXP-…` 出 DS/SR;全程同步模式。
- 判据:无人值守完成;崩溃重启/跳过数在案;墙钟 4–10h;资源 B。失败升级:TM 异常 → 裸 API 巡航备选卡。

### T2.6 评分双实现交叉验证(UE4 侧,CP2 前置;R4-N4 修订)[GPU 短任务;依赖 T2.2+T2.3;与 T2.4 经锁串行]
- 目的:为"同一公式"声称提供证据,赶在 CP2 之前。
- 内容两层:
  1. **无违章路线**:UE4 侧 trivial agent 跑对齐路线子集(≥6 条),官方 leaderboard DS vs 共享核心模块重算 DS 一致;
  2. **违章注入跑**:UE4 侧故意制造碰撞/闯红灯/停车超时各 ≥1 条(**注入手段:脚本强制行为——直接 set_vehicle_control/teleport 制造事件,或等效**);**同一 tick 原始记录(字段清单见 T2.2)分别过两套实现,各自独立判定**,逐分项比对违章判定、惩罚系数与最终 DS。
- ε 口径:**路线级 mean |ΔDS| < 0.5 且各违章分项判定完全一致**;超差修到一致才放行;结果进 CP2 材料。时长 0.5 天 + 墙钟 2–4h;资源 C。

### T2.5 harness 文档 + CP2 [人类门禁]
- 输出:`tools/ue5harness/README.md`(含 socket 协议与 scoring_core 同源性说明)+ CP2 材料(日志/DS/SR/config 可证 dt/sync;**T2.6 交叉验证报告**)。

---

## M3 渲染对比 + zero-shot(依赖 CP1∧CP2;目标 4–5 天)

### T3.0 UE4 对齐路线集基线(复用官方 vendored leaderboard)
- **执行基建来源**:SimLingo 用 T1.1 装配的仓内 harness;AutoMoT 用 T1.3 的;本卡不自建 UE4 执行器。**前置**:T1.1 空场景冒烟已过。
- 输入:T2.3 UE4 侧 XML(20×3)、T2.2 系数集(T2.6 已验证)、T1.2/T1.3 ckpt、白天 preset、同 dt/sync、同交通配置。
- 输出:`EXP-…`(每模型):对齐集 UE4 DS/SR(路线级 60 样本,官方管线原生 DS)+ **重跑噪声标定**(seed-0 子集原样重跑 1 次)+ **初步 MDE(仅 UE4 侧噪声)回填 `STATUS.md` 预警(R4-N1 前移)**——若初步 MDE 已 >5 DS,orchestrator 提前备扩容方案,不等 T3.5。
- 判据:两模型各 60 route-runs + 噪声标定 + 初步 MDE 落盘;config 与 UE5 实验除仿真器版本外逐项一致。时长 0.5 天适配 + 墙钟 8–14h;资源 C。

### T3.1 成对渲染数据集 [GPU,B/C 串行两段]
- 输出:`data/paired/{ue4,ue5}/` 各 ≥5k 张(目标 10k)+ `pairs.json`;**相机对齐清单**(内参复刻 SimLingo 训练相机/曝光锁定/motion blur/tonemapping;分辨率取舍写明与 0.10 "1080p 以下无 motion blur"阈值的关系)。
- 判据:配对完整、元数据齐全;同步模式采图;"语义对齐为度"注明;**场景组标签(路口/直道等)随图落盘**(R4-N2 相关性分析用)。时长 1 天。

### T3.2 域差距指标 [短 GPU]
- **主 KID**([arXiv:1801.01401](https://arxiv.org/abs/1801.01401));FID 仅 ≥10k 张时作辅;不用全参考指标;定性拼图 10 组 + 同侧内部 KID 基线;**按场景组出分组 KID**(路线级/组级对齐 T3.3 掉分表粒度,R4-N2)。
- 判据:可重复;bootstrap 95% CI;分组结果落 `EXP-…`。时长 0.5 天。

### T3.3 SimLingo zero-shot UE5 评测 [GPU 长任务]
- 输入:T3.0 EXP-id(同权重/路线集/系数/dt/交通配置)、M2 harness、eval 集(20×3)。
- 架构:socket 分离(T2.1);相机清单同 T3.1。
- **前置判据:模型服务崩溃注入测试**;**UE5 侧噪声标定**:seed-0 子集重跑 1 次(与 T3.0 对称)。
- 判据:60 route-runs + 标定完成;掉分表(**路线级**,与 T3.2 场景组粒度可对齐)生成;墙钟 6–14h;资源 B。

### T3.4 AutoMoT zero-shot UE5 评测 [GPU 长任务]
- 同构(前置崩溃注入同 T3.3);**LiDAR 分支**:探测不可用 → N/A;可用还须**参数对齐关**(通道/量程/点频匹配训练配置 + preprocess 单帧冒烟),不匹配同样 N/A;通过则评测并附稀释声明。
- 首跑完成真实模型同存实测回填;墙钟 8–16h;资源 B(顶格预案 `01-infra.md` §4.1)。

### T3.5 M3 汇总 + CP3(R4-N1/N2 条款)[人类门禁]
- 输出:
  1. KID 域差距报告(含分组);
  2. zero-shot 掉分表(路线级分布);
  3. **MDE 终版**(双侧重跑噪声 → 配对 bootstrap 最小可检测 DS 差)+ **"MDE vs 预期效应"对账结论与扩容建议**(CP3 ④ 判据的数据源;zero-shot 掉分 <MDE 时的报告口径 = "在检验力 X 下未观察到显著差异",与微调回收同标准,R4-N1);
  4. **KID-vs-ΔDS 相关性分析初版(R4-N2)**:按场景组(或路线)的 Spearman 相关 + bootstrap CI——本设计内唯一间接支撑"掉分与渲染域差距相关(而非纯物理/几何差异)"的统计证据;
  5. HiDrive 锚点(口径差异说明,仅定性);采数档位建议(S/M/L 附论证)。

---

## M4 UE5 采数 + 微调(依赖 CP3;目标 7–10 天)

### T4.0 数据转换器 + 训练侧实读验证(全量采数前的门禁)
- 位置:T4.1 之后、**T4.2 全量采数之前**。
- 输入:T4.1 的 200 帧样本 + 字段清单;SimLingo `simlingo_training` 数据代码。
- 工作内容:实现 0.10 → SimLingo 格式 writer/转换器(目录布局、逐帧 measurements json、索引/划分);处理 **data buckets**(官方 bucket 文件随数据集发布,训练按 bucket 采样,[README · Data buckets](https://github.com/RenzKa/simlingo)/论文 §3.4):用 `carla_get_buckets.py` 生成或验证绕过,结论与配置依据落 notes。
- 完成判据:① T4.1 样本经转换后**用真实 dataloader 跑出 1 个训练 step**;② bucket 生成/绕过结论落盘;③ **增量模式判据(R4-N5):转换器二次调用(追加新样本)后索引/划分文件正确、幂等、可重复实读**——T4.2 边采边转依赖此。
- 时长 1 天;资源 D 主 + 短时 A 冒烟;失败 → 修转换器,**绝不允许带病进 T4.2**(R15:超 1.5 天提前人工)。

### T4.1 采数冒烟(前置字段核实)[GPU]
- 前置:读 SimLingo dataset 类产出必需通道/字段清单,对照 T0.5 探测报告;缺通道即调范围。
- **训练范围默认 (a) 纯驾驶任务**(语言标签生成依赖 PDM-Lite 特权信息,0.10 没有;论文 Table 6 证明纯驾驶可行);(b) 简化 commentary 仅 CP4 批准时启用。
- 输出:200 帧样本 + 可视化 10 张 + 字段映射表(供 T4.0)。时长 0.5–1 天;资源 B。

### T4.2 采数规模运行 [GPU 长任务]
- **口径:驾驶小时 = 存储帧数 ÷ (存储 fps × 3600)**;默认存储率 4fps(dt=0.05 时每 5 tick)。**dt=0.1 分支:存储率改 5fps(每 2 tick)或 2fps,实际值记数据卡与 EXP config**。
- 档位(CP3 签字):S=10h/144k/~25GB/12–14h;**M(默认)=20h/288k/~50GB/24–28h**;L=30h/432k/~75GB/36–42h(需确认磁盘红线)。墙钟 = 驾驶小时 ÷ 实测 RTF + ~15% overhead。
- 输入:CP3 档位、train 路线集、TM autopilot + 向 LEAD 对齐的扰动注入、**T4.0 转换器(边采边转,增量模式已过判据)**。输出:`data/ue5_r1/` + 数据卡。
- 判据:帧数达标、坏帧率 <1%、标签完整、转换产物随时可实读;资源 B 独占;断点续采;TM 异常路段剔除记录。

### T4.3 数据质检 + CP4 [人类门禁]
- 输出:质检报告;CP4 放行才许开训练;CP4 决策全量 vs LoRA(默认全量,依据 T1.0 显存余量)。

### T4.4 SimLingo 微调 [GPU 独占,类 A]
- 输入:官方 ckpt 起步、**T4.0 验证过的数据管线**、`mysim-simlingo`。
- **墙钟推算**:官方 14 epochs × 650k,8×A100 24h → 单 A100 ≈ 47k 样本/h;5090 估 19–38k(30 步冒烟实测);M 档 288k × 2–4 epochs = 0.58–1.15M 样本 → **15–60h**,48h 软顶。
- **resume 协议(N3)**:ckpt 含 optimizer/scheduler/step/sampler 全态;保留 = 2 份 resume 全态 + 1 份 best model-only;中断自动从最近 resume ckpt 拉起(watchdog/orchestrator);**间隔 ≤0.5 epoch 或 2h = 损失上限**;OOM 降档从最近 ckpt 重启记 notes(禁热切换)。
- **选模规则(N5)**:早停与候选选择只用离线 val 指标;训练中不做闭环评测。
- 判据:loss 正常下降、无 OOM 断训;`train_metrics.jsonl` 实时落盘;resume 协议经"主动 kill 续训"演练。

### T4.5 微调版 UE5 评测(选优规则终稿,R4-N3)[GPU 长任务]
- **ckpt 选择规则(预先钉死,记 config)**:候选 = val 最佳/次佳/last 共 2–3 份 model-only ckpt;**默认 val 最佳直接进全量 60 route-runs 进 M5 三档表**;子集筛选(20 条 × 1 seed,每份 2–5h)**仅作 sanity**——仅当筛选显示 val 最佳显著劣于他候选(差 > 双侧重跑噪声)时才换,**换则强制双报**(胜出者全量 + 原 val 最佳子集结果,不追加全量预算);val 为离线指标与闭环 eval 集不相交,默认路径无选择偏差;筛选集与报告集的重合仅在"换"分支触发,故该分支强制附选择偏差声明。
- 输出:三档对比表初稿(路线级分布 + 配对 bootstrap CI);**回收幅度对照 T3.5 MDE 下结论**(<MDE 写"不显著")。
- 墙钟 **12–28h**(sanity 筛选 6–14h + 全量 6–14h);资源 B。

---

## M5 综合对比与报告(analysis-agent;目标 2 天)

### T5.1 对比矩阵汇总 [D]
- 输出:三档 DS/SR 表(对齐路线集 + 同系数集 + 同 dt + 同交通配置,EXP-id 互链;Bench2Drive 220 只在 sanity 附录)+ KID(含分组)+ **KID-vs-ΔDS 相关性终版(R4-N2,三档口径)** + MDE 对照 + ckpt 选择规则可溯 + 变量控制声明;AutoMoT 按 T3.4 走双模型/单模型分支,LiDAR 稀释声明必在。

### T5.2 报告成稿 + CP5 [人类门禁]
- 输出:`docs/03-final-report.md` 草稿;**limitation 固定节(R4-N2,模板预置,CP5 检查存在性)**:显式声明——① UE4↔UE5 差异是渲染 + 物理(PhysX→Chaos)+ 地图重制(Town10 非逐像素)的复合体,**渲染归因只有 KID-vs-ΔDS 相关性层面的间接证据**;② 外推范围限缩"本对齐路线集(20 条 Town10 语义路线)",不声称 Town10 整体、不对标 Bench2Drive 难度;③ 单主模型 / TM autopilot 专家 / 微调数据 ≈ 官方 9% / AutoMoT LiDAR 稀释或 N/A;④ 0.10 固有限制(锁白天、~25 FPS、无场景触发器);⑤ 不显著结果按 MDE 口径陈述,不夸大。

---

## 附:并行/串行总表与 GPU 墙钟求和(v5)

| 流 | 任务 | 并行关系 | GPU |
|---|---|---|---|
| 主线 | M0 → (M1 ∥ M2) → M3 → M4 → M5 | M1∥M2;M3/M4 内各卡经锁串行 | 全部 GPU 任务经锁串行 |
| 旁支 | T1.4 MindDrive | 挂 M1,可砍 | 最低优先级 |
| 横切 | 下载、文档、登记、T4.0 转换器开发 | 与 GPU 任务并行 | D 类不限 |

GPU 串行墙钟(基准):T1.2 8–18h + T1.3 10–20h + T2.4 4–10h + T2.6 2–4h + T3.0 8–14h + T3.1/T3.2 ~6h + T3.3 6–14h + T3.4 8–16h + T4.2 24–28h + T4.4 15–60h + T4.5 12–28h ≈ **101–214h**;**CP3 扩容分支(R4-N1)另 +15–35h**(stretch 50 条或 seeds 3→5,仅触发时计入);总日历 5–8 周见 `00-overview.md` §7。
