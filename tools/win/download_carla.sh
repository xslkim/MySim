#!/bin/bash
# T0.2/T0.3: 下载并安装 CARLA server(Windows 侧 C:\carla,BunnyCDN 直链,断点续传)
# 用法: 后台任务运行;日志即 stdout。成功末尾打印 ALL_DONE
set -u

dl() { # url zipwin ziplin dstwin dstlin expect_size tag
  local url="$1" zipwin="$2" ziplin="$3" dstwin="$4" dstlin="$5" expect="$6" tag="$7"
  echo "[$(date '+%F %T')] [$tag] 开始下载 $url"
  for attempt in 1 2 3; do
    powershell.exe -NoProfile -Command "curl.exe -L -C - --retry 10 --retry-delay 5 -o \"$zipwin\" \"$url\"" 2>&1 | tail -2
    local sz; sz=$(stat -c%s "$ziplin" 2>/dev/null || echo 0)
    echo "[$(date '+%F %T')] [$tag] 尝试 $attempt 结束,size=$sz 期望=$expect"
    if [ "$sz" = "$expect" ]; then break; fi
    [ "$attempt" = 3 ] && { echo "[$tag] SIZE_MISMATCH 失败"; return 1; }
    sleep 5
  done
  mkdir -p "$dstlin"
  echo "[$(date '+%F %T')] [$tag] 解压到 $dstwin"
  powershell.exe -NoProfile -Command "tar.exe -xf \"$zipwin\" -C \"$dstwin\"" 2>&1 | tail -2
  echo "[$(date '+%F %T')] [$tag] 解压完成,删除 zip"
  rm -f "$ziplin"
  echo "[$(date '+%F %T')] [$tag] DONE"
  return 0
}

mkdir -p /mnt/c/carla/dl

dl "https://carla-releases.b-cdn.net/Windows/Carla-0.10.0-Win64-Shipping.zip" \
   'C:\carla\dl\Carla-0.10.0-Win64-Shipping.zip' /mnt/c/carla/dl/Carla-0.10.0-Win64-Shipping.zip \
   'C:\carla\CARLA_0.10.0' /mnt/c/carla/CARLA_0.10.0 10203028286 T0.2 || exit 1

dl "https://carla-releases.b-cdn.net/Windows/CARLA_0.9.15.zip" \
   'C:\carla\dl\CARLA_0.9.15.zip' /mnt/c/carla/dl/CARLA_0.9.15.zip \
   'C:\carla\CARLA_0.9.15' /mnt/c/carla/CARLA_0.9.15 7755135185 T0.3 || exit 1

dl "https://carla-releases.b-cdn.net/Windows/AdditionalMaps_0.9.15.zip" \
   'C:\carla\dl\AdditionalMaps_0.9.15.zip' /mnt/c/carla/dl/AdditionalMaps_0.9.15.zip \
   'C:\carla\CARLA_0.9.15' /mnt/c/carla/CARLA_0.9.15 7211521479 T0.3m || exit 1

echo "[$(date '+%F %T')] ALL_DONE"
