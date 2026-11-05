#!/usr/bin/env python3
"""Render actual Three.js frames through isolated headless Chrome to H.264 MP4."""
import argparse,base64,json,os,subprocess,threading,time
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
DURATIONS={'intro':16,'why-now':12,'overview':8,'authority':10,'outro':15}
class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args): pass

def main():
    p=argparse.ArgumentParser();p.add_argument('--previews-only',action='store_true');p.add_argument('--scene',choices=DURATIONS);p.add_argument('--port',type=int,default=8891);args=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(QuietHandler,directory=str(ROOT)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True,args=['--autoplay-policy=no-user-gesture-required','--enable-unsafe-swiftshader'])
        page=browser.new_page(viewport={'width':1920,'height':1080},device_scale_factor=1)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(f'http://127.0.0.1:{args.port}/',wait_until='networkidle');page.wait_for_function('window.motionReady===true')
        print(json.dumps(page.evaluate('window.motionMeta')),flush=True)
        for name,t in [('intro',14),('why-now',10),('overview',6),('authority',9),('outro',10)]:
            page.evaluate('([n,t])=>window.renderAt(n,t)',[name,t]);page.screenshot(path=str(ROOT/f'{name}-preview.png'))
        (ROOT/'layout-bounds.json').write_text(json.dumps(page.evaluate('window.motionLayout()'),ensure_ascii=False,indent=2)+'\n')
        print('PREVIEWS_READY',flush=True)
        if not args.previews_only:
            for name,duration in DURATIONS.items():
                if args.scene and args.scene!=name:continue
                command=['ffmpeg','-y','-loglevel','error','-f','image2pipe','-vcodec','mjpeg','-framerate','30','-i','-','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(ROOT/f'{name}.mp4')]
                proc=subprocess.Popen(command,stdin=subprocess.PIPE);started=time.monotonic()
                for frame in range(duration*30):
                    data=page.evaluate('([n,t])=>{window.renderAt(n,t);return document.querySelector("canvas").toDataURL("image/jpeg",.95).split(",")[1]}',[name,frame/30])
                    proc.stdin.write(base64.b64decode(data))
                    if frame%150==0:print(f'{name} {frame}/{duration*30} frames · {time.monotonic()-started:.1f}s',flush=True)
                proc.stdin.close();code=proc.wait()
                if code:raise RuntimeError(f'ffmpeg exited {code}')
                print(f'COMPLETE {name}.mp4 {duration}s',flush=True)
        if errors:raise RuntimeError('\n'.join(errors))
        (ROOT/'render-validation.json').write_text(json.dumps({'engine':'Three.js','threeRevision':page.evaluate('window.motionMeta.threeRevision'),'width':1920,'height':1080,'fps':30,'durations':DURATIONS,'pageErrors':errors,'subtitleSafeArea':'y >= 900px','renderMethod':'deterministic WebGL canvas frames; headless Chrome; H.264'},ensure_ascii=False,indent=2)+'\n')
        browser.close()
    server.shutdown()
if __name__=='__main__':main()
