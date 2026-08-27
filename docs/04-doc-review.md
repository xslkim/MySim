# 04 — 文档评审反馈(v1)

> 评审时间:2026-08-27 · 评审方式:全文通读 + 跨文档一致性核对 + 关键引用抽查(PyPI / GitHub raw)+ 本机实测(lscpu / df / free / `.wslconfig` / powershell / git)
> 评审对象:README.md、AGENTS.md、`docs/01-research-report.md`(v4)、`docs/02-roadmap.md`(v3)、`docs/plan/00–03`(v5)
> **总体结论:方案本体(plan v5)质量高,本轮未发现设计层新漏洞;主要问题集中在「文档与本机环境事实脱节」和「评审引用链断裂」两类,启动 M0 前应先清掉 3 个高级别项(均为文档层修改,零代码)。**

## 0. 用户拍板记录(2026-08-27,本反馈据此编写)

| # | 问题 | 决定 |
|---|---|---|
| 1 | `docs/plan/_reviews/` 评审记录缺失(从未提交进 git) | **已丢失,无法恢复** → 按 §3 建议改写引用 |
| 2 | AGENTS.md 与 plan v5 / 实测环境冲突 | **只在本文档记录,用户手动修改** → 建议改法见 §2 |
| 3 | server 盘位(D: 装不下 130GB 的 0.10) | **改到 `C:\carla`** → 连带修订见 §6 |

---

## 1. 本机实测 vs 文档环境事实【高】

| 项 | 文档口径 | 实测(2026-08-27) | 影响 |
|---|---|---|---|
| 宿主物理内存 | 54GB(AGENTS.md、plan 01 §4.3 的闭合算术均以 54 为总数) | **63.4GiB(≈64GiB 物理)**,powershell `TotalPhysicalMemory`;WSL 内 `free` 显示的 54Gi 是 cap 后的结果 | §4.3 全部算术基数错;好消息是结论方向不变且更宽松(见下) |
| `.wslconfig` | "须调 ≥40GB"(AGENTS.md);T0.1 拟生成 memory=32GB/processors=14/swap=16GB | **已存在**:`memory=56GB`、`processors=16`、`swap=32GB` | 当前 56GB 配置在最坏情形下**不闭合**(63.4−56=7.4GiB < 宿主需求 14–24GiB);T0.1 的动作是"降档 56→32",不是"新调" |
| server 盘位 | `D:\carla\`(01-infra §2.1) | **D: 仅剩 61.2GB**,装不下 0.10(130GB)+ 0.9.15(30GB)+ zip 瞬态(≤130GB,峰值约 290GB);**C: 剩 794.3GB** | 高级别:按原方案 T0.2 下载必然失败;已拍板改 C:(§6) |
| CPU | "16 核"(AGENTS.md 环境表) | WSL 侧 16 vCPU(`processors=16` cap 所致);265K 硬件为 **20 核 20 线程**(Arrow Lake 无超线程) | "16 核"是 WSL cap 不是硬件全量;plan 的 processors=14 仍合理(Windows 侧始终可用全部核心) |
| 显示适配器 | 文档未提 | 在册 3 个虚拟显示适配器:**Todesk Virtual Display / OrayIddDriver / Microsoft Remote Display** | 本机常经远程桌面访问。"窗口模式 server 依赖交互会话"(R6/R10/开机自启 runbook)在远程会话断开/注销后的行为未验证——虚拟显示适配器可能反而是保命项,但需实测 |
| GPU | RTX 5090 32GB | ✓ 型号在册(WMI `AdapterRAM` 显示 4GB 是 32 位字段限制,非真实显存,不影响结论) | 无 |

**RAM 闭合重算(以实测 63.4GiB 为基数)**:宿主最坏需求 = Win 6–8 + UE5 server 8–16 = 14–24GiB。
- WSL cap 32GB → 宿主余 31.4GiB > 24,**闭合且余量约 7.4GiB**,plan 的 32GB 推荐成立;28GB 降档预案大概率用不上,但 CP0 门禁(stress-ng 实测)仍应保留作经验证。
- AGENTS.md 的"≥40GB"在 63.4GiB 主机上**反而不闭合**(63.4−40=23.4 < 24)——该建议必须删除,以 plan §4.3 为准。
- 01-infra §4.3 的算术行("54−32=22<24 不闭合→降 28GB")应按 63.4 基数重写;结论(32GB 可行)不变。

## 2. AGENTS.md 待修订清单(用户选择自行修改,此处只记录)

| # | 位置 | 现文 | 建议改为 |
|---|---|---|---|
| 2.1 | 本机环境事实·内存 | "54GB 内存(`.wslconfig` 须调 ≥40GB)" | "宿主物理 64GiB(可见 63.4GiB);`.wslconfig` 当前 memory=56GB,T0.1 降为 32GB(闭合算术见 docs/plan/01-infra.md §4.3)" |
| 2.2 | 本机环境事实·磁盘 | "磁盘可用 ~585GB(0.10 包 130GB + 0.9.15 包 ~30GB,数据集按需下载)" | 三盘口径:"C: 剩 ~794GB(CARLA server 落位 `C:\carla\`);D: 剩 ~61GB(弃用);WSL vhdx 所在盘(1.5T)剩 ~582GB = 数据预算 585GB" |
| 2.3 | 本机环境事实·CPU | "16 核 CPU" | "20 物理核(Core Ultra 7 265K,无超线程);WSL 当前 processors=16" |
| 2.4 | 硬性规则 #1 | "三个 conda 环境严格分离:UE5 客户端(py≥3.11)/ UE4 客户端(**py3.8** + carla==0.9.15)/ 训练(py≥3.10 + torch≥2.7)" | "conda 环境拓扑以 `docs/plan/01-infra.md` §3 为准:常驻 3 个 —— `mysim-ue5`(py3.11 + `carla-ue5-api==0.10.0`)/ `mysim-simlingo`(py3.10 + torch2.7.1+cu128 + `carla==0.9.15`,推理+评测+微调同 env)/ `mysim-automot`(py3.10 + AutoMoT 官方栈);临时 `mysim-minddrive`(T1.4,归档即删)。`carla` 与 `carla-ue5-api` 永不装在同一环境" |
| 2.5 | 已知坑(建议新增一条) | — | "远程桌面会话(Todesk/向日葵虚拟显示)与窗口模式 CARLA server 的兼容性未验证;CP0 冒烟须含'远程会话断开后 server 存活'项" |

理由:AGENTS.md 是每个新 agent 的第一读物(协作约定明文),而 2.4 的"py3.8"已被 plan 自己核实的 cp310 wheel + AutoMoT 官方 py3.10 栈推翻(见 §5.1),env-agent 若先读 AGENTS.md 会直接装错环境;2.1/2.2 的数字则被本机实测推翻。

## 3. `_reviews/` 引用链断裂【高】(已确认丢失,无法恢复)

- **事实**:git 全历史从未收录 `docs/plan/_reviews/`;README("全部评审记录见 docs/plan/_reviews/")是死链;4 份 plan 文档头部均写"依据 `docs/plan/_reviews/round-4.md` 修订"。
- **影响评估:有限**。R4-N1~N5 的实质内容已全部条款化进 v5 正文(头部变更行 + CP3/T2.2/T2.6/T3.5/T4.0/T4.5/T5.2/R16/R17 均在),丢失的只是评审过程记录,方案可执行性与可审计性主干未断。
- **建议**:① 4 份 plan 头部"依据 round-4.md 修订"改为"依据第 4 轮评审(过程记录已佚,发现以正文条款为准)修订";② README 删除该链接或改为"经 5 轮方案-审查迭代(过程记录未入库)";③ 若后续重开评审轮,产物直接入库,不再引用仓外文件。

## 4. 跨文档一致性问题

| # | 级别 | 位置 | 问题与建议 |
|---|---|---|---|
| 4.1 | 中 | `02-roadmap.md` M0 vs `01-infra.md` §1 | roadmap 写"连通 **localhost**:2000/2010",infra 明文"**禁止硬编码 localhost**,NAT 模式须用宿主 IP 动态获取"。建议 roadmap 改为"宿主 IP(脚本动态获取):2000/2010" |
| 4.2 | 中 | `01-research-report.md` §0 第 4 点、§2.1 表 | "carla 0.9.15 客户端锁 Python 3.7/3.8"是**过期错误**:PyPI 实测有 cp37/38/39/**310**(linux+win)wheel(§5.1)。v2 头部保留注只覆盖"首选 0.9.15"结论,未覆盖此错误;该错误还传染了 AGENTS.md 规则 #1(§2.4)。建议 §0/§2.1 加一行更正注 |
| 4.3 | 中 | 分数口径四处不一 | SimLingo 参考分:85.94(§0)/ 85.9(§3.2)/ 85.1(§9.1)/ 85.07±0.95(论文 Table 2,3 seeds;plan T1.2/CP1 已钉此口径)。建议全文统一引用论文 Table 2 口径,README/转述分注明"README 口径,以论文为准" |
| 4.4 | 低 | `00-overview.md` §7 与 `02-execution.md` 附录(两处同源) | GPU 串行墙钟逐项加和实测为 **103–218h**,文档写 101–214h(低 2 / 高 4)。量级无碍,建议订正保持"同源"声称成立 |
| 4.5 | 低 | `02-execution.md` 章节顺序 | T2.5 排在 T2.6 之后、T4.0 编号在 T4.1 之前(执行顺序文中已解释,纯观感)。可在 M 启动时顺手重编号,或保持现状 |
| 4.6 | 低 | train 路线集无归属卡 | roadmap M2 说"≥20 条,训练/验证分离",但 T2.3 输出只写 eval 集(20×3);T4.2 输入需要"train 路线集"却无产出卡。建议 T2.3 输出补一句"另产出 train 路线集(与 eval 集分离,每侧 XML)" |
| 4.7 | 低 | LEAD 扰动设计无承接卡 | "TM autopilot + 向 LEAD 对齐的扰动注入"只作为 T4.2 的输入出现,没有任何任务卡的输出物是扰动设计文档。建议 T4.1 输出补"扰动注入设计说明(参照 LEAD,落 notes)" |
| 4.8 | 低 | "≈官方 9%" 分母缺失 | 执行摘要/R8/T5.2 三处用"微调数据 ≈ 官方 9%",但官方数据集规模(分母)从未在任何文档给出。建议在 T4.2 或执行摘要写明一次算术 |
| 4.9 | 低 | `00-overview.md` §3 DAG | T3.3 输入含"相机清单同 T3.1",即对 T3.1 存在软依赖,但 DAG 将 T3.1/T3.2 与 T3.3/T3.4 画成并行分支。执行时注意:T3.3 开跑前相机对齐清单须冻结 |
| 4.10 | 低 | `02-roadmap.md`(v3)整体 | 未包含 CP0–CP5 人类门禁结构,M4 完成判据也无 MDE 口径(plan 已细化为"对照 MDE 下结论")。建议 roadmap 头部加一行"执行细节与人工门禁以 docs/plan v5 为准" |

## 5. 关键引用抽查结果

| 引用 | 结果 |
|---|---|
| PyPI `carla==0.9.15` wheel(plan 01-infra §3 的立论基础) | ✅ 实测 9 个 wheel:cp27(l)/cp37(l+w)/cp38(l+w)/cp39(l+w)/**cp310(l+w)**。**证实 plan,证伪调研报告 §0/§2.1 的"锁 py3.7/3.8"**(→ §4.2) |
| AutoMoT `requirements.txt`(release 分支) | ✅ 标题"AutoMoT + Bench2Drive requirements";Python 3.10 / CUDA 12.8;torch 2.7.1+cu128、flash-attn 2.8.3、transformers 4.57.3,与 plan 引用一致。**小注**:`carla` 不在该文件内(单独安装),plan env 表中 `mysim-automot` 的 `carla==0.9.15` 是本项目追加而非官方钉版——T0.4 落记录时注明即可 |
| SimLingo `environment.yaml` | ✅ py3.8.18 / torch2.2.0 / transformers4.46.3 与 plan/R11 一致;⚠️ **flash-attn 不在该文件**(仓库 requirements.txt 路径 404)。R11/T1.0 写"flash-attn 2.7.0.post2(environment.yaml)"出处存疑,T1.0 执行时以仓内实际文件为准 |

## 6. 盘位改 C: 的连带修订(已拍板:server 落 `C:\carla\`)

1. `01-infra.md` §2.1 安装表:`D:\carla\CARLA_0.10.0\`、`D:\carla\CARLA_0.9.15\` → `C:\carla\…`;T0.1 盘位登记对象改 C:/D:(D: 记为"已评估弃用,余 61GB")。
2. **磁盘预算表拆两侧**(现表把 server 的 130+30 记在 WSL 585GB 预算内,盘位改 C: 后口径应分离):
   - Windows C: 侧:0.10 解压后 130 + 0.9.15 30(最多 50)+ zip 瞬态 ≤130 → **峰值 ~290GB / 稳态 ~160GB**,对 C: 的 794GB 充足(下载解压仍在 Windows 侧执行,纪律不变);
   - WSL vhdx 侧:原 372 − 160 = **~212GB**(36 envs + 20 缓存 + 10+13+8 权重 + 10 B2D + 10 成对渲染 + 50 自采 + 45 ckpt + 10 experiments),对 582GB 水位约 36%,**无 zip 瞬态**,余量比原方案大幅改善;
   - 水位线(80%/90%)监控对象明确为 **vhdx 所在盘的 df**。
3. T0.1 顺带坐实 vhdx 物理位置(1.5T 盘是独立盘还是 C: 上的大 vhdx 未验证):若与 C: 同盘,在已知坑记录"采数期 server 读 + dataloader 读同盘 I/O 竞争"提示。
4. `.wslconfig` 动作性质变更:由"生成新配置"改为"**56GB→32GB 降档**"(processors 16→14、swap 32→16 一并落),写进 windows-actions 时注明。

## 7. 核对无误项(本轮复核过,后续评审可免查)

- AGENTS.md"关键决策"与 plan v5 无冲突:模型选型(SimLingo 主 / AutoMoT 不微调 / MindDrive 备选)、双仿真器 Windows 原生、闭环自建、排除项完全一致。
- RAM 闭合推理结构、磁盘表小计(372/392/502)、GPU 任务分级互斥、T4.4 吞吐推算(8×A100→单卡 47k/h→5090 19–38k→15–60h)、T4.5 墙钟(12–28h)、T4.2 帧数算术(20h×4fps=288k)、传感器带宽(1280×720×3≈2.75MB/帧,20Hz≈55MB/s)——算术全部复核通过。
- 评分双实现交叉验证设计(T2.2 原始量字段清单 + 共享 scoring_core + T2.6 注入对拍)、统计治理(MDE 前移/CP3 对账/R16/R17/limitation 固定节)是本方案最扎实的设计,无需改动。
- CP 时间线与各里程碑目标天数加和自洽(M1∥M2 并行轴下 5–8 周成立)。
- 唯一的设计层固有局限(渲染+物理+地图复合差异不可分解)方案已自知自限(limitation 条款 + KID-vs-ΔDS 仅作间接证据),无可进一步修复项。

## 8. 启动 M0 前建议动作清单(按序,全部为文档层)

1. 手动修订 AGENTS.md(§2 清单,5 处)。
2. 改写 4 份 plan 头部与 README 的 `_reviews` 引用(§3)。
3. `01-infra.md` §2.1/§5 盘位与磁盘预算改 C: 口径(§6)。
4. `01-research-report.md` §0/§2.1 加 py 版本更正注(§4.2)。
5. (可选)`02-roadmap.md` localhost 措辞与指针行(§4.1/§4.10)。
6. 其余低级别项(§4.4–4.9)可留待下次文档迭代,不阻塞 M0。
