"""Capture the deployed synthetic demo and render a LinkedIn image/PDF kit.

uv run --with playwright --with pymupdf python docs/social/linkedin/build_assets.py
No source UI changes, model calls, personal browser sessions, or social posting.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import shutil
import sys
import zipfile

import pymupdf
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
RAW = OUT / "screenshots"
IMAGES = OUT / "images"
BASE = "https://culture-fit-demo-production.up.railway.app"
GITHUB = "https://github.com/Ontology0/hanium-arbiter"


def capture(browser):
    context = browser.new_context(viewport={"width": 1340, "height": 1180}, device_scale_factor=2)
    page = context.new_page()
    errors, posts, shots = [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)

    def shot(name, selector=None, clip=None):
        path = RAW / (name + ".png")
        if selector:
            page.locator(selector).screenshot(path=str(path), animations="disabled")
        else:
            page.screenshot(path=str(path), clip=clip, animations="disabled")
        shots.append({"path": str(path.relative_to(OUT)), "url": page.url,
                      "selector": selector, "clip_css_pixels": clip,
                      "sha256": sha256(path.read_bytes()).hexdigest()})

    page.goto(BASE + "/", wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    assert "Human-in-the-Loop (HITL)" in page.locator(".description").inner_text()
    shot("01-landing")

    page.goto(BASE + "/workspace", wait_until="networkidle")
    page.wait_for_selector(".precedence-form")
    assert "Cross-owner authority conflict" in page.locator("#authority-checks").inner_text()
    assert page.locator(".precedence-form input:checked").count() == 0
    shot("02-workspace")
    page.locator(".authority-check").first.evaluate("e=>e.scrollIntoView({block:'start',behavior:'instant'})")
    boxes = page.evaluate("""() => {
        const c = document.querySelector('.authority-check').getBoundingClientRect();
        const f = document.querySelector('.precedence-form').getBoundingClientRect();
        return {x:c.x, y:Math.max(0,c.y), width:c.width, height:f.y-c.y-8};
    }""")
    shot("03-authority-conflict", clip=boxes)
    shot("04-decision-brief", selector="#brief-panel")

    page.get_by_role("button", name="Review Agent Priority Up", exact=True).click()
    form = page.locator(".precedence-form")
    for checkbox in form.locator("input[name=approved_by]").all():
        checkbox.check()
    page.locator(".precedence-form h4").click()
    shot("05-owner-approvals", selector=".precedence-form")
    form.locator(".precedence-submit").click()
    page.wait_for_function("document.querySelector('#precedence-feedback').textContent.includes('Decision owner: Review Agent')")
    assert "Briefing interventions: 0" in page.locator("#authority-intervention-count").inner_text()
    shot("06-authority-resolved", selector=".authority-check")
    sid = page.evaluate("localStorage.getItem('arbiter-session')")
    response = context.request.get(BASE + f"/api/sessions/{sid}/next-action")
    assert response.ok
    advice = response.json()
    assert advice["action"] == "follow_authority", advice["action"]
    assert advice["decision_owner"] == "Review Agent"
    assert advice["execution_status"] == "not_verified"
    # Only publish a small response excerpt; no visitor cookie or session token.
    excerpt = {key: advice[key] for key in ("action", "decision_owner", "execution_status")}
    (OUT / "next-action-excerpt.json").write_text(json.dumps(excerpt, indent=2) + "\n")

    page.goto(BASE + "/download", wait_until="networkidle")
    shot("07-how-to-use")
    shot("08-source-and-skill", selector=".download-packages")
    assert page.locator("#source-download").get_attribute("href") == "/static/downloads/culture-fit-source.zip"
    assert not errors, errors
    assert len(posts) == 1 and posts[0].endswith("/api/authority/precedence"), posts
    receipt = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": BASE, "browser": "Headless Chrome / fresh isolated visitor context",
        "data": "Public synthetic example and previously recorded model analysis",
        "interaction": "Record synthetic owners' agreement with Review Agent first for payment-release-1.2 / approve",
        "before": {"authority_status": "cross_owner_conflict", "decision_owner": None},
        "after": excerpt,
        "model_calls": 0, "external_work_executed": False,
        "remote_owner_identity_verified": False,
        "production_ui_modified": False, "page_errors": errors,
        "screenshots": shots,
    }
    (OUT / "capture-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    context.close()
    return receipt, excerpt


CSS = """
@font-face{font-family:InterLike;src:url('fonts/Pretendard-Regular.otf');font-weight:400}
@font-face{font-family:InterLike;src:url('fonts/Pretendard-SemiBold.otf');font-weight:600}
@font-face{font-family:InterLike;src:url('fonts/Pretendard-ExtraBold.otf');font-weight:800}
*{box-sizing:border-box} html,body{margin:0;padding:0;background:#e7e8eb;color:#101215}
body{font-family:InterLike,Arial,sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.slide{width:1200px;height:1500px;background:#fbfbf9;position:relative;overflow:hidden;
padding:64px 72px 0;margin:0 auto 28px;break-after:page;page-break-after:always}
.slide:last-child{break-after:auto;page-break-after:auto}
.top{display:flex;justify-content:space-between;align-items:center;height:46px;font-size:21px}
.brand{font-size:30px;font-weight:800;letter-spacing:-1.1px;display:flex;gap:16px;align-items:center}
.mark{background:#244dff;color:white;font-size:32px;line-height:46px;width:46px;height:46px;text-align:center;letter-spacing:-3px;padding-right:3px}
.serial{font-size:18px;font-weight:600;letter-spacing:1.3px;color:#656b76}
.eyebrow{margin:57px 0 20px;font-size:20px;line-height:1.3;letter-spacing:1.9px;text-transform:uppercase;font-weight:600;color:#244dff}
h1{font-size:82px;line-height:1.02;letter-spacing:-3.6px;font-weight:800;margin:0}
h1 em{font-style:normal;color:#244dff}
.lead{font-size:29px;line-height:1.38;letter-spacing:-.4px;color:#525863;margin:25px 0 0;max-width:1010px}
.visual{margin-top:48px;border:1px solid #d9dde4;background:white}
.visual img{display:block;width:100%;height:auto}
.visual .chrome{height:42px;background:#f0f2f5;border-bottom:1px solid #e0e3e9;display:flex;align-items:center;padding:0 20px;font-size:15px;letter-spacing:.2px;color:#646c7b;gap:13px}
.chrome .dot{width:7px;height:7px;border-radius:50%;background:#a4adbb;display:inline-block}
.chrome .address{margin-left:8px}
.stage{margin-top:48px;min-height:0}
.frame{border:1px solid #d9dde4;background:white;padding:16px}
.frame img{display:block;width:100%;height:auto;max-height:795px;object-fit:contain}
.detail{font-size:23px;line-height:1.5;margin:26px 0 0;color:#535b67;max-width:1000px}
.detail strong{color:#161a21;font-weight:600}
.small-note{font-size:19px;line-height:1.42;color:#676f7b;margin-top:16px;max-width:990px}
.footer{position:absolute;left:72px;right:72px;bottom:48px;padding-top:22px;border-top:1px solid #cdd2da;display:flex;justify-content:space-between;gap:20px;align-items:flex-end;font-size:18px;line-height:1.4;color:#6a707a}
.footer b{color:#14181e;font-weight:600}
.footer .count{font-size:22px;font-weight:600;letter-spacing:1px;color:#14181e;white-space:nowrap}
.s1 h1{font-size:88px}.s1 .lead{font-size:30px;color:#444b56}.s1 .visual{margin-top:40px}
.s1 .visual img{max-height:755px;object-fit:cover;object-position:top}
.s2 .frame{padding:24px}
.s3 h1{font-size:77px}.s3 .eyebrow{margin-top:46px}.s3 .lead{font-size:27px}
.s3 .frame{padding:12px}.s3 .frame img{max-height:785px}
.s4 h1{font-size:77px}.s4 .frame{padding:16px}.s4 .frame img{max-height:510px}
.code-title{font-size:17px;letter-spacing:1.5px;font-weight:600;margin:26px 0 13px;color:#244dff}
pre{margin:0;background:#111826;color:#edf2ff;padding:24px 30px;font:23px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;border-left:4px solid #244dff}
.s5 .eyebrow{margin-top:49px}.s5 h1{font-size:80px}
.s5 .visual img{max-height:520px;object-fit:contain}.integration{display:flex;gap:35px;margin:32px 0 0;padding:0 0 24px;border-bottom:1px solid #d9dde4;font-size:27px;font-weight:600}
.integration span+span:before{content:'/';padding-right:35px;color:#a1a7b0;font-weight:400}
.repo{font-size:27px;line-height:1.45;color:#111827;margin-top:23px;font-weight:600;letter-spacing:-.4px}
.repo a{color:inherit;text-decoration:none}.install{font-size:20px;line-height:1.5;color:#596273;margin-top:8px;word-break:break-word}
.install a{color:inherit;text-decoration:none}
@page{size:1200px 1500px;margin:0}
@media print{body{background:white}.slide{margin:0}}
"""


def top(n):
    return f'<div class="top"><div class="brand"><span class="mark">c.</span>Culture-Fit</div><span class="serial">OPEN SOURCE / HUMAN-IN-THE-LOOP</span></div>'


def footer(n, line="Actual product screenshots · Synthetic demo"):
    return f'<div class="footer"><span><b>Culture-Fit</b> / Human-in-the-Loop (HITL)<br>{line}</span><span class="count">0{n} / 05</span></div>'


def frame(name, cls="frame"):
    return f'<div class="{cls}"><img src="screenshots/{name}.png" alt="Actual Culture-Fit product screenshot"></div>'


def make_carousel(excerpt):
    slides = [
        top(1) + '<p class="eyebrow">Introducing Culture-Fit</p><h1>AI agents can talk.<br><em>Who gets to decide?</em></h1>'
        '<p class="lead">Open-source Human-in-the-Loop (HITL)<br>for multi-agent collaboration.</p>'
        '<div class="visual"><div class="chrome"><span class="dot"></span><span class="dot"></span><span class="dot"></span><span class="address">culture-fit-demo-production.up.railway.app</span></div><img src="screenshots/02-workspace.png" alt="The deployed Culture-Fit workspace"></div>'
        + footer(1),
        top(2) + '<p class="eyebrow">01 / Surface the authority conflict</p><h1>One approval.<br><em>Two owners.</em></h1>'
        '<p class="lead">Both agents have approval rights.<br>The decision owner is still unresolved.</p>'
        '<div class="stage">' + frame("03-authority-conflict") + '</div>'
        '<p class="detail"><strong>Check the task, action and delegated authority.</strong><br>Keep the decision linked to its original conversation evidence.</p>'
        + footer(2),
        top(3) + '<p class="eyebrow">02 / Involve the right people</p><h1>Let the right<br><em>people decide.</em></h1>'
        '<p class="lead">Record the owners’ agreed priority for this task.</p>'
        '<div class="stage">' + frame("05-owner-approvals") + '</div>'
        '<p class="small-note">Approvals are entered by a local operator.<br>External owner identities are not authenticated.</p>'
        + footer(3),
        top(4) + '<p class="eyebrow">03 / Return a usable next action</p><h1>Make the decision<br><em>agent-readable.</em></h1>'
        '<p class="lead">Re-evaluate authority against the recorded agreement.</p>'
        '<div class="stage">' + frame("06-authority-resolved") + '</div>'
        '<p class="code-title">ACTUAL API RESPONSE · SELECTED FIELDS</p><pre>' + escape(json.dumps(excerpt, indent=2)) + '</pre>'
        '<p class="small-note">This authority update makes no additional model call.<br>External task execution remains unverified.</p>'
        + footer(4),
        top(5) + '<p class="eyebrow">04 / Install in your own environment</p><h1>Bring it into<br><em>your agent stack.</em></h1>'
        '<p class="lead">Source, dashboard and setup instructions are available.</p>'
        '<div class="visual"><div class="chrome"><span class="address">How to use Culture-Fit / Download packages</span></div><img src="screenshots/08-source-and-skill.png" alt="Real source and OpenClaw Skill download options"></div>'
        '<div class="integration"><span>MCP tools</span><span>A2A interface</span><span>Reusable Skill</span></div>'
        f'<p class="repo"><a href="{GITHUB}">github.com/Ontology0/hanium-arbiter ↗</a></p>'
        f'<p class="install"><a href="{BASE}/download">{BASE.removeprefix("https://")}/download</a></p>'
        '<p class="small-note">Connect agents to your own local installation.<br>The hosted demo is a separate synthetic sandbox.</p>'
        + footer(5, "MIT licensed · English UI · English & Korean conversation analysis"),
    ]
    content = '\n'.join(f'<article class="slide s{i}" id="slide-{i}">{body}</article>' for i, body in enumerate(slides, 1))
    html = '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Culture-Fit — LinkedIn image kit</title><style>' + CSS + '</style></head><body>' + content + '</body></html>'
    (OUT / "carousel.html").write_text(html)


def render(browser):
    context = browser.new_context(viewport={"width": 1200, "height": 1500}, device_scale_factor=1)
    page = context.new_page()
    page.goto((OUT / "carousel.html").as_uri(), wait_until="load")
    page.evaluate("document.fonts.ready")
    page.wait_for_function("Array.from(document.images).every(i=>i.complete && i.naturalWidth>0)")
    overflow = page.evaluate("""() => Array.from(document.querySelectorAll('.slide')).flatMap(slide => {
        const footer = slide.querySelector('.footer').getBoundingClientRect();
        const bounds = slide.getBoundingClientRect();
        return Array.from(slide.children).filter(e=>!e.classList.contains('footer')).flatMap(e=>{
            const r=e.getBoundingClientRect();
            return r.bottom>footer.top-12 || r.right>bounds.right-30 || r.left<bounds.left
              ? [{slide:slide.id,element:e.className,bottom:r.bottom-bounds.top,footer:footer.top-bounds.top}] : [];
        });
    })""")
    if overflow:
        raise RuntimeError(json.dumps({"layout_overflow": overflow}))
    spacing = page.evaluate("""() => Array.from(document.querySelectorAll('.slide')).map(slide => {
        const lead = slide.querySelector('.lead');
        const frame = slide.querySelector('.frame, .visual');
        return {slide:slide.id, gap_css_px:frame.getBoundingClientRect().top-lead.getBoundingClientRect().bottom,
                shadow:getComputedStyle(frame).boxShadow};
    })""")
    assert all(row['gap_css_px'] >= 40 and row['shadow'] == 'none' for row in spacing), spacing
    names = ["01-introducing-culture-fit", "02-authority-conflict", "03-human-decision", "04-agent-readable-decision", "05-install-and-connect"]
    for i, name in enumerate(names, 1):
        page.locator(f"#slide-{i}").screenshot(path=str(IMAGES / (name + ".png")), animations="disabled")
    page.pdf(path=str(OUT / "culture-fit-linkedin-carousel.pdf"), print_background=True, prefer_css_page_size=True)
    context.close()
    pdf = pymupdf.open(OUT / "culture-fit-linkedin-carousel.pdf")
    assert len(pdf) == 5
    collisions, pdf_pages = [], []
    review = OUT / "pdf-review"
    review.mkdir(exist_ok=True)
    for page_number, p in enumerate(pdf, 1):
        assert "Human-in-the-Loop" in p.get_text()
        image_rects = [pymupdf.Rect(item['bbox']) for item in p.get_image_info()]
        text_rects = [pymupdf.Rect(block[:4]) for block in p.get_text('blocks') if block[6] == 0]
        for image_rect in image_rects:
            for text_rect in text_rects:
                intersection = image_rect & text_rect
                if not intersection.is_empty:
                    collisions.append({'page': page_number, 'image': list(image_rect), 'text': list(text_rect)})
        pdf_pages.append({'page': page_number, 'image_count': len(image_rects),
                          'inline_shadow_images': sum(item['xref'] == 0 for item in p.get_image_info(xrefs=True))})
        p.get_pixmap(matrix=pymupdf.Matrix(4/3, 4/3), alpha=False).save(review / f"page-{page_number:02d}.png")
    pdf.close()
    assert not collisions, collisions
    assert all(row['inline_shadow_images'] == 0 for row in pdf_pages), pdf_pages
    (OUT / 'pdf-layout-validation.json').write_text(json.dumps({
        'revision': 2, 'spacing': spacing, 'pages': pdf_pages,
        'image_text_intersections': collisions, 'pdf_pages_rendered_for_review': 5,
    }, indent=2) + '\n')
    return names


def package(browser, names, receipt):
    thumbs = ''.join(f'<figure><img src="images/{n}.png"><figcaption>{i:02d} / {escape(n[3:].replace("-", " "))}</figcaption></figure>' for i, n in enumerate(names, 1))
    proof = '<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;padding:34px;background:#e9eaed;font:18px Arial;color:#202630}.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:20px}figure{margin:0}img{width:100%;display:block;box-shadow:0 8px 18px #0001}figcaption{font-size:15px;margin-top:13px}h1{font-size:25px;margin:0 0 24px;font-weight:600}</style></head><body><h1>Culture-Fit / LinkedIn carousel · 5 actual-product slides</h1><div class="grid">' + thumbs + '</div></body></html>'
    (OUT / "contact-sheet.html").write_text(proof)
    page = browser.new_page(viewport={"width": 1640, "height": 540})
    page.goto((OUT / "contact-sheet.html").as_uri(), wait_until="load")
    page.screenshot(path=str(OUT / "preview.png"), full_page=True)
    page.close()
    posts = ''.join(f'<h2>{label}</h2><pre>{escape((OUT / filename).read_text())}</pre><a href="{filename}" download>Download text</a>' for label, filename in [("한국어 게시글", "post-ko.txt"), ("English post", "post-en.txt")])
    index = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Culture-Fit LinkedIn kit</title><style>body{max-width:1100px;margin:56px auto;padding:0 24px;background:#fbfbf9;color:#151920;font:17px/1.6 Arial,sans-serif}h1{font-size:40px;line-height:1.15}a{color:#244dff}nav{display:flex;flex-wrap:wrap;gap:24px;margin:26px 0}img{max-width:100%}pre{white-space:pre-wrap;background:white;border:1px solid #d9dde4;padding:28px;font:inherit}section{margin-top:48px}.images{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}.images img{width:100%}</style></head><body><h1>Culture-Fit / LinkedIn 게시 세트</h1><p>실제 공개 데모 캡처 · 이미지 5장 · 5쪽 PDF · 한국어/영어 문구</p><nav><a href="culture-fit-linkedin-kit.zip" download>전체 ZIP</a><a href="culture-fit-linkedin-carousel.pdf" download>카루셀 PDF</a><a href="post-ko.txt" download>한국어 문구</a><a href="post-en.txt" download>English copy</a><a href="posting-guide.txt">업로드 순서·캡션·대체 텍스트</a></nav><img src="preview.png" alt="Five LinkedIn carousel pages"><section><h2>이미지 파일</h2><div class="images">' + ''.join(f'<a href="images/{n}.png" download><img src="images/{n}.png" alt="Slide {i}"></a>' for i, n in enumerate(names, 1)) + '</div></section><section>' + posts + '</section><section><p>Public synthetic example · recorded analysis · no new model call or external execution. LinkedIn 게시 자체는 수행하지 않았습니다.</p></section></body></html>'
    (OUT / "index.html").write_text(index)
    assets = list(IMAGES.glob("*.png")) + list(RAW.glob("*.png"))
    dimensions = {}
    for path in assets:
        image = pymupdf.Pixmap(str(path))
        dimensions[str(path.relative_to(OUT))] = [image.width, image.height]
    assert all(dimensions[f"images/{n}.png"] == [1200, 1500] for n in names)
    validation = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "slides": 5,
                  "pdf_pages": 5, "png_pixels": [1200, 1500], "layout_overflow": [],
                  "images": dimensions, "actual_capture": receipt,
                  "pdf_layout": json.loads((OUT / 'pdf-layout-validation.json').read_text()),
                  "social_publication_performed": False}
    (OUT / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n")
    allowed = [OUT / n for n in ["index.html", "carousel.html", "preview.png", "contact-sheet.html",
                                "culture-fit-linkedin-carousel.pdf", "post-ko.txt", "post-en.txt",
                                "posting-guide.txt", "capture-receipt.json", "validation.json",
                                "next-action-excerpt.json", "build_assets.py", "pdf-layout-validation.json"]]
    allowed += assets + list((OUT / "fonts").iterdir())
    with zipfile.ZipFile(OUT / "culture-fit-linkedin-kit.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in allowed:
            archive.write(path, Path("culture-fit-linkedin-kit") / path.relative_to(OUT))
    print(json.dumps({"directory": str(OUT), "slides": 5, "raw_screenshots": len(receipt["screenshots"]),
                      "pdf_pages": 5, "layout_overflow": [], "page_errors": receipt["page_errors"],
                      "zip_bytes": (OUT / "culture-fit-linkedin-kit.zip").stat().st_size}, indent=2))


def main():
    for path in (RAW, IMAGES, OUT / "fonts"):
        path.mkdir(parents=True, exist_ok=True)
    for name in ("Pretendard-Regular.otf", "Pretendard-SemiBold.otf", "Pretendard-ExtraBold.otf", "LICENSE", "sources.json"):
        shutil.copyfile(ROOT / "docs/video/fonts" / name, OUT / "fonts" / name)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        if (OUT / "capture-receipt.json").exists() and "--recapture" not in sys.argv:
            receipt = json.loads((OUT / "capture-receipt.json").read_text())
            excerpt = json.loads((OUT / "next-action-excerpt.json").read_text())
        else:
            receipt, excerpt = capture(browser)
        make_carousel(excerpt)
        names = render(browser)
        package(browser, names, receipt)
        browser.close()


if __name__ == "__main__":
    main()
