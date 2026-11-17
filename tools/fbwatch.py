#!/usr/bin/env python3
"""Watch a running qemu-sweet.py guest's framebuffer, live.

  fbwatch.py OUTDIR PAYLOAD [--kernel KERNEL] [--secs N] [--every S] [--text]

Connects to the QMP socket that qemu-sweet.py leaves in OUTDIR while the
guest runs, pmemsaves the 1080x2400 panel at 0x9c000000 every S seconds
(default 5), and writes fb-live.png plus (with --kernel) fb-live.txt so you
can watch a long emulated boot instead of waiting for qemu-sweet.py's
single end-of-run dump. --text also prints each decoded console refresh.
"""
import importlib.machinery, argparse, os, socket, struct, subprocess, sys, time

_here = os.path.dirname(os.path.abspath(__file__))
qs = importlib.machinery.SourceFileLoader('qs', os.path.join(_here, 'qemu-sweet.py')).load_module()


def snap(sock, outdir, font):
    raw_path = os.path.join(outdir, 'fb-live.raw')
    qs.qmp(sock, pmemsave=(qs.FB_BASE, qs.FB_STRIDE * qs.FB_H, raw_path))
    try:
        raw = open(raw_path, 'rb').read()
    finally:
        try:
            os.unlink(raw_path)
        except OSError:
            pass
    if len(raw) != qs.FB_STRIDE * qs.FB_H:
        return None, None
    return raw, (qs.decode_screen(raw, font) if font else (None, 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('outdir')
    ap.add_argument('payload')
    ap.add_argument('--kernel')
    ap.add_argument('--secs', type=float, default=3600)
    ap.add_argument('--every', type=float, default=5)
    ap.add_argument('--text', action='store_true')
    a = ap.parse_args()

    sock = os.path.join(a.outdir, 'mon.sock')
    font = None
    if a.kernel:
        symbols = subprocess.check_output(['llvm-nm', '--defined-only', a.kernel], text=True)
        fonts = [int(l.split()[0], 16) for l in symbols.splitlines() if l.split()[-1:] == ['_iso_font']]
        font = qs.payload_data(open(a.payload, 'rb').read(), fonts[0], 256 * 16)

    t0 = time.time()
    last = None
    while time.time() - t0 < a.secs:
        if not os.path.exists(sock):
            time.sleep(1)
            continue
        try:
            raw, (text, _) = snap(sock, a.outdir, font)
        except (OSError, ConnectionError, ValueError, struct.error):
            time.sleep(2)
            continue
        if raw and raw != last:
            last = raw
            qs.write_png(os.path.join(a.outdir, 'fb-live.png'), raw)
            if text is not None:
                open(os.path.join(a.outdir, 'fb-live.txt'), 'w').write(text)
                if a.text:
                    print(text)
        time.sleep(a.every)


if __name__ == '__main__':
    sys.exit(main())
