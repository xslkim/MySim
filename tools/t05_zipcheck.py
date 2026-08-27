#!/usr/bin/env python3
"""不重新下载 13GB 的前提下校验 CARLA zip 内容完整性:
HTTP Range 拉取 zip 中央目录(支持 ZIP64),逐文件对比 uncompressed size 与本地文件大小。
用法: python3 tools/t05_zipcheck.py
"""
import struct, sys, urllib.request, os

URL = "https://carla-releases.b-cdn.net/Windows/Carla-0.10.0-Win64-Shipping.zip"
ROOT = "/mnt/c/carla/CARLA_0.10.0/Carla-0.10.0-Win64-Shipping"
TOP = "Carla-0.10.0-Win64-Shipping/"

def fetch_range(start, end):
    req = urllib.request.Request(URL, headers={"Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()

req = urllib.request.Request(URL, method="HEAD")
with urllib.request.urlopen(req, timeout=60) as r:
    total = int(r.headers["Content-Length"])
print(f"zip total size = {total}", flush=True)

tail = fetch_range(max(0, total - 262144), total - 1)
pos = tail.rfind(b"PK\x05\x06")
assert pos >= 0, "EOCD not found"
eocd = tail[pos:pos + 22]
n16   = struct.unpack_from("<H", eocd, 10)[0]
csz32 = struct.unpack_from("<I", eocd, 12)[0]
coff32= struct.unpack_from("<I", eocd, 16)[0]

if csz32 == 0xFFFFFFFF or coff32 == 0xFFFFFFFF or n16 == 0xFFFF:
    # ZIP64:locator 在 EOCD 前 20 字节
    loc = tail[pos - 20:pos]
    assert loc[:4] == b"PK\x06\x07", "ZIP64 locator not found"
    z64off = struct.unpack_from("<Q", loc, 8)[0]
    z = fetch_range(z64off, z64off + 55)
    assert z[:4] == b"PK\x06\x06"
    n_entries = struct.unpack_from("<Q", z, 32)[0]
    cd_size   = struct.unpack_from("<Q", z, 40)[0]
    cd_off    = struct.unpack_from("<Q", z, 48)[0]
else:
    n_entries, cd_size, cd_off = n16, csz32, coff32
print(f"entries={n_entries} cd_off={cd_off} cd_size={cd_size}", flush=True)

cd = b""
CHUNK = 4 * 1024 * 1024
for off in range(cd_off, cd_off + cd_size, CHUNK):
    cd += fetch_range(off, min(off + CHUNK, cd_off + cd_size) - 1)
assert len(cd) == cd_size
print("central directory fetched", flush=True)

mismatch, missing, checked = [], [], 0
i = 0
while i < cd_size:
    assert cd[i:i+4] == b"PK\x01\x02", f"bad CD sig at {i}"
    method = struct.unpack_from("<H", cd, i + 10)[0]
    csize  = struct.unpack_from("<I", cd, i + 20)[0]
    usize  = struct.unpack_from("<I", cd, i + 24)[0]
    nlen   = struct.unpack_from("<H", cd, i + 28)[0]
    elen   = struct.unpack_from("<H", cd, i + 30)[0]
    clen   = struct.unpack_from("<H", cd, i + 32)[0]
    extra  = cd[i + 46 + nlen: i + 46 + nlen + elen]
    if csize == 0xFFFFFFFF or usize == 0xFFFFFFFF:
        # ZIP64 extra field 0x0001
        j = 0
        while j < len(extra):
            tag, sz = struct.unpack_from("<HH", extra, j)
            body = extra[j + 4: j + 4 + sz]
            if tag == 0x0001:
                vals = []
                k = 0
                if usize == 0xFFFFFFFF:
                    usize = struct.unpack_from("<Q", body, k)[0]; k += 8
                if csize == 0xFFFFFFFF:
                    csize = struct.unpack_from("<Q", body, k)[0]; k += 8
                break
            j += 4 + sz
    name = cd[i + 46:i + 46 + nlen].decode("utf-8", "replace")
    if name.startswith(TOP) and not name.endswith("/"):
        rel = name[len(TOP):]
        local = os.path.join(ROOT, rel)
        checked += 1
        if not os.path.exists(local):
            missing.append(rel)
        else:
            actual = os.path.getsize(local)
            if actual != usize:
                mismatch.append((rel, usize, actual))
    i += 46 + nlen + elen + clen

print(f"checked={checked} missing={len(missing)} size_mismatch={len(mismatch)}")
for r in missing[:20]: print("MISSING:", r)
for r, e, a in mismatch[:60]: print(f"MISMATCH: {r} expected={e} actual={a}")
