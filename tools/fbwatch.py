#!/usr/bin/env python3
"""Watch a running qemu-sweet.py guest's framebuffer, live.

  fbwatch.py OUTDIR PAYLOAD [--kernel KERNEL] [--secs N] [--every S] [--text]

Connects to the QMP socket that qemu-sweet.py leaves in OUTDIR while the
guest runs, pmemsaves the 1080x2400 panel at 0x9c000000 every S seconds
(default 5), and writes fb-live.png plus (with --kernel) fb-live.txt so you
can watch a long emulated boot instead of waiting for qemu-sweet.py's
single end-of-run dump. --text also prints each decoded console refresh.
With --kernel it also appends newly scrolled-off lines to fb-history.txt,
a deduplicated full boot log (the on-screen console is circular).
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


def merge_screen(history, screen):
    """Append the part of `screen` not already at the tail of `history`.

    The kernel console is circular: each snapshot overlaps the previous
    one. Find the longest suffix of history that is a prefix of the new
    screen and keep only what scrolled in since. Returns appended lines.
    """
    new_lines = [l for l in screen.split('\n') if l.strip()]
    if not new_lines:
        return []
    # Try to align the new screen's first line inside the recent history
    # tail; everything after that point in new_lines is fresh output.
    tail = history[-400:]
    first = new_lines[0]
    best = -1
    for i in range(len(tail) - 1, -1, -1):
        if tail[i] == first:
            best = len(history) - len(tail) + i
            break
    if best < 0:
        return new_lines
    # history[best] == new_lines[0]; count how many following lines repeat.
    k = 1
    while k < len(new_lines) and best + k < len(history) and history[best + k] == new_lines[k]:
        k += 1
    return new_lines[k:]


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

    hist_path = os.path.join(a.outdir, 'fb-history.txt')
    history = []
    if font and os.path.exists(hist_path):
        history = [l.rstrip('\n') for l in open(hist_path, errors='replace')]

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
                fresh = merge_screen(history, text)
                if fresh:
                    with open(hist_path, 'a') as hf:
                        hf.write('\n'.join(fresh) + '\n')
                    history += fresh
                if a.text:
                    print(text)
        time.sleep(a.every)


if __name__ == '__main__':
    sys.exit(main())
