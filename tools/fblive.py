#!/usr/bin/env python3
"""Live framebuffer viewer: QMP pmemsave the panel and serve it over HTTP.

Usage: python3 tools/fblive.py <mon.sock> [--port 8099] [--every 3]
Opens an auto-reloading page at http://localhost:PORT — the framebuffer
refreshes in place every --every seconds.
"""
import importlib.machinery, os, sys, time, threading, argparse

qs = importlib.machinery.SourceFileLoader(
    'qs', '/mnt/f/.dev/ios-sweet/tools/qemu-sweet.py').load_module()

ap = argparse.ArgumentParser()
ap.add_argument('sock')
ap.add_argument('--port', type=int, default=8099)
ap.add_argument('--every', type=float, default=3.0)
ap.add_argument('--out', default='/root/run-smp6/fb-live.raw')
a = ap.parse_args()

png = {'data': b'', 'ts': 0.0}


def grab():
    while True:
        try:
            qs.qmp(a.sock, pmemsave=(qs.FB_BASE, qs.FB_STRIDE * qs.FB_H, a.out))
            raw = open(a.out, 'rb').read()
            if len(raw) == qs.FB_STRIDE * qs.FB_H:
                tmp = a.out + '.png'
                qs.write_png(tmp, raw)
                png['data'] = open(tmp, 'rb').read()
                png['ts'] = time.time()
        except Exception as e:
            png['err'] = repr(e)
        time.sleep(a.every)


threading.Thread(target=grab, daemon=True).start()

from http.server import BaseHTTPRequestHandler, HTTPServer

PAGE = b"""<!doctype html><meta charset=utf-8>
<title>ios-sweet fb</title>
<style>body{background:#111;margin:0;display:flex;flex-direction:column;align-items:center;font:14px monospace;color:#9cf}
img{image-rendering:pixelated;max-height:96vh;margin-top:8px}#t{padding:4px}</style>
<div id=t>loading...</div><img id=f>
<script>
let n=0;
function tick(){n++;document.getElementById('f').src='/fb.png?r='+n;
fetch('/ts').then(r=>r.text()).then(s=>document.getElementById('t').textContent='frame '+n+' | '+s).catch(()=>{});}
setInterval(tick,%d);tick();
</script>""" % int(a.every * 1000)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == '/fb.png' or self.path.startswith('/fb.png?'):
            d = png['data']
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(d)
        elif self.path == '/ts':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            age = time.time() - png['ts'] if png['ts'] else -1
            err = png.get('err', '')
            self.wfile.write(('grabbed %.1fs ago %s' % (age, err)).encode())
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(PAGE)


HTTPServer(('127.0.0.1', a.port), H).serve_forever()
