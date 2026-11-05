"""Build editable diagrams with official logos and real, synthetic-demo screenshots.

Run: uv run --with playwright --with pymupdf python docs/build_diagrams.py
"""
from __future__ import annotations

import base64
from html import escape
import json
from pathlib import Path

from playwright.sync_api import sync_playwright
import pymupdf

OUT = Path(__file__).parent / "assets" / "diagrams"
INK, MUTED, LINE = "#17212d", "#526173", "#cbd3dc"
BLUE, ORANGE, GREEN = "#285bb4", "#af5b16", "#16705b"


def tag_text(x, y, content, size=23, color=INK, weight=400, anchor="start"):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}">{escape(content)}</text>'


def lines(x, y, values, size=23, color=MUTED, step=33):
    return "".join(tag_text(x, y+i*step, value, size, color) for i, value in enumerate(values))


def rect(x, y, w, h, fill="white", stroke=LINE, dash=None, radius=4):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2"'+(f' stroke-dasharray="{dash}"' if dash else "")+'/>'


def asset(name, x, y, w, h, folder="logos"):
    path = OUT / folder / name
    mime = "image/svg+xml" if path.suffix == ".svg" else "image/png"
    payload = base64.b64encode(path.read_bytes()).decode()
    return f'<image x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid meet" href="data:{mime};base64,{payload}"/>'


def arrow(points, color=BLUE, both=False, dashed=False):
    return f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.7" stroke-linejoin="round" marker-end="url(#{color[1:]})"'+(f' marker-start="url(#{color[1:]}-back)"' if both else "")+(' stroke-dasharray="8 6"' if dashed else "")+'/>'


def person(x, y, color=INK, scale=1):
    return f'<g transform="translate({x} {y}) scale({scale})" fill="white" stroke="{color}" stroke-width="3"><circle cx="0" cy="0" r="15"/><path d="M-29 51v-13c0-21 58-21 58 0v13z"/></g>'


def start(w, h, title, subtitle, category):
    markers = ""
    for c in (BLUE, ORANGE, GREEN, MUTED):
        markers += f'<marker id="{c[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="{c}"/></marker>'
        markers += f'<marker id="{c[1:]}-back" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M10 0L0 5L10 10z" fill="{c}"/></marker>'
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}"><title>{escape(title)}</title><defs>{markers}</defs><style>text{{font-family:Arial,"Apple SD Gothic Neo",sans-serif}}</style><rect width="100%" height="100%" fill="white"/>',
            tag_text(70, 60, f"CULTURE-FIT  /  {category}", 18, BLUE, 700),
            tag_text(70, 125, title, 48, INK, 700),
            tag_text(70, 174, subtitle, 24, MUTED)]


def architecture():
    s=start(2200, 1510, "Human-in-the-Loop coordination for AI agents", "An open-source HITL layer: connect evidence, check authority, and involve the right person.", "SYSTEM ARCHITECTURE")
    s += [rect(440, 230, 1280, 995, "#fbfcfe", LINE, "10 7"), tag_text(465, 270, "YOUR INSTALLATION  ·  Culture-Fit services", 22, BLUE, 700), tag_text(70, 270, "EXISTING TOOLS", 21, MUTED, 700), tag_text(1810, 270, "HUMAN OPERATOR", 21, MUTED, 700)]
    # Connections sit behind all nodes.
    s += [arrow("370,405 480,405"), arrow("370,650 480,650", both=True), arrow("370,895 480,895", both=True),
          arrow("780,405 815,405 815,382 850,382"), arrow("780,650 815,650 815,382 850,382", both=True),
          arrow("780,895 815,895 815,382 850,382", both=True),
          arrow("1040,445 1040,550", dashed=True), arrow("1220,660 1280,660"), arrow("1465,445 1465,550"),
          arrow("1040,780 1040,850"), arrow("1465,780 1465,850"),
          arrow("1040,990 1040,1070", both=True), arrow("1465,990 1465,1070", both=True),
          arrow("850,920 815,920 815,650 780,650", GREEN),
          arrow("1660,625 1810,625", ORANGE), arrow("1810,720 1660,720", ORANGE),
          arrow("1970,430 1970,490", MUTED)]
    # Product inputs.
    for y in (320, 565, 810): s.append(rect(70,y,300,170))
    s += [asset("slack.svg",94,346,65,65), tag_text(180,390,"Slack",32,INK,700), lines(94,445,["Bot messages", "Selected channels / threads"],21,step=29),
          asset("openclaw.svg",94,590,65,65), tag_text(180,635,"OpenClaw",29,INK,700), lines(94,689,["Your agent host", "Skill + Python helper"],21,step=29),
          asset("a2a.svg",94,837,64,64), tag_text(180,879,"Other agents",26,INK,700), lines(94,934,["Discover analysis capability", "Request a tracked task"],20,step=28)]
    # Adapters.
    for y in (320, 565, 810): s.append(rect(480,y,300,170))
    s += [tag_text(505,364,"Slack adapter",28,INK,700), lines(505,407,["Socket Mode events", "Filter · deduplicate · store", "No automatic LLM call"],20,step=29),
          asset("mcp-icon.png",504,586,40,40),tag_text(554,620,"MCP + Skill",27,INK,700),lines(505,664,["Report conversations", "Read authority / decisions", "8 MCP tools"],21,step=29),
          tag_text(505,855,"A2A adapter",28,INK,700),lines(505,898,["Agent Card discovery", "Send · Get · Cancel task", "Requests a model briefing"],20,step=29)]
    s += [rect(850,320,810,125), asset("fastapi.svg",878,342,170,45),tag_text(1090,377,"Shared conversation API",30,INK,700),tag_text(878,418,"Import / events  ·  rule-based wait candidates  ·  state and decisions",22,MUTED)]
    s += [tag_text(866,490,"Explicit web or A2A request",18,MUTED),tag_text(1330,490,"Current grants + scope",18,MUTED)]
    s += [rect(850,550,370,230),tag_text(875,594,"Evidence & issue extraction",24,INK,700),lines(875,640,["Local Codex CLI → LLM", "Decision scope and action", "Agreements / open questions", "Exact source-quote checks"],22,step=33),
          rect(1280,550,380,230,"#f0f5ff","#b5c9e9"),tag_text(1305,594,"Authority rule engine",26,INK,700),lines(1305,640,["Scope / action match", "Conditions · expiry · revocation", "Owner approvals + priority", "Re-evaluate without an LLM"],21,step=33)]
    s += [rect(850,850,810,140),tag_text(878,894,"Actionable coordination state",30,INK,700),lines(878,935,["Who can decide  ·  who must answer  ·  supporting evidence", "Next action: follow authority / wait for a person / refresh context"],22,step=31),tag_text(490,1082,"Agent reads the result",23,GREEN,700),lines(490,1120,["The connected agent chooses", "and performs the external work."],21,step=30)]
    s += [rect(850,1070,390,120),asset("sqlite.svg",875,1085,135,47),lines(1026,1106,["Durable SQLite", "Conversations, grants", "decisions and analysis"],19,step=27),
          rect(1280,1070,380,120),tag_text(1305,1106,"Typed relationship model",23,INK,700),lines(1305,1140,["Person · Agent · Task · Evidence", "Decision · Claim · Commitment"],19,step=28)]
    s += [person(1970,335,scale=1.1),tag_text(1970,418,"Agent owners / team operator",20,INK,500,"middle"),
          rect(1810,490,320,340,"#fffaf5","#e5c5a5"),tag_text(1836,539,"Decision dashboard",28,INK,700),lines(1836,584,["1. Read the conflict", "2. Inspect the evidence", "3. Record approvals", "4. Check the new owner"],23,step=48),
          tag_text(1732,610,"Review",18,ORANGE),tag_text(1732,749,"Record",18,ORANGE),
          lines(1810,880,["Approval records are operator input.", "Remote owner identity is not verified.", "Authority is not proof of factual truth."],19,step=31)]
    # Separate actual hosted deployment, not a claim that Slack is connected to it.
    s += [rect(70,1280,2060,154,"#f8f9fb",LINE,"8 6"),tag_text(95,1320,"PUBLIC VISITOR DEMO",22,BLUE,700),
          asset("docker.svg",100,1340,70,62),tag_text(186,1381,"Docker",23,INK,700),arrow("280,1372 330,1372",MUTED),asset("railway.svg",350,1340,60,62),tag_text(425,1381,"Railway",23,INK,700),arrow("535,1372 585,1372",MUTED),asset("sqlite.svg",607,1345,120,50),
          lines(790,1327,["Same core, isolated browser-cookie storage", "Recorded analysis + synthetic conversations; live LLM and Slack are disabled.", "The public demo URL is not an external MCP or A2A endpoint."],22,step=37),
          tag_text(70,1476,"Official technology logos identify components. Local integration setup is required. No external task execution is implied.",18,MUTED)]
    return "".join(s)+"</svg>"


def user_flow():
    s=start(2200,1580,"Know who can decide. Ask a human when it matters.","Human-in-the-Loop (HITL): two agents have different owners. The operator resolves who has authority.","USER JOURNEY")
    s += [rect(70,220,2060,145,"#f8f9fb"),person(115,255,scale=.75),tag_text(165,267,"ONE-TIME SETUP",20,BLUE,700),lines(165,304,["Connect your tools and record each agent’s owner, scope and delegated action."],23),
          asset("slack.svg",1220,245,54,54),tag_text(1290,283,"Slack",24,INK,700),asset("mcp-icon.png",1420,245,54,54),tag_text(1490,283,"MCP",24,INK,700),asset("openclaw.svg",1610,245,54,54),tag_text(1680,283,"OpenClaw Skill",24,INK,700),asset("a2a.svg",1950,245,54,54),tag_text(2020,283,"A2A",24,INK,700)]
    panels=[
        (70,"01","See the blocked decision",BLUE,"01-conflict-brief.png",["Read a focused question with its evidence.","See why neither agent can take priority yet."],"Authority conflict",["Release Agent and Review Agent have", "delegations from different owners."]),
        (780,"02","Record the owners’ decision",ORANGE,"02-owner-approval-form.png",["Choose the priority and record owner approvals.","Unselected owners are not treated as approving."],"Human intervention",["The operator records both owners’ approval", "for Review Agent to take priority."]),
        (1490,"03","Know who can proceed",GREEN,"03-resolved-authority.png",["The rule engine re-evaluates the same issue.","The agent can retrieve the updated next action."],"Review Agent can approve",["No new model call is needed for this", "authority update. External work stays separate."]),
    ]
    for x,n,title,color,screen,detail,big,outcome in panels:
        s += [tag_text(x,435,n,42,color,700),tag_text(x,490,title,30,INK,700),lines(x,535,detail,22,step=32),
              rect(x,605,640,460,"#fafbfc"),asset(screen,x+12,617,616,436,folder="screens"),
              tag_text(x,1123,big,30,color,700),lines(x,1170,outcome,23,step=33)]
    s += [arrow("725,824 765,824"),arrow("1435,824 1475,824",GREEN)]
    s += [rect(70,1260,2060,185,"#f8f9fb"),tag_text(100,1305,"WHERE THE HUMAN PARTICIPATES",23,BLUE,700),
          person(127,1350,ORANGE,.75),lines(180,1355,["Review the evidence and record a decision in the browser.","Routine follow-up uses the stored decision; new conflicts can still require another person."],25,step=39),
          tag_text(70,1490,"Screens: real Culture-Fit UI, synthetic example, translated replay of recorded analysis. Approval entries are demonstration records.",18,MUTED),
          tag_text(70,1525,"Slack / MCP / Skill / A2A are installation options. The public sandbox does not connect to your live workspace or execute a release.",18,MUTED)]
    return "".join(s)+"</svg>"


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    results={}
    with sync_playwright() as pw:
        chrome=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        browser=pw.chromium.launch(**({'executable_path':str(chrome)} if chrome.exists() else {}))
        for name,svg,w,h in [('system-architecture',architecture(),2200,1510),('user-flow',user_flow(),2200,1580)]:
            (OUT/f'{name}.svg').write_text(svg)
            html=f'<!doctype html><html lang="en"><meta charset="utf-8"><title>Culture-Fit {name}</title><style>@page{{size:{w}px {h}px;margin:0}}body{{margin:0;width:{w}px;height:{h}px}}svg{{display:block}}</style>{svg}</html>'
            path=OUT/f'{name}.html';path.write_text(html)
            page=browser.new_page(viewport={'width':w,'height':h},device_scale_factor=2)
            page.goto(path.resolve().as_uri(),wait_until='networkidle')
            page.evaluate('document.fonts.ready')
            checks=page.evaluate('''() => ({textOverflow:[...document.querySelectorAll('svg > text')].filter(el=>{const b=el.getBBox(),v=el.ownerSVGElement.viewBox.baseVal;return b.x<0||b.y<0||b.x+b.width>v.width||b.y+b.height>v.height}).map(el=>el.textContent), images:document.querySelectorAll('image').length})''')
            assert not checks['textOverflow'],checks
            page.screenshot(path=str(OUT/f'{name}.png'))
            page.pdf(path=str(OUT/f'{name}.pdf'),print_background=True,prefer_css_page_size=True)
            with pymupdf.open(OUT/f'{name}.pdf') as doc:
                assert len(doc)==1
                checks['pdf_pages']=len(doc)
                checks['pdf_text_chars']=len(doc[0].get_text())
            checks.update(width_px=w*2,height_px=h*2)
            results[name]=checks
            page.close()
        browser.close()
    (OUT/'validation.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))


if __name__=='__main__':main()
