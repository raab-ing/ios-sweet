#!/usr/bin/env python3
"""SWEET monitor: SpringBoard thread count + kernel log + fb state, once a minute."""
import importlib.machinery, re, time, hashlib, os, sys

qs = importlib.machinery.SourceFileLoader(
    'qs', '/mnt/f/.dev/ios-sweet/tools/qemu-sweet.py').load_module()
SOCK = sys.argv[1] if len(sys.argv) > 1 else '/root/run-smp6/mon.sock'


def rdq(va, n, phys=False):
    vals = []
    cmd = 'xp' if phys else 'x'
    for off in range(0, n, 0x10):
        r = qs.qmp(SOCK, '%s /2xg %#x' % (cmd, va + off))[0]
        for m in re.finditer(r':\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)', r):
            vals += [int(m.group(1), 16), int(m.group(2), 16)]
    return vals


def xw(va):
    r = qs.qmp(SOCK, 'x /1xg %#x' % va)[0]
    m = re.search(r':\s+0x([0-9a-f]+)', r)
    return int(m.group(1), 16) if m else 0


RING = 0xb1c52710
SIZE = 4 * 1024 * 1024
ALLPROC = 0xfffffe0007bfc540
OUTDIR = os.path.dirname(SOCK)


def find_task(name):
    p = xw(ALLPROC)
    seen = 0
    while p and p != ALLPROC and seen < 400:
        seen += 1
        comm = rdq(p + 0x5c0, 0x10)
        nm = b''.join(v.to_bytes(8, 'little') for v in comm).split(b'\x00')[0]
        if nm == name.encode():
            pro = xw(p + 0x18)
            return xw(pro + 8), p
        p = xw(p)
    return 0, 0


last = 0
while True:
    try:
        task, proc = find_task('SpringBoard')
        n = 0
        if task:
            t = xw(task + 0x80)
            while t and t != task + 0x80 and n < 200:
                n += 1
                t = xw(t + 0x478)
        total = rdq(RING, 8, phys=True)[0] or 0
        cnt = min(total, SIZE)
        data = rdq(RING + 8, cnt, phys=True)
        txt = b''.join(v.to_bytes(8, 'little') for v in data).decode('utf-8', 'replace')
        swaps = re.findall(r'SWEET FB: swap (\d+)', txt)
        fbpath = os.path.join(OUTDIR, 'fb-live.png')
        fb = open(fbpath, 'rb').read() if os.path.exists(fbpath) else b''
        print('%s SBtask=%#x threads=%d klog=%d swaps=%s fb=%s' % (
            time.strftime('%H:%M:%S'), task, n, total,
            max(swaps) if swaps else '-', hashlib.md5(fb).hexdigest()[:8]), flush=True)
        new = total - last
        if 0 < new < 30000:
            seg = txt[-new:]
            for l in seg.splitlines()[-6:]:
                if l.strip():
                    print('    |', l[-110:], flush=True)
        last = total
    except Exception as e:
        print('err', repr(e), flush=True)
    time.sleep(60)
