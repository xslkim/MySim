#!/usr/bin/env python3
"""server_watchdog.py — CARLA server / 模型服务 / 训练进程守护(docs/plan/01-infra.md §2.2)。

最小可用版(M0 阶段):监控 CARLA server RPC 心跳,失联则经 powershell 互操作重启。
用法: python tools/server_watchdog.py --side ue5   # 或 --side ue4

启动可靠性(M0 实战):
- graphicsadapter 索引随重启/会话漂移(T0.5 UE5=2、T0.6 UE4=0、CP0 复测 UE5 漂到 0),
  启动后必须 nvidia-smi 验证 5090 显存增量,不符则换索引重试(ADAPTER_CANDIDATES)。
- 端口 2021/2031(winNAT 保留段吞掉 2000-2002/2010-2012,T0.5 根因)。
- UE4 的 CarlaUE4.exe 是引导壳,清理要连 CarlaUE4-Win64-Shipping.exe 一起杀。
后续扩展点:模型服务心跳、训练 ckpt 拉起、宿主 RAM 告警线。
"""
import argparse, subprocess, sys, time

SIDES = {
    "ue5": {"port": 2021, "exe": r"C:\carla\CARLA_0.10.0\Carla-0.10.0-Win64-Shipping",
            "cmd": r"C:\carla\CARLA_0.10.0\Carla-0.10.0-Win64-Shipping\CarlaUnreal.exe -carla-rpc-port=2021 -graphicsadapter={adapter} -quality-level=Epic -windowed -ResX=1280 -ResY=720",
            "kill": ["CarlaUnreal"]},
    "ue4": {"port": 2031, "exe": r"C:\carla\CARLA_0.9.15\WindowsNoEditor",
            "cmd": r"C:\carla\CARLA_0.9.15\WindowsNoEditor\CarlaUE4.exe -carla-rpc-port=2031 -graphicsadapter={adapter} -quality-level=Epic -windowed -ResX=1280 -ResY=720",
            "kill": ["CarlaUE4-Win64-Shipping", "CarlaUE4"]},
    # ue4b:第二 UE4 实例(双实例并发评测,T1.2 起;端口 2041–2043,winNAT 保留段 2756–3989 之外)
    "ue4b": {"port": 2041, "exe": r"C:\carla\CARLA_0.9.15\WindowsNoEditor",
            "cmd": r"C:\carla\CARLA_0.9.15\WindowsNoEditor\CarlaUE4.exe -carla-rpc-port=2041 -graphicsadapter={adapter} -quality-level=Epic -windowed -ResX=1280 -ResY=720",
            "kill": ["CarlaUE4-Win64-Shipping", "CarlaUE4"]},
}
ADAPTER_CANDIDATES = [0, 2, 1, 3]
GPU_DELTA_MB = 4000  # 启动后 5090 显存须比基线多这么多,否则判选错卡

def host_ip():
    return subprocess.check_output("ip route show | awk '/default/{print $3}'", shell=True).decode().strip()

def ps(cmd):
    return subprocess.run(["powershell.exe", "-NoProfile", "-Command", cmd],
                          capture_output=True, text=True, timeout=120)

def gpu_used_mb():
    out = subprocess.check_output(
        ["powershell.exe", "nvidia-smi.exe", "--query-gpu=memory.used", "--format=csv,noheader"],
        text=True).strip()
    return int(out.replace("MiB", "").strip())

def server_alive(port):
    try:
        import carla
        c = carla.Client(host_ip(), port); c.set_timeout(10.0)
        c.get_world().get_actors()
        return True
    except Exception:
        return False

def _port_procs_ps(side):
    """按命令行里的 -carla-rpc-port 匹配进程(双实例同名,按进程名杀会误伤另一侧)。"""
    port = SIDES[side]["port"]
    return (f"Get-CimInstance Win32_Process | Where-Object "
            f"{{ $_.CommandLine -and $_.CommandLine.Contains('-carla-rpc-port={port}') }}")

def kill_side(side):
    # ue5 单实例时按名杀即可;ue4/ue4b 必须按命令行端口区分(同名进程,双实例并发)
    ps(f"{_port_procs_ps(side)} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}")
    # 兜底:命令行匹配漏掉的(如引导壳参数被改写场景)再按名扫,但仅当另一侧不在跑
    other = [s for s in SIDES if s != side and SIDES[s]["exe"] == SIDES[side]["exe"]]
    other_alive = any(server_alive(SIDES[s]["port"]) for s in other)
    if not other_alive:
        for name in SIDES[side]["kill"]:
            ps(f"Stop-Process -Name {name} -Force -ErrorAction SilentlyContinue")

def launch_once(side, adapter):
    cfg = SIDES[side]
    baseline = gpu_used_mb()
    ps(f"Start-Process -FilePath cmd.exe -ArgumentList '/c','{cfg['cmd'].format(adapter=adapter)}' -WorkingDirectory '{cfg['exe']}'")
    t0 = time.time()
    while time.time() - t0 < 180:
        if server_alive(cfg["port"]):
            used = gpu_used_mb()
            if used >= baseline + GPU_DELTA_MB:
                print(f"[watchdog] {side} 就绪(adapter={adapter},显存 {baseline}→{used}MiB)", flush=True)
                return True
            print(f"[watchdog] {side} RPC 通但显存未涨({baseline}→{used}MiB),判错卡", flush=True)
            return False
        # 进程已死则不必等满(按命令行端口判存,双实例同名不能按进程名)
        r = ps(f"({_port_procs_ps(side)} | Measure-Object).Count -gt 0")
        if r.stdout.strip() != "True":
            print(f"[watchdog] {side} 进程已消失(adapter={adapter})", flush=True)
            return False
        time.sleep(5)
    return False

def restart(side):
    print(f"[watchdog] {side} 失联,清理 + 重启(adapter 轮询 {ADAPTER_CANDIDATES})", flush=True)
    kill_side(side)
    time.sleep(5)
    for ad in ADAPTER_CANDIDATES:
        if launch_once(side, ad):
            return True
        kill_side(side)
        time.sleep(5)
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", choices=list(SIDES), required=True)
    ap.add_argument("--max-restarts", type=int, default=3)
    args = ap.parse_args()
    port = SIDES[args.side]["port"]

    fails = 0
    while fails < args.max_restarts:
        if server_alive(port):
            fails = 0
            time.sleep(15)
            continue
        time.sleep(30)  # 失联确认窗口(>30s 判失联)
        if server_alive(port):
            continue
        fails += 1
        if restart(args.side):
            print(f"[watchdog] {args.side} 重启成功(第 {fails} 次)", flush=True)
        else:
            print(f"[watchdog] {args.side} 全部 adapter 候选失败", flush=True)
    print(f"[watchdog] {args.side} 连续 {fails} 次失败,BLOCKED 停队列", flush=True)
    sys.exit(2)

if __name__ == "__main__":
    main()
