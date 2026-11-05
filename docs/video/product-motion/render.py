#!/usr/bin/env python3
"""Deterministic, offline Three.js → Chrome WebGL → 1080p H.264 rendering."""
import argparse
import base64
import hashlib
import json
import subprocess
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
DURATIONS = {"problem": 16, "connections": 8, "cta": 13}
PREVIEW_TIMES = {"problem": 13, "connections": 6, "cta": 10}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--previews-only", action="store_true")
    parser.add_argument("--scene", choices=DURATIONS)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(QuietHandler, directory=str(ROOT.parent)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required", "--enable-unsafe-swiftshader"],
        )
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        errors, failed_requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("requestfailed", lambda request: failed_requests.append({"url": request.url, "failure": request.failure}))
        page.goto(f"http://127.0.0.1:{server.server_address[1]}/product-motion/", wait_until="networkidle")
        page.wait_for_function("window.motionReady === true")
        meta = page.evaluate("window.motionMeta")
        print(json.dumps(meta), flush=True)
        for scene, at in PREVIEW_TIMES.items():
            page.evaluate("([name, at]) => window.renderAt(name, at)", [scene, at])
            page.screenshot(path=str(ROOT / f"{scene}-preview.png"))
        (ROOT / "layout-bounds.json").write_text(json.dumps(page.evaluate("window.motionLayout()"), indent=2) + "\n")
        print("PREVIEWS_READY", flush=True)
        # Check spacing before committing time to the video renders.
        subprocess.run(["python3", str(ROOT / "check_spacing.py")], check=True)
        if not args.previews_only:
            for scene, duration in DURATIONS.items():
                if args.scene and scene != args.scene:
                    continue
                command = [
                    "ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-vcodec", "mjpeg", "-framerate", "30", "-i", "-",
                    "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(ROOT / f"{scene}.mp4"),
                ]
                process = subprocess.Popen(command, stdin=subprocess.PIPE)
                started = time.monotonic()
                for frame in range(duration * 30):
                    data = page.evaluate(
                        "([name, at]) => { window.renderAt(name, at); return document.querySelector('canvas').toDataURL('image/jpeg', .96).split(',')[1]; }",
                        [scene, frame / 30],
                    )
                    process.stdin.write(base64.b64decode(data))
                    if frame % 150 == 0:
                        print(f"{scene}: {frame}/{duration * 30} frames; {time.monotonic() - started:.1f}s", flush=True)
                process.stdin.close()
                if process.wait():
                    raise RuntimeError(f"Encoding failed: {scene}")
                print(f"COMPLETE {scene}.mp4 ({duration}s)", flush=True)
        artifacts = {}
        for scene, duration in DURATIONS.items():
            path = ROOT / f"{scene}.mp4"
            if not path.exists():
                continue
            probe = json.loads(subprocess.check_output([
                "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames,pix_fmt", "-of", "json", str(path),
            ]))
            video = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
            assert (video["width"], video["height"], video["r_frame_rate"], video["nb_frames"]) == (1920, 1080, "30/1", str(duration * 30))
            assert abs(float(probe["format"]["duration"]) - duration) < 0.001
            artifacts[scene] = {"path": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "probe": probe}
        if errors or failed_requests:
            raise RuntimeError(json.dumps({"pageErrors": errors, "failedRequests": failed_requests}))
        (ROOT / "render-validation.json").write_text(json.dumps({
            **meta,
            "engine": "Three.js WebGLRenderer; orthographic camera; meshes, lines, CanvasTexture text",
            "render_method": "Deterministic Chrome WebGL frames; JPEG pipe to ffmpeg H.264; no external requests",
            "pageErrors": errors, "failedRequests": failed_requests,
            "artifacts": artifacts,
            "sources": {
                "font": "../fonts/sources.json",
                "three": "https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js",
                "code": "https://github.com/Ontology0/hanium-arbiter",
                "download": "https://culture-fit-demo-production.up.railway.app/download",
            },
            "scope": "Explanatory product diagrams. No external execution, owner authentication, deployment or measured performance is depicted.",
        }, indent=2) + "\n")
        browser.close()
    server.shutdown()


if __name__ == "__main__":
    main()
