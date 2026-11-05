"""Embed local screenshots and render the editable A1 poster as one-page PDF.

Run from the project root:
    uv run --with playwright --with pymupdf python docs/build_poster.py

Uses installed Google Chrome on macOS, or Playwright Chromium elsewhere.
HTML content remains editable; data-asset links refresh images on the next build.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
import re

import pymupdf
from playwright.sync_api import sync_playwright


DOCS = Path(__file__).resolve().parent
HTML = DOCS / "poster.html"
PDF = DOCS / "poster.pdf"
PREVIEW = DOCS / "poster-preview.png"


def embed(match: re.Match) -> str:
    tag = match.group()
    asset = re.search(r'data-asset="([^"]+)"', tag)
    if not asset:
        return tag
    path = DOCS / asset.group(1)
    if not path.is_file():
        raise FileNotFoundError(f"Missing poster screenshot: {path}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return re.sub(r'src="[^"]*"', f'src="data:image/png;base64,{encoded}"', tag)


def main() -> None:
    markup = re.sub(r"<img\b[^>]*>", embed, HTML.read_text(encoding="utf-8"))
    HTML.write_text(markup, encoding="utf-8")
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    with sync_playwright() as p:
        browser = p.chromium.launch(**({"executable_path": str(chrome)} if chrome.exists() else {}))
        page = browser.new_page(viewport={"width": 2246, "height": 3180}, device_scale_factor=1)
        page.goto(HTML.as_uri(), wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        checks = page.evaluate("""() => {
          const sheet = document.querySelector('.poster');
          const frame = sheet.getBoundingClientRect();
          return {
            projectName: document.querySelector('h1').textContent,
            pageHeight: frame.height, contentBottom: document.querySelector('.foot').getBoundingClientRect().bottom,
            brokenImages: [...document.images].filter(i => !i.complete || !i.naturalWidth).map(i => i.id),
            roundedContainers: [...sheet.querySelectorAll('*')].filter(el => parseFloat(getComputedStyle(el).borderTopLeftRadius) > 0).map(el => el.className),
            svgOverflow: [...sheet.querySelectorAll('.flow text')].filter(el => {
              const r = el.getBBox(), v = el.closest('svg').viewBox.baseVal;
              return r.x < v.x - .5 || r.y < v.y - .5 || r.x + r.width > v.x + v.width + .5 || r.y + r.height > v.y + v.height + .5;
            }).map(el => el.textContent),
            overflow: [...sheet.querySelectorAll('section, figure, figcaption, p, h1, h2, h3, footer')].filter(el => {
              const r = el.getBoundingClientRect();
              return r.right > frame.right + .5 || r.bottom > frame.bottom + .5 || r.left < frame.left - .5;
            }).map(el => el.className || el.tagName)
          };
        }""")
        if (checks["overflow"] or checks["brokenImages"] or checks["roundedContainers"] or checks["svgOverflow"]
                or checks["projectName"] != "컬처핏(Culture-Fit)"):
            raise RuntimeError(json.dumps(checks, ensure_ascii=False))
        page.pdf(path=str(PDF), prefer_css_page_size=True, print_background=True)
        browser.close()
    with pymupdf.open(PDF) as pdf:
        assert len(pdf) == 1, f"Expected one page, got {len(pdf)}"
        page = pdf[0]
        expected = (594 / 25.4 * 72, 841 / 25.4 * 72)
        assert abs(page.rect.width - expected[0]) < 2 and abs(page.rect.height - expected[1]) < 2
        extracted = page.get_text()
        for fragment in ("컬처핏", "Culture-Fit", "권한", "기획의 출발과 전환", "KG-RAG", "서비스 구현 화면", "팀번호", "이화여자대학교", "이다영", "박세령", "손현경", "박정두"):
            assert fragment in extracted, f"Missing PDF text: {fragment}"
        assert "\ufffd" not in extracted, "Replacement glyph found in PDF"
        page.get_pixmap(dpi=85, alpha=False).save(PREVIEW)
        checks.update(pdfPages=len(pdf), pdfSizePoints=[page.rect.width, page.rect.height], textCharacters=len(extracted))
    validation = json.dumps(checks, ensure_ascii=False, indent=2)
    (DOCS / "poster-validation.json").write_text(validation + "\n", encoding="utf-8")
    print(validation)


if __name__ == "__main__":
    main()
