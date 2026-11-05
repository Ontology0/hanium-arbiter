#!/usr/bin/env python3
"""A4-readable internal architecture supplement, verified against local source."""
from __future__ import annotations
import base64
import hashlib
import html
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "assets" / "report-system-architecture"
W, H = 1200, 1680
INK, MUTED, TEAL, BLUE, ORANGE = "#172431", "#526374", "#087e77", "#245c9f", "#ad5b18"
parts: list[str] = []


def rect(name, x, y, w, h, fill="#ffffff", stroke="#c4cfd9"):
    parts.append(f'<rect id="{name}" x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')


def txt(text, x, y, size=25, weight=450, color=INK, owner=None, align="start"):
    tag = f' data-owner="{owner}"' if owner else ""
    role = ' data-role="code"' if size < 24 else ' data-role="label"'
    parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{align}"{tag}{role}>{html.escape(text)}</text>')


def path(points, color=BLUE, arrow=True, dashed=False, both=False):
    route = " ".join(("M" if i == 0 else "L") + f" {x} {y}" for i, (x, y) in enumerate(points))
    end = f' marker-end="url(#{"amber" if color == ORANGE else "arrow"})"' if arrow else ""
    start = ' marker-start="url(#back)"' if both else ""
    dash = ' stroke-dasharray="7 5"' if dashed else ""
    parts.append(f'<path d="{route}" fill="none" stroke="{color}" stroke-width="2.1"{end}{start}{dash}/>')


def main():
    # The fixed 1200px layout yields 9.18pt for a 24px label at 16.2cm width.
    font = base64.b64encode((ROOT / "video/motion/work/PretendardVariable.ttf").read_bytes()).decode()
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    parts.append(f'<style>@font-face{{font-family:ReportSans;src:url(data:font/ttf;base64,{font})}}text{{font-family:ReportSans,sans-serif}}</style>')
    parts.append('<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8Z" fill="#245c9f"/></marker><marker id="back" markerWidth="8" markerHeight="8" refX="1" refY="4" orient="auto"><path d="M8 0L0 4L8 8Z" fill="#245c9f"/></marker><marker id="amber" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8Z" fill="#ad5b18"/></marker></defs>')
    rect("canvas", 0, 0, W, H, "white", "white")
    txt("Culture-Fit  |  내부 처리 구조", 44, 59, 40, 750)
    txt("대화 수집 → 근거 추출 → 위임권한 판정 → 사람 개입 → 최신 상태 조회", 44, 104, 25, 500, MUTED)

    inputs = [
        (44, "web", "Web 가져오기", "대화 붙여넣기", "세션·이벤트 API", "app.py"),
        (326, "slack", "Slack 수신기", "Socket Mode 이벤트", "채널·중복 필터", "slack_bridge / slack_ingest"),
        (608, "mcp", "MCP · Skill", "8 도구 · stdio/HTTP", "Skill → HTTP API", "mcp_server · arbiter_client"),
        (890, "a2a", "A2A 어댑터", "AgentCard · Send", "Get · Cancel · Task", "a2a_server.py · SQLite"),
    ]
    for x, name, title, one, two, code in inputs:
        rect(name, x, 142, 266, 180)
        txt(title, x + 17, 184, 27, 700, BLUE, name)
        txt(one, x + 17, 229, 24, 450, INK, name)
        txt(two, x + 17, 265, 24, 450, INK, name)
        txt(code, x + 17, 303, 18, 450, MUTED, name)
        path([(x + 133, 322), (x + 133, 351)], arrow=False)
    path([(177, 351), (1023, 351)], arrow=False)
    path([(394, 351), (394, 390)])

    rect("api", 44, 390, 700, 164, "#f7fafc")
    txt("공통 API · 대화 상태 정규화", 66, 432, 30, 700, INK, "api")
    txt("FastAPI(app.py) → conversations.py", 66, 470, 25, 550, BLUE, "api")
    txt("세션·발언 ID·출처·결정 요청 상태 유지", 66, 507, 25, 450, INK, "api")
    txt("이벤트 추가 → 규칙 재분석", 66, 540, 25, 450, INK, "api")
    rect("sqlite", 800, 390, 356, 164, "#f7fafc")
    txt("SQLite · SessionStore", 821, 432, 27, 700, INK, "sqlite")
    txt("세션·메시지·브리핑", 821, 471, 25, 450, INK, "sqlite")
    txt("위임·우선권·사람 결정", 821, 508, 25, 450, INK, "sqlite")
    txt("storage.py · WAL", 821, 539, 20, 450, MUTED, "sqlite")
    path([(751, 470), (791, 470)], both=True)
    path([(394, 554), (394, 575), (309, 575), (309, 604)])
    path([(394, 575), (891, 575), (891, 604)])

    rect("rules", 44, 604, 530, 202)
    txt("규칙 기반 후보 탐지", 66, 647, 29, 700, INK, "rules")
    txt("conversations.py · domain.py", 66, 682, 22, 500, MUTED, "rules")
    txt("확인 약속·책임 미정·대기 후보", 66, 723, 25, 450, INK, "rules")
    txt("입력 이벤트와 사람의 답으로 상태 갱신", 66, 761, 25, 450, INK, "rules")
    rect("brief", 626, 604, 530, 202)
    txt("요청 기반 LLM 브리핑", 648, 647, 29, 700, INK, "brief")
    txt("briefing.py · providers.py", 648, 682, 22, 500, MUTED, "brief")
    txt("웹 / A2A 요청 → Codex CLI", 648, 723, 25, 450, INK, "brief")
    txt("결정 scope/action · 원문 인용 검증", 648, 761, 25, 450, INK, "brief")
    txt("Slack·MCP 수신은 모델을 자동 호출하지 않음", 648, 792, 24, 450, MUTED, "brief")
    path([(309, 806), (309, 834), (600, 834)], arrow=False)
    path([(891, 806), (891, 834), (600, 834), (600, 869)])

    rect("authority", 44, 869, 1112, 189, "#f0f8f6", "#78aaa3")
    txt("규칙 기반 위임권한 판정", 66, 913, 31, 750, TEAL, "authority")
    txt("authority.py · evaluate_authority", 1133, 911, 22, 500, MUTED, "authority", "end")
    txt("위임: 소유자·에이전트·대상·행동", 66, 960, 25, 550, INK, "authority")
    txt("모든 소유자의 유효 위임을 함께 판정", 643, 960, 25, 550, INK, "authority")
    txt("조건 · 만료 · 철회 상태 검증", 66, 1002, 25, 450, INK, "authority")
    txt("공동 우선권 + 정확한 위임 스냅샷 결속", 643, 1002, 25, 450, INK, "authority")
    txt("범위별 승인을 재사용하고, 새 판단이 필요한 결정에만 사람 개입을 제시", 66, 1040, 24, 450, MUTED, "authority")
    path([(1156, 470), (1180, 470), (1180, 937), (1158, 937)], dashed=True)
    path([(600, 1058), (600, 1081), (309, 1081), (309, 1111)])
    path([(600, 1081), (891, 1081), (891, 1111)])

    rect("follow", 44, 1111, 530, 145)
    txt("유효한 권한 · 담당자 확인", 66, 1152, 27, 700, TEAL, "follow")
    txt("남은 질문이 없으면 follow_authority", 66, 1193, 25, 450, INK, "follow")
    txt("외부 업무 실행은 연결 에이전트의 역할", 66, 1232, 24, 450, MUTED, "follow")
    rect("human", 626, 1111, 530, 145, "#fffaf4", "#d7b691")
    txt("미해결 · wait_for_human", 648, 1152, 27, 700, ORANGE, "human")
    txt("원문 근거·관련 소유자·구체적 질문", 648, 1193, 25, 450, INK, "human")
    txt("UI에 승인 기록 · 오래된 화면은 409", 648, 1232, 24, 450, MUTED, "human")
    # Local operator writes grants/precedence and then queries refreshed authority.
    path([(1156, 1184), (1192, 1184), (1192, 986), (1158, 986)], color=ORANGE)
    path([(309, 1256), (309, 1278), (600, 1278)], arrow=False)
    path([(891, 1256), (891, 1278), (600, 1278), (600, 1300)])

    rect("projection", 44, 1300, 1112, 119, "#f7fafc")
    txt("권한 기록 후 재평가 · UI / MCP / Skill에 같은 최신 상태 제공", 66, 1341, 28, 700, BLUE, "projection")
    txt("GET session / brief / next-action  ·  모델 재호출 없이 위임권한 갱신", 66, 1376, 25, 450, INK, "projection")
    txt("app.py: coordination_snapshot  ·  briefing.py: brief_view  ·  coordination_advice.py", 66, 1404, 20, 450, MUTED, "projection")

    rect("public", 44, 1461, 1112, 122, "#f3f6fa", "#9cafc4")
    txt("별도 공개 체험 영역 · Railway", 66, 1498, 29, 700, BLUE, "public")
    txt("서명 쿠키별 SQLite 분리 · 합성 대화 + 기록된 분석 재생", 66, 1536, 25, 450, INK, "public")
    txt("외부 모델·Slack 차단 · 공개 주소는 MCP/A2A 엔드포인트 아님", 66, 1569, 24, 450, INK, "public")
    txt("검증 경계: 실 Slack 계정·원격 소유자 신원 인증·외부 업무 실행은 미검증", 44, 1624, 24, 500, MUTED)
    txt("근거: backend/arbiter/ 위 모듈, deployment.py · skills/arbiter-coordination/scripts/arbiter_client.py", 44, 1659, 19, 450, MUTED)
    parts.append("</svg>")
    svg = "\n".join(parts)
    OUT.with_suffix(".svg").write_text(svg)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless=True)
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_content(f'<html><head><style>html,body{{margin:0}}@page{{size:162mm 226.8mm;margin:0}}svg{{display:block;width:100%;height:auto}}@media print{{body{{width:162mm}}}}</style></head><body>{svg}</body></html>')
        page.evaluate("document.fonts.ready")
        validation = page.evaluate('''() => {
          const texts = [...document.querySelectorAll('svg text')].map(t => { const b=t.getBBox();return {text:t.textContent,owner:t.dataset.owner,role:t.dataset.role,font:Number(t.getAttribute('font-size')),x:b.x,y:b.y,width:b.width,height:b.height}; });
          const overflow=[];
          for(const t of texts){if(t.owner){const r=document.getElementById(t.owner).getBBox();if(t.x<r.x+8||t.x+t.width>r.x+r.width-8||t.y<r.y+7||t.y+t.height>r.y+r.height-5)overflow.push(t);}else if(t.x<20||t.x+t.width>1180||t.y<10||t.y+t.height>1676)overflow.push(t);}
          const overlap=[];for(let i=0;i<texts.length;i++)for(let j=i+1;j<texts.length;j++){const a=texts[i],b=texts[j];if(Math.min(a.x+a.width,b.x+b.width)>Math.max(a.x,b.x)&&Math.min(a.y+a.height,b.y+b.height)>Math.max(a.y,b.y))overlap.push([a.text,b.text]);}
          return {overflow,overlap,minimumLabelPx:Math.min(...texts.filter(t=>t.role==='label').map(t=>t.font)),texts};
        }''')
        page.screenshot(path=str(OUT.with_suffix(".png")), full_page=True)
        page.pdf(path=str(OUT.with_suffix(".pdf")), prefer_css_page_size=True, print_background=True)
        browser.close()
    validation.update({"width": W, "height": H, "pngScale": 2, "intendedWidthCm":16.2,"minimumLabelPtAtIntendedWidth":24*(16.2/2.54*72)/W,"pageErrors":errors,"codeFootersMayBeSmaller":True})
    OUT.with_suffix(".validation.json").write_text(json.dumps(validation,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:v for k,v in validation.items() if k!='texts'},ensure_ascii=False,indent=2))
    if validation["overflow"] or validation["overlap"] or errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
