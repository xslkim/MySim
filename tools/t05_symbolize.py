#!/usr/bin/env python3
"""手工 PDB 符号化(v3):stderr 进度 + 连续 run 读。用法: /tmp/pdbenv311/bin/python tools/t05_symbolize.py"""
import bisect, struct, sys

PDB = "/tmp/cu.pdb"
OFFSETS = [0x68ab862, 0x68af167, 0x68ad97f, 0x68ac1bc, 0x68ac298,
           0x437762f, 0x43dc98d, 0x430377b, 0x42fefe6, 0x3ffadca,
           0x3f84035, 0x3f66a2c, 0x1244001, 0x6a7d5ae]

def log(*a): print(*a, file=sys.stderr, flush=True)

f = open(PDB, "rb")
sb = f.read(4096)
ps, alloc, free, root_bytes, reserved, block_map_page = struct.unpack_from("<IIIIII", sb, 32)
num_root_pages = (root_bytes + ps - 1) // ps
f.seek(block_map_page * ps)
root_page_nums = struct.unpack(f"<{num_root_pages}I", f.read(num_root_pages * 4))

def read_pages(pages):
    out = bytearray()
    run_start = None
    prev = None
    def flush_run(start, end):
        f.seek(start * ps)
        return f.read((end - start + 1) * ps)
    for pn in pages:
        if run_start is None:
            run_start = prev = pn
        elif pn == prev + 1:
            prev = pn
        else:
            out += flush_run(run_start, prev)
            run_start = prev = pn
    if run_start is not None:
        out += flush_run(run_start, prev)
    return bytes(out)

root = read_pages(root_page_nums)[:root_bytes]
num_streams = struct.unpack_from("<I", root, 0)[0]
sizes = list(struct.unpack_from(f"<{num_streams}I", root, 4))
pos = 4 + num_streams * 4
stream_pages = []
for i in range(num_streams):
    n = (sizes[i] + ps - 1) // ps if sizes[i] != 0xFFFFFFFF else 0
    if sizes[i] == 0xFFFFFFFF: sizes[i] = 0
    pgs = struct.unpack_from(f"<{n}I", root, pos) if n else ()
    stream_pages.append(pgs)
    pos += n * 4
log(f"streams={num_streams}")

def get_stream(idx):
    return read_pages(stream_pages[idx])[:sizes[idx]]

# DBI 头(先读头一页拿子流大小,再按 dbg_off 重读足够页)
dbi0 = read_pages(stream_pages[3][:1])
(sig_v, ver, age, gsi_idx, build, psi_idx, pdbdll, symrec_idx, rbld,
 mod_sz, sc_sz, sm_sz, si_sz, tsm_sz, mfc, dbg_sz, ec_sz,
 flags, machine, pad) = struct.unpack_from("<iIIHHHHHHiiiiiIiiHHI", dbi0, 0)
log(f"symrec_idx={symrec_idx} size={sizes[symrec_idx]} gsi={gsi_idx} psi={psi_idx}")
dbg_off = 64 + mod_sz + sc_sz + sm_sz + si_sz + tsm_sz + ec_sz
npages = (dbg_off + 22 + ps - 1) // ps
dbi0 = read_pages(stream_pages[3][:npages])
dbg = struct.unpack_from("<11h", dbi0, dbg_off)
fpo, exc, fixup, omap_to, omap_from, sect_hdr, trm, xdata, pdata, newfpo, sect_hdr_orig = dbg
log(f"sect_hdr={sect_hdr} sect_hdr_orig={sect_hdr_orig}")

sect_raw = get_stream(sect_hdr if sect_hdr != -1 else sect_hdr_orig)
sections = []
for off in range(0, len(sect_raw) - 39, 40):
    nm = sect_raw[off:off + 8].rstrip(b"\0").decode("ascii", "replace")
    va = struct.unpack_from("<I", sect_raw, off + 12)[0]
    sections.append((va, nm))
log(f"sections={len(sections)}")

log("reading symrec ...")
raw = get_stream(symrec_idx)
log(f"symrec bytes={len(raw)}; walking ...")

WANT_PUB = 0x110E
WANT_DATA = (0x110D, 0x110C)
WANT_PROC = (0x1110, 0x110F, 0x1147, 0x1146, 0x1125, 0x1127)
syms = []
L = len(raw)
for start in (0, 4):
    n = 0
    posi = start
    good_run = 0
    while posi + 4 <= L:
        reclen = struct.unpack_from("<H", raw, posi)[0]
        if reclen < 4 or posi + 2 + reclen > L:
            break
        rtype = struct.unpack_from("<H", raw, posi + 2)[0]
        body = posi + 4
        if rtype == WANT_PUB or rtype in WANT_DATA:
            soff, sseg = struct.unpack_from("<IH", raw, body + 4)
            nm_off = body + 10
        elif rtype in WANT_PROC:
            soff, sseg = struct.unpack_from("<IH", raw, body + 28)
            nm_off = body + 35
        else:
            posi += 2 + reclen
            continue
        end = raw.find(b"\0", nm_off, posi + 2 + reclen)
        if end != -1 and 1 <= sseg <= len(sections):
            syms.append((sections[sseg - 1][0] + soff, raw[nm_off:end].decode("utf-8", "replace")))
            n += 1
        posi += 2 + reclen
    log(f"walk(start={start}) syms={n} endpos={posi}/{L}")
    if n > 1000:
        break

syms.sort()
rvas = [r for r, _ in syms]
log(f"total syms={len(syms)}")
for o in OFFSETS:
    i = bisect.bisect_right(rvas, o) - 1
    if i >= 0:
        r, nm = syms[i]
        print(f"exe+0x{o:x} = {nm} +0x{o - r:x}")
    else:
        print(f"exe+0x{o:x} = <unresolved>")
