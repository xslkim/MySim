# env-registry.md — 环境登记(CP0 时合入 AGENTS.md)

## 网络
- 宿主 IP(WSL→Windows):**172.28.96.1**(脚本动态获取:`ip route show | awk '/default/{print $3}'`,禁硬编码)
- 端口:**UE5 2021/2022/2023;UE4 2031/2032/2033**(CP0 拍板;旧 2000/2010 段被 winNAT 保留);TM 两侧默认 8000
- localhost 模式:NAT(mirrored 未启用)

## GPU(双侧 nvidia-smi 一致)
- RTX 5090 32607MiB;基线占用 6887MiB(2026-08-27 17:36 读数,有两 python 进程在跑)
- 显存观测以 `powershell.exe nvidia-smi.exe` 为准

## 宿主(2026-08-28 更新)
- 物理 RAM 63.4GiB;CPU 20 核无 HT;虚拟显示适配器 ×3(远程桌面场景;A3 断连存活已验证)
- `.wslconfig` 当前:**memory=32GB / processors=16 / swap=16GB**(A1 已生效;processors 保留 16)

## 盘位(2026-08-27)
- C: 795GB 余 → server 落 `C:\carla\`(0.10 解压后 ~130GB + 0.9.15 ~30GB)
- D: 62GB 余 → 弃用
- WSL vhdx:**G:\wsl\Ubuntu-22.04**(G: 1.5T 独立盘,余 582GB = 数据预算;与 C: 不同盘,无同盘 I/O 竞争)

## CARLA 安装(T0.2/T0.3 完成后回填)
- 0.10.0: 已装(2026-08-28),`C:\carla\CARLA_0.10.0\Carla-0.10.0-Win64-Shipping\CarlaUnreal.exe`,占用 21GB
- 0.9.15: 已装(2026-08-28),`C:\carla\CARLA_0.9.15\WindowsNoEditor\CarlaUE4.exe`,29GB(含 AdditionalMaps;Town01–07/10HD + Town11/12/13/15 大图子目录;zip 结构不带 WindowsNoEditor 壳,已 robocopy 合并归位)
- C: 余量 741GB(双 server 落位后)

## conda envs(T0.4 已完成,2026-08-28)
- mysim-ue5(py3.11.15):carla-ue5-api 0.10.0 + numpy 1.26.4 + opencv-headless 4.10.0.84 + shapely 2.0.0
- mysim-simlingo(py3.10.20):torch 2.7.1+cu128 + carla==0.9.15 + numpy 1.26.4;matmul/cap(12,0) 冒烟通过
- mysim-automot(py3.10.20):同 torch 栈 + carla 0.9.15 + 官方 requirements 钉版 + flash-attn 2.8.3 预编译轮(sm_120 kernel 冒烟归 T1.x)
- 导出快照:state/envs/*.yml;HF_ENDPOINT=https://hf-mirror.com 已入 ~/.bashrc

## 实测回填区(T0.5/T0.6)
- FPS / 显存 / RAM / 同步跟随 / API 探测:待填

### T0.5 实测(2026-08-28,UE5 server @ C:\carla,Town10HD_Opt,Epic 1280×720 窗口)
- **端口重大发现**:TCP 2000/2010–2012 全落在 winNAT 动态保留段 `1921–2020`(`netsh int ipv4 show excludedportrange tcp`),bind 直接 AccessDenied —— 这是 0.10 server 首次启动 6 连崩(0xe06d7363)的根因(FCarlaServer::Start → rpc::server bind 抛 std::system_error,经 PDB 符号化+minidump RTTI 取证)。**本次用 2021 跑通(RPC=2021,TM=8000)**;端口约定需修订(建议 UE5 2021–2023 / UE4 2031–2033,或管理员释放保留段)。
- adapter:-graphicsadapter=0/=2 均选中 RTX 5090(崩溃 XML RHI.AdapterName 字段;IddCx 虚拟卡不进 UE 的 DXGI 枚举);正式跑用 =2;Shipping 无 -log 不落 CarlaUnreal.log,Saved 在 %LOCALAPPDATA%\CarlaUnreal\Saved。
- 启动:端口修复后 RPC 就绪 6s(缓存热);包完整性经 zip 中央目录比对 15208 文件无损。
- API 探测:14 传感器/weather/交通灯×15/TM(8000)/sync/spectator 全 ok,无缺失;spawn 点 155;地图仅 Mine_01+Town10HD_Opt。
- 同步跟随:42.3 FPS(dt=0.05 目标 20,200 tick);60s 短测基线 45.2 FPS。
- RGB 相机吞吐:1280×720 fov110,12317 帧/304.6s ≈ 40.4 FPS,0 丢帧。
- RPC 延迟(WSL→宿主):43ms。
- RAM 门禁(56GB 口径):server 运行基线 host free ~23GiB;WSL 压 30GB 后 host free 2.9–3.2GiB(<6GB FAIL)→ 降档 32GB 必要性坐实;释放后恢复 32GiB。32GB 口径待 T0.1 用户降档后复测。
- 显存门禁:server 占 ~9GB;+8GB torch → 24.4GB 同步 43.5FPS;+13GB torch → 29.5/32.6GB 同步 43.0FPS,server 全程存活,劣化 <5%(噪声内);13GB 共存可行但余量仅 ~3GB。
- 客户端坑:carla-ue5-api 0.10.0 结束恢复异步 apply_settings → C++ abort(exit 134),server 无感;smoke_carla.py 已改为先落盘再恢复。
- 观测:logs/t05-observe.log(15s×129 条)。

### T0.6 实测(2026-08-28,UE4 server 0.9.15 @ C:\carla,Town10HD_Opt,Epic 1280×720 窗口,端口 2031)
- **adapter 重大修正**:`-graphicsadapter=2` 在 0.9.15 上**不选 5090**(UE4.26 DXGI 枚举含 Intel 核显+2×IddCx,与 UE5 不同)——错卡时 5090 显存平躺 6989MiB/util 0%、同步 13.9 FPS、相机丢帧 729;**0.9.15 必须用 `-graphicsadapter=0`**(显存 +7.6GB、util 45–57%、性能 ~7× 坐实)。0.9.15 Shipping 窗口模式不写 CarlaUE4.log,只能靠 nvidia-smi 判卡。
- 启动结构:CarlaUE4.exe 是引导壳,真进程 CarlaUE4-Win64-Shipping.exe(bind 2031),清理要杀两个;RPC 就绪 <30s。
- 同步跟随:97.6 FPS(dt=0.05,200 tick,≈4.9× 实时)。RGB 相机:33251 帧/302.0s ≈ 110.1 FPS,0 丢帧。RPC 延迟 30ms,TM 端口 8000。
- 资源:server 显存增量 ~8.1GB(总量 15.1GB);宿主 free RAM 37.7–37.8 GiB(56GB 口径,充足)。
- 地图:20 个可用(Town01–07+_Opt、Town10HD+_Opt、Town11/12/13/15),Bench2Drive 所需 Town06/07 齐;默认地图 Town10HD_Opt。
- 客户端坑:carla==0.9.15 退出时 C++ abort("operate on a destroyed actor"),与 0.10 同类,数据先落盘即可。
- 观测:logs/t06-observe.log(RUN2 标记后为正确渲染段;前半段是错卡对照);结果 logs/smoke-ue4.json,result=PASS。

### CP0 复测(2026-08-28,降档 32GB 生效后)
- RAM 门禁 32GB 口径:**PASS** —— UE5 server(2021,adapter=0)+ WSL 压 28GB 驻留 4min,宿主空闲 12.9–14.5GB(门禁 ≥6GB);server 全程存活;释压后 60s 冒烟回归 PASS(同步 41.9 FPS,RGB 2631 帧零丢帧)。logs/t07-ram-observe.log、logs/smoke-ue5-rerun.json。
- **adapter 索引漂移坐实**:WSL/宿主重启后 UE5 侧 5090 从 =2 漂到 =2 crash(Microsoft Basic Render Driver)→ =0 正常。启动必须 nvidia-smi 增量校验(tools/wait_server.py / watchdog 内置轮询)。
- winNAT 保留段重启后漂移:1921–2020 消失,新增 2756–3355/3390–3989;2021/2031 当前空闲。
- A3:远程会话断开后 server 存活(用户实测)。
