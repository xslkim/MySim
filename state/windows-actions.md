# windows-actions.md — 待宿主(用户)执行动作队列

> 状态:[待执行] = 等用户;[完成] 登记时间。全部 CP0 前置。

## A1 .wslconfig 降档 [完成 2026-08-28](memory=32GB/swap=16GB 生效;processors 保留 16)
- 复测 PASS(t07-retest2):UE5 server + WSL 压 28GB,宿主空闲 12.9–14.5GB ≥6GB;server 存活;60s 冒烟回归 PASS(41.9 FPS 同步、零丢帧)
- 副产物:adapter 索引重启后漂移(UE5 侧 =2→=0),watchdog 已内置 adapter 轮询+显存校验;`conda run` stdin heredoc 坑入 AGENTS.md

## A2 防火墙放行 CARLA 端口 [实测不需要,可跳过]
- T0.5/T0.6 实测:WSL→宿主 IP 直连 RPC(43ms/30ms)、相机流、TM(8000) 全通,未配任何入站规则
- 保留备查:若未来开 mirrored 网络或跨机连接再回来配:
  ```powershell
  New-NetFirewallRule -DisplayName "CARLA-UE5" -Direction Inbound -Protocol TCP -LocalPort 2021-2023 -Action Allow
  New-NetFirewallRule -DisplayName "CARLA-UE4" -Direction Inbound -Protocol TCP -LocalPort 2031-2033 -Action Allow
  ```

## A3 远程会话存活测试 [完成 2026-08-28]
- 用户实测:断开远程会话后 server 进程与 RPC 端口存活,回连正常

## A4 端口约定修订拍板 [完成 2026-08-28 — 选项 a]
- 接受 **UE5 2021–2023 / UE4 2031–2033** 新约定;AGENTS.md 端口行与已知坑已更新,watchdog SIDES 已是新端口
- 备忘:winNAT 保留段会动态漂移,大重启后复查 `netsh int ipv4 show excludedportrange tcp`

(开机自启任务计划模板待 A3 结果后追加)
