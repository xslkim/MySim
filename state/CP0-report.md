# CP0(M0 出口门禁)材料 — 提交用户确认

日期:2026-08-28。范围:docs/plan v5 里程碑 M0(T0.1–T0.7)。结论:**M0 技术项全部通过,4 项人工动作待用户执行/拍板**。

## 一、任务卡收口

| 卡 | 结果 | 关键证据 |
|---|---|---|
| T0.1 实测登记 | done | env-registry 网络/GPU/宿主/盘位节 |
| T0.2 0.10 安装 | done | `C:\carla\CARLA_0.10.0\Carla-0.10.0-Win64-Shipping\CarlaUnreal.exe`,21GB,15208 文件 zip 校验无损 |
| T0.3 0.9.15 安装 | done | `C:\carla\CARLA_0.9.15\WindowsNoEditor\CarlaUE4.exe`,29GB,AdditionalMaps 合并后 Town01–07/10HD/11/12/13/15 全在 available_maps 坐实 |
| T0.4 三 conda env | done | state/envs/*.yml;互不串包核查;torch cu128 cap(12,0) matmul 过;flash-attn 2.8.3 import 过 |
| T0.5 UE5 冒烟 | PASS | logs/smoke-ue5.json:同步 42.3 FPS(2.1×)、RGB 40.4 FPS 零丢帧、5min 无崩;probe 14 传感器全 ok;显存门禁 +8/+13GB PASS |
| T0.6 UE4 冒烟 | PASS | logs/smoke-ue4.json:同步 97.6 FPS(4.9×)、RGB 110 FPS 零丢帧、5min 无崩;20 地图全 |
| T0.7 汇总/本材料 | 本文件 | — |

## 二、重大发现(影响既定约定)

1. **端口约定必须改**:2000–2002/2010–2012 落在 winNAT 保留段 1921–2020,server bind 即崩(T0.5 PDB 符号化取证,不是偶发)。已临时落位 **UE5=2021 / UE4=2031** 并双冒烟通过 → **A4 待拍板**。
2. **RAM 门禁 56GB 口径 FAIL(实测)**:WSL 压 30GB + UE5 server 时宿主空闲仅 2.9–3.2GiB。A1 降档 32GB 从"建议"升级为"必须";降档后复测(我来做,需你先执行 A1)。
3. **显卡选择两侧不对称**:UE5 用 `-graphicsadapter=2`、UE4 必须用 `-graphicsadapter=0`(IddCx 虚拟卡只进 UE4.26 的 DXGI 枚举)。错卡特征=5090 显存平躺+FPS 骤降 7×,已进 AGENTS.md 已知坑,watchdog 已修。
4. 远程会话兼容性:Todesk/向日葵会话内双冒烟全程通过;"断开后存活"(A3)未测。

## 三、用户动作收口(2026-08-28 全清)

- **A1** 已降档 32GB/16/16GB → 复测 **PASS**(WSL 压 28GB + UE5 server,宿主空闲 12.9–14.5GB ≥6GB;释压后 60s 冒烟回归 PASS,41.9 FPS 零丢帧)
- **A2** 防火墙:实测不需要,跳过
- **A3** 远程断连后 server 存活,通过
- **A4** 拍板接受 **UE5 2021–2023 / UE4 2031–2033**;AGENTS.md 端口行、watchdog、env-registry 已同步
- 复测副产物(新坑,已登记):adapter 索引重启后漂移(UE5 侧 =2 改 =0 才选中 5090),watchdog 内置 adapter 轮询 + nvidia-smi 显存增量校验;winNAT 保留段重启后漂移,2021/2031 当前空闲

## 四、数字基线(供后续对比实验)

| 指标 | UE5(0.10) | UE4(0.9.15) |
|---|---|---|
| 同步 FPS(Epic 720p Town10HD_Opt) | 42.3 | 97.6 |
| RGB 720p 吞吐 | 40.4 FPS 零丢帧 | 110.1 FPS 零丢帧 |
| server 显存 | ~9GB | ~8.1GB |
| 模型共存(+13GB torch) | PASS(29.5/32.6GB) | 未测(余量更大,风险低) |
| RPC 延迟 | 43ms | 30ms |

## 五、M1 入口条件自评

双 server 可起可连可跑同步;三 env 就位;watchdog/smoke 工具链经过实战;数据预算 582GB 未动。**A1/A3/A4 齐后 M1(SimLingo UE4 复现)可开。**
