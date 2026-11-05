"""Fill a COPY of the supplied 2026 template; never modify the template itself."""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import subprocess
import uuid
import re
import json
import shutil
import time
import sys

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION_START, WD_ORIENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


ROOT = Path(__file__).resolve().parent
PROJECT = "컬처핏(Culture-Fit)"
TITLE = PROJECT
UNKNOWN = "확인 필요"
FONT = "맑은 고딕"


def write_paragraph(paragraph, text, size=10):
    paragraph.text = text
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.line_spacing = 1.15
    # The HWP-converted template snaps body text to an 18pt grid by default.
    # Keep the official tables and headings, but honor the explicit line spacing.
    grid = paragraph._p.get_or_add_pPr().find(qn("w:snapToGrid"))
    if grid is None:
        grid = OxmlElement("w:snapToGrid")
        paragraph._p.get_or_add_pPr().append(grid)
    grid.set(qn("w:val"), "0")
    for run in paragraph.runs:
        run.font.name = FONT
        run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT)
        run.font.size = Pt(size)
        run.font.color.rgb = RGBColor(0, 0, 0)


def write_cell(cell, text, size=9):
    cell.text = ""
    for index, line in enumerate(text.split("\n")):
        write_paragraph(cell.paragraphs[0] if index == 0 else cell.add_paragraph(), line, size)


def cell(table, row, col):
    # The supplied HWP-exported schedule has an uneven grid; row access preserves it.
    return table.rows[row].cells[col]


def picture(cell_, path, caption, width=6):
    cell_.text = ""
    paragraph = cell_.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run().add_picture(str(path), width=Cm(width))
    write_paragraph(cell_.add_paragraph(), caption, 8)


def make_architecture(output: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
    font_manager.fontManager.addfont("/System/Library/Fonts/AppleSDGothicNeo.ttc")
    plt.rcParams["font.family"] = "Apple SD Gothic Neo"
    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=180)
    ax.set(xlim=(0, 11), ylim=(0, 5.2)); ax.axis("off")
    boxes = [(0.1, 3.5, 2.4, 1.1, "대화 입력\nSlack · 붙여넣기 · A2A"),
             (3.1, 3.5, 3.0, 1.1, "LLM 구조화 추출\n결정 대상 · 행동 · 원문 인용"),
             (6.7, 3.5, 4.1, 1.1, "규칙 기반 권한 판정\nscope/action · 만료 · 조건 · 우선권"),
             (6.7, 1.75, 1.9, 1.05, "유효 권한 존재\n담당 에이전트 제시"),
             (8.9, 1.75, 1.9, 1.05, "공백 · 충돌\n사람에게 질문"),
             (2.9, 1.75, 3.1, 1.05, "사람의 위임 레지스트리\n로컬 운영자 입력 · MCP 조회"),
             (0.1, 0.15, 10.7, 0.95, "관제 화면 · 원문 근거 · SQLite 기록 · MCP 조회 · A2A 분석 artifact\n로컬 승인 기록 ≠ 원격 소유자 인증     |     분석 완료 ≠ 외부 업무 실행 완료")]
    for x,y,w,h,label in boxes:
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.025,rounding_size=0.08",facecolor="#f3f5f7",edgecolor="#24394b",linewidth=1.0))
        ax.text(x+w/2,y+h/2,label,ha="center",va="center",fontsize=10.8,color="#142333",linespacing=1.5)
    for start,end in [((2.5,4.05),(3.1,4.05)),((6.1,4.05),(6.7,4.05)),((6.0,2.3),(7.2,3.5)),((7.7,3.5),(7.7,2.8)),((9.8,3.5),(9.8,2.8)),((7.7,1.75),(7.7,1.1)),((9.8,1.75),(9.8,1.1))]:
        ax.add_patch(FancyArrowPatch(start,end,arrowstyle="-|>",mutation_scale=12,linewidth=1.1,color="#456274"))
    fig.tight_layout(pad=0.5)
    output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(output,bbox_inches="tight",facecolor="white")
    plt.close(fig)


def append_technical_detail(doc, anchor):
    """Add readable technical pages without changing the official 34 tables."""
    sections = json.loads((ROOT / "submission/report-technical-sections.json").read_text())
    for item in sections:
        heading = doc.add_paragraph()
        anchor._p.addprevious(heading._p)
        write_paragraph(heading, item["title"], 12)
        heading.runs[0].bold = True
        heading.paragraph_format.space_after = Pt(8)
        heading.paragraph_format.keep_with_next = True
        heading.paragraph_format.page_break_before = True
        for text in item["paragraphs"]:
            p = doc.add_paragraph()
            anchor._p.addprevious(p._p)
            write_paragraph(p, text, 9 if text.startswith("근거:") else 10)
            p.paragraph_format.line_spacing = 1.15
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.widow_control = True
    diagrams = [
        ("상세 구성도 A. 내부 모듈과 판단의 경계", "assets/report-system-architecture.png", False,
         "명시적 분석 요청·인용 검증·권한 재판정·공개 체험을 구분한 현재 구현도. 본문 라벨은 A4 16.2cm 폭에서 9pt 이상이며 세부 설명은 앞의 상세 설계를 따른다."),
        ("상세 구성도 B. 전체 시스템과 외부 연결", "assets/diagrams/system-architecture.png", True,
         "연결 선택지를 포함한 전체 구조. Slack 실계정 수신·OpenClaw 실제 모델 사용은 미검증이다. 공개 체험은 개인 MCP/A2A 접속점이 아니며 외부 실행은 연결한 에이전트의 별도 책임이다."),
        ("상세 구성도 C. 근거 확인에서 공동 승인 기록까지", "assets/diagrams/user-flow.png", True,
         "합성 예제·저장 분석을 사용하는 실제 영어 UI. 그림의 승인 해소는 해당 결정 범위에 한정되며, 다른 질문이 남으면 next-action은 계속 대기할 수 있다. 원격 소유자 인증이나 배포 실행의 증거가 아니다."),
    ]
    for title, name, landscape, caption in diagrams:
        page = doc.add_section(WD_SECTION_START.NEW_PAGE)
        page.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
        page.page_width, page.page_height = (Cm(29.7), Cm(21)) if landscape else (Cm(21), Cm(29.7))
        page.top_margin = page.bottom_margin = Cm(1.0 if landscape else 1.5)
        page.left_margin = page.right_margin = Cm(1.4 if landscape else 2.0)
        p = doc.add_paragraph()
        write_paragraph(p, title, 12)
        p.runs[0].bold = True
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.keep_with_next = True
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1
        p.add_run().add_picture(str(ROOT / name), width=Cm(24.0 if landscape else 16.2))
        p = doc.add_paragraph()
        write_paragraph(p, caption, 8)
        p.paragraph_format.space_after = Pt(0)


def append_service_screens(doc):
    """Three portrait appendix sections; preserve each 1600x800 source ratio."""
    pages = [
        (
            "실제 서비스 화면 1. 제품 소개와 설치 자료",
            "현재 배포된 영어 서비스의 제품 소개와 다운로드 화면이다. 공개 체험을 바로 열거나 소스 ZIP을 받아 자기 환경에서 실행할 수 있다. 아래 이미지는 제품 영상 제작 때 실제 웹에서 캡처한 원본이다.",
            [
                ("01-product-landing.png", "그림 5. 제품 첫 화면. Human-in-the-Loop(HITL)의 목적과 공개 체험·개인 설치 진입점을 안내한다."),
                ("02-source-and-skill.png", "그림 6. 다운로드 화면. MCP 서버·대시보드 소스 ZIP과 OpenClaw Skill ZIP을 구분하고 영어 UI·한국어와 영어 대화 분석 지원을 안내한다."),
            ],
            "서비스: https://culture-fit-demo-production.up.railway.app/  |  설치 자료: /download  |  공개 체험: /workspace. 소스 ZIP 실행은 로컬 환경이며 공개 체험의 합성 데이터와 구분한다.",
        ),
        (
            "실제 서비스 화면 2. 권한 충돌과 공동 승인 입력",
            "공개 체험의 합성 대화에서 payment-release-1.2 / approve에 대한 서로 다른 소유자의 권한이 겹친 사례다. 저장된 모델 분석에 현재 위임 규칙을 대조하며, 운영자가 해당 범위의 우선순위와 승인 여부를 기록한다.",
            [
                ("10-authority-conflict.png", "그림 7. 권한 충돌. Release Agent와 Review Agent가 후보이고 담당자는 Unknown으로 표시된다. Owner A와 Owner B의 판단이 필요한 상태다."),
                ("16-both-owner-approvals.png", "그림 8. 저장 전 입력. Review Agent를 우선으로 놓고 두 소유자의 체크박스를 선택했다. 이 화면만으로 저장·승인 적용이 완료됐다고 보지 않는다."),
            ],
            "두 체크박스는 운영자가 입력하는 승인 기록이다. 실제 원격 소유자의 신원·동의를 인증한 증거가 아니며, 저장 후 다시 평가된 결과는 다음 쪽에서 확인한다.",
        ),
        (
            "실제 서비스 화면 3. 저장 후 담당자 확인",
            "우선순위와 관련 소유자의 승인 기록을 저장한 뒤 동일한 결정 범위의 판정이 갱신된 화면이다. 이 결과와 외부 업무의 실행 완료는 구분한다.",
            [
                ("17-review-agent-authorized.png", "그림 9. 저장 후 결과. payment-release-1.2 / approve의 Decision owner가 Review Agent로 표시되고, 이 브리핑의 개입 지점은 0개다."),
            ],
            "화면 해석: 적용된 우선순위는 Review Agent → Release Agent이며, 현재 위임에 기록된 소유자 승인을 대조한 결과다. 화면 아래 Decision brief는 과거 모델 분석의 재생임을 표시한다. 권한 변경의 재평가는 새 모델 호출 없이 이루어진다.\n\n검증 경계: 공개 체험의 대화·소유자·업무는 합성 예제이며 승인 입력은 운영자 기록이다. 이 그림은 실제 배포 실행이나 원격 소유자 인증의 증거가 아니다. 다른 범위의 질문이 남은 세션은 계속 wait_for_human일 수 있다.\n\n제품 영상: 한국어 https://youtu.be/NO08LQL7ekU  |  영어 https://youtu.be/oP9F6zEm9RM . 각 3분이며 설치·첫 실행과 실제 영어 서비스의 흐름을 보여준다.\n\n캡처 근거: docs/video/captures/product/의 원본 PNG 5개, docs/video/PRODUCT-README.md 및 product-references.json. 화면 자체와 설명용 구성도를 구분하여 보존했다.",
        ),
    ]
    for title, introduction, pictures, note in pages:
        section = doc.add_section(WD_SECTION_START.NEW_PAGE)
        section.orientation = WD_ORIENT.PORTRAIT
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.top_margin = section.bottom_margin = Cm(1.5)
        section.left_margin = section.right_margin = Cm(2)
        paragraph = doc.add_paragraph()
        write_paragraph(paragraph, title, 12)
        paragraph.runs[0].bold = True
        paragraph.paragraph_format.keep_with_next = True
        paragraph.paragraph_format.space_after = Pt(6)
        paragraph = doc.add_paragraph()
        write_paragraph(paragraph, introduction, 9)
        for filename, caption in pictures:
            paragraph = doc.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.line_spacing = 1
            paragraph.paragraph_format.space_after = Pt(2)
            paragraph.paragraph_format.keep_with_next = True
            paragraph.add_run().add_picture(str(ROOT / "video/captures/product" / filename), width=Cm(16.2))
            paragraph = doc.add_paragraph()
            write_paragraph(paragraph, caption, 8.5)
            paragraph.paragraph_format.space_after = Pt(6)
        paragraph = doc.add_paragraph()
        write_paragraph(paragraph, note, 9)


def build(output: Path):
    template = ROOT / "templates/2026-result-report.docx"
    before = sha256(template.read_bytes()).hexdigest()
    doc = Document(template)
    paragraphs, tables = list(doc.paragraphs), list(doc.tables)
    # Retain all official headings, mandatory tables and schedule columns.
    write_cell(cell(tables[1],0,1), TITLE + "\n이화여자대학교 · 팀장 이다영 / 멘티 박세령·손현경\n멘토 박정두(네이버(주) Creator Hub 리더)\n등록 기간 2026.04.01~10.30(7월 개발보고서 기준)\n작성 초안 · 팀번호·월별 수행내역 확인 필요", 10)
    write_cell(cell(tables[3],1,1), TITLE, 10)
    write_cell(cell(tables[3],2,2), "☑ 업무")
    write_cell(cell(tables[3],4,1), "☑ 소프트웨어")
    write_cell(cell(tables[3],4,2), "☑ 인공지능")
    summaries = {
        8: "에이전트 협업 대화에서 결정 대상과 사람의 위임권한을 연결하는 관제 시스템이다.\nHITL 탐지·A2A 분석 서비스·MCP 도구를 제공한다.",
        9: '생성형 AI의 근거·판단을 검증하고 관리한다는 목표를 이어 왔다.\n콘텐츠 고증·지식 충돌 해결에서 협업의 결정·위임 관제로 범위를 발전시켰다.',
        10: "모델은 원문 근거와 결정 대상을 추출하고 별도 규칙이 위임 범위를 판정한다.\n권한 공백·소유자 간 충돌이면 반복 대기를 기다리지 않고 사람 질문을 제시한다.",
        11: "대화 수집, 근거 인용 브리핑, 범위별 권한·우선권 판정과 결정 기록을 구현하였다.\nAgentCard 분석 요청, MCP 조회, 읽기 전용 Slack 수신 구성을 제공한다.",
        12: "협업 상태·권한 근거를 함께 보여 사람의 확인과 책임 판단을 지원하는 것이 목표다.\n전 세계 개발자·운영팀·전문가가 기존 환경에 연결해 쓰는 오픈소스 활용을 지향한다.",
    }
    for row,text in summaries.items():write_cell(cell(tables[3],row,1),text,9)

    content = {
        27: "1) 프로젝트 정의 및 목표",
        28: "- 컬처핏(Culture-Fit)은 전 세계 에이전트 개발자·운영팀·도메인 전문가가 기존 환경에 연결해 쓰는 Human-in-the-Loop(HITL) 오픈소스 연결 계층을 목표로 한다. 웹 관제와 MCP·A2A로 결정 대상·위임·사람의 개입 근거를 연결한다.\n- 사람의 위임을 scope(대상 범위)·action(허용 행동)·유효기간·조건으로 기록한다. 자연어에서 추출한 결정과 이 기록을 비교하여 담당 에이전트 또는 사람이 필요한 질문을 제시한다.",
        32: '1) 생성형 AI의 검증·관리라는 공통 목표',
        33: '- 초기 개요서는 문화·역사 콘텐츠를 온톨로지와 KG-RAG로 검증하고 공인 사료 매칭·위험 대시보드를 제공하는 구상이었다. 역할별 에이전트가 분석·조회·검수를 분담하도록 기획했다.\n- 2026.07.12 개발보고서에서는 GitHub 문서 기반 RAG와 Telegram 질의응답으로 대상을 넓혔다. 검색 자료와 모델 지식의 충돌에 대해 수용·거부·유보(Accept·Reject·Abstain)를 선택하고 출처·불확실성을 확인하는 방향이었다.\n- 이후 긴 에이전트 대화, 확인 약속, 상호 검토 대기, 승인 후 미실행에 대한 사용자 관찰을 계기로 결정 대상·위임 범위·사람의 개입 지점으로 초점을 확장했다. 생성형 AI를 신뢰하고 활용하기 위한 구조화·근거 추적·검토 부담 완화라는 목표는 이어진다. 관찰만으로 무한루프나 실패율을 입증하지 않는다.\n- Anthropic의 MCP(2024.11.25)와 Google의 A2A(2025.04.09) 공개로 도구·데이터 접근과 에이전트 협업을 연결할 공통 기반이 구체화되었다. Li·Xie(2025)는 통합 시 작업 의미의 정합성, 정책 관리와 실행 추적이 함께 필요하다고 분석했다. 기존 HITL의 중단·재개 수단과 연결할 수 있도록 우리는 결정 대상·위임 범위·개입 이유를 설명하는 관제에 집중했다.\n- 팀은 분야별 전문 판단은 도메인 전문가에게 맡기고, 여러 에이전트와 분야 사이에서 재사용할 권한·근거·HITL 연결 계층을 오픈소스로 제공하는 데 공학적 의의를 두었다. 개인 설치에서는 브리핑에 LLM을 사용한다. 영문 체험 웹·설치 ZIP을 배포했고 소스는 PR #2 병합 후 main에 MIT로 공개했다. 이전 KG-RAG·DPO 모델의 통합 완성품으로 설명하지 않는다.',
        37: "1) 권한을 기준으로 개입 지점을 설명",
        38: '- 결정 단위의 근거: 일반 대화 요약에서 한 걸음 더 나아가 무엇을 결정할지(scope), 어떤 행동인지(action), 관련 발화와 사람의 위임을 같은 항목에 연결한다. 인용을 통해 해석의 출발점을 확인할 수 있다.\n- 적절한 HITL: Microsoft는 외부 응답 대기·재개를, Palantir는 권한 제어와 사람의 검토·결정 경로를 제공한다. 본 구현은 정보·선호·전문가 판단·승인이 필요할 때 언제 누구에게 무엇을 어떤 근거로 물을지에 집중한다. 최초성·비교 우월성은 주장하지 않는다.\n- 업무별 권한: 같은 소유자의 에이전트도 범위·행동마다 위임이 다르다. 서로 다른 소유자가 같은 결정을 맡으면 관련 소유자 전원의 승인 기록이 있는 우선권을 요구한다. 발언 순서·자신감·대화 길이로 전역 서열을 만들지 않는다.\n- 상태의 구분: 확인 약속, 실제 요청 전달, 사람의 답변, 외부 작업 완료를 서로 다른 상태로 기록한다. 이미 승인된 결정은 권한의 부재와 실행 근거의 부재를 구분하여 표시한다.\n- 재사용 구조: MCP·A2A와 구조화된 상태·근거 추적·HITL 코어를 기존 에이전트 환경에 연결하도록 설계했다. 분야별 판단과 위임 규칙은 각 도메인 전문가가 맡고 웹 관제는 같은 코어를 활용한다.\n- 현재 한계: 위임·공동 승인은 로컬 운영자 기록이며 외부 소유자 인증이 아니다. Slack 실계정 수신, 사용자 부담 감소와 독립 권한 탐지 정확도는 후속 검증 범위다. 영문 화면·한국어와 영어 입력 지원은 다국어 정확도 평가와 구분한다.',
        46: "1) 동일 분석 코어를 사용하는 세 가지 입구",
        47: "- Slack/대화 입력 → 결정 대상·인용 근거 추출 → 권한 규칙 대조 → 담당자 또는 사람 질문 → 관제 기록·조회.\n- A2A는 다른 에이전트의 분석 위임, MCP는 작업 중인 에이전트의 사건 보고·결정 조회를 담당한다.",
        66: "- 추가설명: 화면의 발화와 결정은 최신 영어 공개 체험의 합성 예제이다. 모델 해석·사람의 기록·외부 실행 증거를 서로 다른 상태로 표시한다.",
        71: "- 추가설명: 별도 제작 하드웨어가 없는 소프트웨어 과제이며 H/W 필수 표는 유지하였다.",
        75: "1) 구조화 추출과 권한 판정의 결합",
        76: "- LLM이 결정의 scope/action, 관련 발화자, 미해결·승인 후 미실행·차단 상태와 원문 인용을 추출한다. 인용은 실제 메시지 ID와 부분 문자열이 일치해야 저장되며, 이것만으로 의미적 정확성까지 보증하지는 않는다.\n- 규칙 엔진은 정확한 scope/action의 권한만 선택하고 철회·만료 권한을 제외한다. 조건 충족이 확인되지 않으면 자동 허용하지 않는다. 유효한 담당자/우선권이 없거나 다른 소유자 사이 충돌이 있으면 사람 질문을 만든다.\n- MCP에는 사람 결정·위임을 변경하는 도구를 제공하지 않고 로컬 운영자 입력으로 구분한다. 개인 설치의 HTTP 쓰기 API는 소유자 인증이 없으며 공개 체험의 방문자 쿠키도 소유자 신원·동의를 증명하지 않는다.\n- UI 승인 기록은 업무 범위와 위임 스냅샷에 연결한다. 오래된 화면의 저장은 409로 거절하며, 목록 필터로 다른 소유자의 충돌을 숨길 수 없도록 범위 전체의 권한을 판정한다.",
        86: '- 제품 소개·설치 영상: docs/video/culture-fit-product-ko-1080p.mp4 및 culture-fit-product-en-1080p.mp4 (각 3분, 1920×1080). 영어 UI를 공통으로 쓰며 한국어·영어 음성과 자막은 각각 별도 제작했다. 영문 공개 영상: https://youtu.be/oP9F6zEm9RM . 한국어 공개 영상: https://youtu.be/NO08LQL7ekU .',
        87: '- 시연: 제품의 역할 → 소스 ZIP 설치와 빈 첫 화면 → 합성 공개 체험 → 근거·권한 충돌 확인 → 부분·공동 승인 기록 → 담당자 확인. 실제 영어 UI 143초와 Three.js 설명 37초를 포함한다. 원문·검증 기록·음성 출처는 docs/video/PRODUCT-README.md와 product-validation-ko/en.json에 보존한다.',
        114: '- 문제: 문화·역사 고증 → GitHub RAG·지식 충돌 해결 → 에이전트 협업 관제로 대상이 바뀌며 공통 목적과 최종 구현 범위를 설명할 필요가 있었다.\n- 대응: 생성형 AI의 근거·판단을 검증하고 관리한다는 목표 아래, 팀은 특정 LLM 호출 서비스보다 도메인 전문가가 재사용할 연결 계층에 집중하기로 판단했다. 프로토콜·상태·결정 책임·검증 기록을 분리하고 초기 목표와 현재 결과를 구분했다.\n- 초기 80% 시간 감소·최대 1,200만 원 절감과 논문·공모전은 목표이며 실적이 아니다. 7월 보고서의 등록 기간은 출처를 붙이고, 당시 자체 진척률·모델 연구를 현재 관제의 통합 검증 성과로 합산하지 않았다. 개인별 업무·월별 실적·변경 협의 기록은 확인이 필요하다.',
        120: "- 문제: ‘확인하겠다’와 실제 전달을 같은 상태로 취급하면 잘못된 완료 판단이 생긴다. 대응: 약속·요청·응답·실행 근거를 분리하였다.\n- 승인 후에도 이전 질문이 계속 남는 문제는 최신 권한과 정확히 연결된 질문만 재질문 대상에서 제외하여 해결했다. 원본 미응답 사건과 무관한 질문은 보존하고 권한 철회 때 재판정한다.\n- 실제 모델 1차 점검에서 업무 승인 대신 우선권을 고르는 메타 행동이 추출되어 의도한 소유자 충돌이 권한 공백으로 분류되었다. 추출 계약을 보완한 2차 호출에서는 실제 approve 행동과 소유자 충돌을 확인하였다. 같은 합성 사례를 재사용한 연결 점검으로, 독립 평가나 정확도 향상률은 아니다.\n- A2A 분석 취소 후 늦은 결과가 적용되는 문제는 생성 식별자 무효화·작업 취소와 늦은 artifact 차단 테스트로 확인하였다.",
        130: '- 프로토콜 연결과 업무의 결정권은 별도 설계 대상이며, 모델의 해석만으로 사람의 동의를 확정할 수 없었다.\n- 기능 실행·인용 일치와 사용자 효과를 각각 검증해야 한다. 실패 기록도 개선 근거로 남겼으며 개인별 소감은 참여자 확인 후 보완한다.',
        139: "- 기대효과: 사람에게 결정 대상·권한 공백·원문 근거를 함께 제시하여 긴 대화에서 확인할 지점을 찾도록 돕는다. 위임 범위가 명확한 결정은 담당 에이전트에게 맡기고 필요한 질문을 구체화한다.\n- 읽기 시간 감소, 개입 정확도 향상, 비용 절감은 아직 사용자 연구로 측정하지 않았다. 정량 절감률·시장 규모·ROI를 제시하지 않는다.",
        147: "- 전 세계 개발자·운영팀·전문가가 자체 환경에 연결·확장하는 활용을 지향한다. 리뷰·배포 승인과 일정 조율 등이 적용 예다. 화면은 영어 고정이며 언어 선택은 없다. 대화 분석은 한국어·영어 입력을 지원하고 원문·인용의 언어를 보존한다. 해외 사용자 확보·다국어 정확도는 아직 검증하지 않았다.\n- 공개 체험: https://culture-fit-demo-production.up.railway.app/workspace . 합성 대화·과거 모델 분석을 재생하며 방문자 쿠키별 SQLite를 격리하고 자기 기록만 초기화한다. 새 모델 호출·Slack 수신은 차단한다. 영문 UI와 설치 ZIP을 배포했고 소스는 main에 MIT로 공개했다.",
        155: '- 사용자 제공 「2026년 한이음 드림업 프로젝트 개요서」 1~2쪽: 초기 문화·역사 고증 및 멀티 에이전트 검수 기획.\n- 사용자 제공 「2026년 한이음 드림업 개발보고서」, 2026.07.12, 1~5·7~8·10·13~15쪽: GitHub RAG·지식 충돌 해결, 당시 자체 진행 보고와 등록 기간.\n- Anthropic (2024.11.25). Introducing the Model Context Protocol. https://www.anthropic.com/news/model-context-protocol\n- Google (2025.04.09). Announcing the Agent2Agent Protocol (A2A). https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/\n- Li, Q. & Xie, Y. (2025.05.06). From Glue-Code to Protocols: A Critical Analysis of A2A and MCP Integration for Scalable Agent Systems. arXiv:2505.03864v1, §3.1·6. https://arxiv.org/pdf/2505.03864v1\n- A2A 명세: https://a2a-protocol.org/latest/specification/\n- MCP 구조: https://modelcontextprotocol.io/docs/learn/architecture\n- W3C RDF 1.1: https://www.w3.org/TR/rdf11-concepts/',
        156: "- Microsoft Agent Framework, Human-in-the-loop: https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop?pivots=programming-language-csharp\n- Palantir, Platform overview (Actions): https://www.palantir.com/docs/foundry/platform-overview/overview\n- Palantir, Autopilot—Integrations: https://www.palantir.com/docs/foundry/autopilot/integrations\n- Slack Socket Mode: https://docs.slack.dev/apis/events-api/using-socket-mode/\n- 직접 근거: tests/, docs/submission/implementation-verification.json(완료 실행 요약), experiments/results/briefing-smoke/(실제 모델 2회), experiments/results/latest/(통제평가), .runtime/live-agent-smoke/20261029T054147Z/(실제 Codex→MCP). 문헌은 설계 근거이며 본 시스템 효과의 실험 증거가 아니다.",
    }
    for i,text in content.items():write_paragraph(paragraphs[i],text)
    paragraphs[76].paragraph_format.keep_together=True

    notes = {
        5: "구현 결과: 대화 관제 웹, 권한 판정 모듈, A2A 분석 어댑터, MCP 도구, Slack 수신기와 공개 체험 웹·검증 자료. 코드·일부 화면의 개발명은 Arbiter이며 제출 프로젝트명은 컬처핏(Culture-Fit)이다. 실제 Slack 계정 연결·메시지 전송은 완료되지 않았다.",
        6: "문제 유형 구분: 지식 충돌은 같은 대상의 상반된 주장, 지식 공백은 필요한 정보 부재, 권한 충돌은 결정할 수 있는 주체·우선권 문제이다. 사람의 선호 선택만으로 외부 사실을 검증할 수는 없다.\n같은 테스트 결과를 공유해도 검토와 최종 승인 위임은 다르다. 추가 검색이나 저장소 읽기·쓰기 권한으로 승인권이 생기지는 않는다. 위임 기록을 함께 저장할 수 있지만, 발급 주체·범위·조건·만료·철회·소유자 합의의 유효성 판정과 적용은 별도다.",
        7: "온톨로지는 Person·Agent·Claim·Evidence·Commitment·HumanInputRequest·DecisionOwner·Artifact와 위임 관계를 명시한 경량 Python/JSON 모델이다. RDF/OWL/SPARQL 표준 준수 또는 범용 논리 추론기를 구현했다고 주장하지 않는다.",
        10: "공통 저장: SQLite의 세션·메시지·결정·권한 기록. event_id로 재전송을 구분한다. 모델 분석 완료, 사람의 결정, 외부 작업 완료는 별개의 사건이다.",
        12: "아래 이미지는 최신 영어 공개 체험의 실제 화면이며 합성 대화와 저장된 분석을 사용한다. 실제 Slack 운영자나 비공개 대화를 재현하지 않는다.",
        13: "여섯 주요 탭: 현황 / 대화 / 결정함 / 지식맵 / 실험 / 연결 설정. 대화는 페이지 탐색을 제공하고 새 발화 도착 시 읽던 위치를 유지한다.",
        15: "별도 센서·제어보드·제작 디바이스를 사용하지 않아 H/W 기능과 실물사진은 해당 없음.",
        16: "실행 컴퓨터와 웹 브라우저는 개발·시연 환경이다. 별도 하드웨어 개발 성과로 기재하지 않는다.",
        17: "권한 판정 예: 같은 scope/action에서 유효 권한 보유자가 한 명이면 담당자로 제시한다. 복수라면 사람이 기록한 일관된 우선권을 적용하며, 서로 다른 소유자는 관련 소유자 전원의 승인 기록을 요구한다. 승인 후 미실행은 실행 근거를 요청하되 권한 자체를 새로 발명하지 않는다.",
        19: "버전 재현은 pyproject.toml·uv.lock을 기준으로 한다. 로컬 Codex CLI 로그인은 실제 브리핑에 필요하며 통제 시뮬레이션은 모델 호출 없이 실행한다.",
        21: '한국어·영어 제품 소개 영상을 각 3분으로 제작했다. 소스 ZIP의 macOS 빈 첫 실행과 새 방문자의 공개 체험을 촬영했다. 데이터·승인은 합성 예제와 운영자 기록이며 외부 작업을 실행하지 않았다. 이전 한국어 UI 시연본은 이력으로 보존하며 한국어 공개 영상 주소는 https://youtu.be/NO08LQL7ekU 이다.',
        23: "그림은 최신 영어 공개 체험의 합성 예제 화면이다. 세 열은 흐름 요약이며, 실제 서비스 화면 별첨에서 16.2cm 폭으로 확대했다. 실제 사용자 연구나 운영 실적으로 사용하지 않는다.",
        25: "외부 등록·발표·출원·공모전 등 증빙된 실적 없음. 본 표의 체크박스는 선택하지 않았다. 코드·로컬 테스트·포스터 초안 제작은 외부 등록 또는 발표 실적과 구분한다.",
        28: '등록 기간은 2026.04.01~2026.10.30(2026.07.12 개발보고서 13쪽의 한이음 사이트 기준 기재)이다. 실제 월별 수행·회의 기록과 구분하고, 아래 검증 수치는 2026-10-29의 현재 구현에 한정한다.',
        29: '최신 전체 검증: 199개 테스트·8개 하위검증 통과(10.32초). 공개 API 29항목·Chrome UI 27항목, 영어 상호 대기 규칙 13항목, 기존 예시 별칭·승인 식별자 보존 33항목을 별도 확인했다. macOS ZIP 실설치에 통과했고 Windows 실실행은 미검증이다. 근거는 docs/submission/implementation-verification.json의 완료 실행 요약과 배포 검증 기록이다.\n브리핑 모델은 같은 합성 사례에서 2회 호출했고 1차 추출 오류·2차 approve·소유자 충돌을 보존했다. 별도 실제 Codex→MCP 2회(도구 4회)는 모의 승인 전 wait_for_human, 후 follow_authority·Review Agent를 반환했다. 수동 scope/action 사례로 추출 정확도·실제 소유자 승인·외부 실행 검증은 아니다.\n별도 24회 통제 시뮬레이션: 고정 상한 2/8·평균14.75턴, 주기적/적응형 각각8/8·평균5턴. 요청7건/6건의 차이는 정상사례1건이며 최신 자연어 권한 탐지 효과의 평가가 아니다.',
        30: "평가 계획: 독립 사람이 라벨링한 결정·권한 사례를 분리하여 정밀도·재현율, 불필요한 개입, 결정 찾는 시간과 작업 완료를 측정한다. 조직별 권한 체계·응답 지연·잘못된 위임도 포함한다.",
        31: "후속 과제: 실제 Slack 수신 검증, 권한 기록의 인증·변경 이력, Scope 표현 정합성, 민감 대화 보관 정책, 사용자 연구, 버전 릴리스, Windows 실설치, 영문 예제·기여 안내 보강과 다국어 검증. 일반 에이전트 전체를 자동 중단하는 기능은 현재 범위가 아니다.",
        33: "해당 없음: 현재 제출 가능한 외부 등록·논문 발표·특허·공모전 성과 증빙이 없다. 증빙된 성과가 생길 경우 확인 가능한 자료만 별첨한다. 로컬 기능 테스트와 원시 실험은 구현 검증 자료로 별도 보관한다.",
    }
    for i,text in notes.items():
        write_cell(cell(tables[i],0,0),text,9)
        # Instruction boxes in the blank template reserve handwriting space.
        # Let filled explanatory notes use their actual height, keeping the table.
        for row in tables[i].rows:
            properties = row._tr.get_or_add_trPr()
            for height in list(properties.findall(qn("w:trHeight"))):
                properties.remove(height)
    figure = ROOT / "assets/authority-architecture.png"
    make_architecture(figure)
    picture(cell(tables[8],0,0),figure,"그림 1. 전체 흐름 요약. 모델은 명시적 요청으로 실행하며 내부 모듈·데이터·경계는 상세 구성도 A~C에서 확대한다.",16.2)

    functionality = [
        ("S/W","대화 수집·관제","Slack 읽기 전용 수신, 텍스트 가져오기, 원문·페이지 탐색"),
        ("S/W","권한 기반 HITL","결정 추출·원문 인용, scope/action 대조, 우선권 또는 사람 질문"),
        ("H/W","별도 제작 없음","소프트웨어 프로젝트로 센서·제어장치 해당 없음"),
        ("H/W","개발용 컴퓨터","로컬 서버·브라우저 실행 환경이며 신규 하드웨어 성과 아님"),
    ]
    for ri,values in enumerate(functionality,1):
        for ci,value in enumerate(values):write_cell(cell(tables[9],ri,ci),value)
    for values in [("S/W","A2A·MCP 연결","분석 작업 요청·조회·취소 및 사건 기록·사람 결정 조회"),("S/W","저장·실험·배포 자료","SQLite, JSON/Markdown 내보내기, 정책 비교 및 재사용 Skill 구성")]:
        row=tables[9].add_row()
        for c,value in zip(row.cells,values):write_cell(c,value)
    shots = [ROOT/"video/captures/product/10-authority-conflict.png",ROOT/"video/captures/product/16-both-owner-approvals.png",ROOT/"video/captures/product/17-review-agent-authorized.png"]
    sw = [("결정 브리핑·권한 충돌","같은 배포 승인에 두 소유자의 권한이 겹친 상태와 필요한 판단을 확인한다."),
          ("공동 승인·우선권 기록","해당 업무의 순서와 소유자 승인을 기록한다. 저장 후 담당자·다음 행동이 갱신되며, 입력은 로컬 운영자 기록이다.")]
    for ri,(name,description) in enumerate(sw,1):
        write_cell(cell(tables[11],ri,0),name)
        write_cell(cell(tables[11],ri,1),description)
        picture(cell(tables[11],ri,2),shots[ri-1],"최신 영어 공개 체험 · 합성 예제" + (" · 저장 전" if ri == 2 else ""),6.1)
    for ri in (1,2):
        for ci,value in enumerate(["해당 없음","별도 제작 H/W 없음","해당 없음"]):write_cell(cell(tables[14],ri,ci),value)
    environments = [
        "macOS 15.7.9 ARM64 (검증 호스트)","Paseo / 로컬 개발 도구; 실제 팀별 IDE는 확인 필요",
        "uv, Git, pytest, FastAPI, Uvicorn, SQLite","Python 3.12 검증(프로젝트 요구 >=3.11), JavaScript, HTML, CSS",
        "a2a-sdk 1.3.0, MCP SDK 1.30.0, Slack SDK; 잠금 버전은 uv.lock",
        "개발용 컴퓨터·웹 브라우저; 별도 제작 장치 없음","해당 없음","공개 HTTPS 체험, 로컬 HTTP·stdio, WebSocket(Slack Socket Mode)",
        "해당 없음","제품 H/W 제작·조립 없음","Git 저장소·소스 해시 기록","실제 팀 의사소통 도구·회의 기록 확인 필요",
        "https://github.com/Ontology0/hanium-arbiter — main 소스 MIT 공개(PR #2 병합 완료). 설치 ZIP: https://culture-fit-demo-production.up.railway.app/download . 버전 릴리스는 후속",
    ]
    for ri,text in enumerate(environments,1):write_cell(cell(tables[18],ri,2),text)
    equipment=[("개발용 컴퓨터","로컬 API·규칙 엔진·브라우저·테스트 실행. 모델·보유 수량 확인 필요"),("추가 기자재 없음","센서·제어보드·재료 구매 내역 없음"),("해당 없음","별도 하드웨어 제작 없음"),("해당 없음","별도 하드웨어 제작 없음")]
    for ri,(name,purpose) in enumerate(equipment,1):write_cell(cell(tables[20],ri,1),name);write_cell(cell(tables[20],ri,2),purpose)
    for ci,path in enumerate(shots):picture(cell(tables[22],0,ci),path,f"그림 {ci+2}. {['권한 충돌','공동 승인 입력(저장 전)','Review Agent 확인(저장 후)'][ci]} · 최신 영어 공개 체험·합성 예제",5.2)
    # No achievements have external evidence: never check a box or invent dates.
    for ri in (1,3,5,7,9,11,13,15):
        seen=set()
        for ci,c in enumerate(tables[24].rows[ri].cells):
            if ci<2 or id(c._tc) in seen:continue
            seen.add(id(c._tc));write_cell(c,"미확인" if ci==2 else "—",8)
    write_cell(cell(tables[24],12,2),"실제 운영 적용·실용화 실적 미확인",8)
    team={1:("박정두","멘토","네이버(주) · Creator Hub 리더"),
          2:("","지도교수","지도교수 참여 여부 확인 필요"),
          3:("이다영","팀장","등록: 컬처 핏 개발 파트 담당"),
          4:("박세령","멘티","등록: LLM 오케스트레이션 담당"),
          5:("손현경","멘티","등록: 온톨로지 설계 및 LLM 지식 주입 담당"),
          6:("","팀원3",""),7:("","팀원4","")}
    for ri,values in team.items():
        for ci,text in enumerate(values,1):write_cell(cell(tables[26],ri,ci),text)
    # Do not fabricate March–November work. Existing month columns remain blank.
    phase=["기획·범위 정리","지식 충돌·권한 문제 분석","결정·위임 구조 설계","관제 화면·탭 설계","권한 규칙·기록 구현","MCP·A2A·Slack 수신","체험 웹·개발 분기 공개","기능·공개 체험 검증","보고서·영상 제작","회의 실적 확인 필요"]
    for ri,text in enumerate(phase,2):write_cell(cell(tables[27],ri,1),text,7.5)
    write_cell(cell(tables[27],12,0),"등록 기간 2026.04.01~10.30(7월 보고서 13쪽). 실제 월별 수행·회의 실적은 미확인하여 수행색을 채우지 않음. 현재 구현 검증일: 2026-10-29.",8)
    # Blank spacer lines are not content. Remove them after the cover/summary
    # while retaining all official headings and required tables.
    for i,p in enumerate(paragraphs):
        if i >= 25 and not p.text.strip():
            if not p._p.findall('.//'+qn('w:drawing')):
                p._p.getparent().remove(p._p)
            continue
        if p.text.startswith(("I.","II.","III.","Ⅳ.","Ⅴ.")):
            p.paragraph_format.keep_with_next=True
            if i>=44:p.paragraph_format.page_break_before=True
        elif p.text.startswith("3. 프로젝트 특"):
            p.paragraph_format.keep_with_next=True
            p.paragraph_format.page_break_before=True
        elif re.match(r"^\d+[.)] ", p.text):
            p.paragraph_format.keep_with_next=True
    for table_ in tables:
        for row in table_.rows:
            row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
    for i in [3,9,11,14,18,20,26,27]:
        tables[i].rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    tables[27].rows[1]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    paragraphs[98].paragraph_format.page_break_before=True
    append_technical_detail(doc, paragraphs[107])
    append_service_screens(doc)
    assert len(doc.tables) == 34, "Official template tables must remain intact"
    doc.core_properties.title=PROJECT+" — 2026 한이음 공식서식 상세 보고서"
    doc.core_properties.author=""
    doc.core_properties.comments="원본 보존. 포털 등록 업무 반영. 팀번호·월별 실제 수행내역·성과 증빙 확인 필요. 최신 서비스 캡처와 한국어·영어 영상 주소 반영."
    output.parent.mkdir(parents=True,exist_ok=True)
    doc.save(output)
    assert sha256(template.read_bytes()).hexdigest()==before
    print(f"Created {output}; original template SHA256 unchanged: {before}")


def _report_word_cleanup_issue(message):
    # Diagnostics must never replace the original conversion exception.
    try:
        print(message, file=sys.stderr)
    except Exception:
        pass


def _close_word_render_documents(render_docx: Path, temporary_pdf: Path):
    """Attempt cleanup only for this export; a zero exit alone is not success.

    Word close previously returned -1708 on this host. This guarded path is
    intentionally fail-closed until an actual export confirms document absence.
    """
    script='''on run argv
set sourcePath to item 1 of argv
set pdfPath to item 2 of argv
set reportNames to {item 3 of argv, item 4 of argv}
if application "Microsoft Word" is not running then return "CLOSED"
tell application "Microsoft Word"
 repeat with reportName in reportNames
  if (name of every document) contains (reportName as text) then
   set reportDoc to document (reportName as text)
   set reportPath to full name of reportDoc as text
   if reportPath is not sourcePath and reportPath is not pdfPath then
    try
     set reportPath to POSIX path of (reportPath as alias)
    end try
   end if
   if reportPath is not sourcePath and reportPath is not pdfPath then return "UNCONFIRMED: document path differs"
   if saved of reportDoc is not true then return "UNCONFIRMED: document save state is not confirmed"
   try
    with timeout of 5 seconds
     close reportDoc saving no
    end timeout
   on error messageText number errorNumber
    return "UNCONFIRMED: close " & errorNumber & " / " & messageText
   end try
  end if
 end repeat
 repeat 10 times
  set openNames to name of every document
  if openNames does not contain (item 3 of argv) and openNames does not contain (item 4 of argv) then return "CLOSED"
  delay 0.2
 end repeat
end tell
return "UNCONFIRMED: temporary document is still open"
end run'''
    try:
        result = subprocess.run(
            ["osascript", "-e", script, str(render_docx), str(temporary_pdf), render_docx.name, temporary_pdf.name],
            capture_output=True, text=True, timeout=20,
        )
        detail = (result.stdout or result.stderr).strip()
        return result.returncode == 0 and detail == "CLOSED", detail
    except Exception as error:
        return False, f"{type(error).__name__}: {error}"


def export_pdf_with_word(docx: Path):
    docx = docx.resolve()
    pdf=docx.with_suffix(".pdf")
    temporary=pdf.with_name("_render-"+uuid.uuid4().hex+".pdf")
    # An already-open Word document can keep an earlier revision in memory.
    # Render an exact, uniquely named copy so the PDF reflects these DOCX bytes.
    render_docx=docx.with_name("_word-"+uuid.uuid4().hex+".docx")
    # Shared by both report builders. A prior uncertain export or concurrent
    # invocation must not accumulate another Word window. Do not auto-clear it.
    journal = ROOT.parent / ".runtime/word-report-export.json"
    journal.parent.mkdir(parents=True, exist_ok=True)
    state = {"source": str(docx), "temporary_docx": str(render_docx),
             "temporary_pdf": str(temporary), "destination_pdf": str(pdf), "phase": "prepared"}
    try:
        with journal.open("x", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2)
    except FileExistsError as error:
        raise RuntimeError(f"Prior Word export needs reconciliation: {journal}. No new document opened.") from error
    # Word sometimes completes an AppleEvent but delays its reply. Send the
    # open/export asynchronously, then verify the requested document and PDF.
    # Never activate Word or close another document.
    script='''on run argv
set sourcePath to item 1 of argv
set reportName to item 2 of argv
set targetPath to item 3 of argv
ignoring application responses
 tell application "Microsoft Word" to open file name sourcePath
end ignoring
repeat 48 times
 tell application "Microsoft Word" to set reportNames to name of every document
 if reportNames contains reportName then exit repeat
 delay 0.25
end repeat
if reportNames does not contain reportName then error "Report did not open"
ignoring application responses
 tell application "Microsoft Word" to save as document reportName file name targetPath file format format PDF
end ignoring
end run'''
    dispatched = False
    closed = False
    published = False
    files_cleaned = False
    try:
        shutil.copyfile(docx, render_docx)
        state["phase"] = "open_or_export_in_flight"
        journal.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        dispatched = True
        subprocess.run(["osascript","-e",script,str(render_docx),render_docx.name,str(temporary)],check=True,timeout=30)
        last_size = None
        stable = 0
        for _ in range(45):
            if temporary.exists():
                data = temporary.read_bytes()
                size = len(data)
                stable = stable + 1 if size == last_size else 0
                last_size = size
                if stable >= 2 and data.startswith(b"%PDF-") and b"%%EOF" in data[-100:]:
                    break
            time.sleep(1)
        else:
            raise RuntimeError("Word did not finish the requested PDF")
        state["phase"] = "pdf_ready_cleanup_pending"
        journal.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        closed, detail = _close_word_render_documents(render_docx, temporary)
        if not closed:
            raise RuntimeError(f"Temporary Word document cleanup unconfirmed: {detail}. State: {journal}")
        # Publish only after the exact temporary document has been closed.
        temporary.replace(pdf)
        published = True
    except BaseException as error:
        state.update(phase="reconciliation_required", error=f"{type(error).__name__}: {error}")
        try:
            journal.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as journal_error:
            _report_word_cleanup_issue(f"Could not update Word export state: {journal_error}")
        raise
    finally:
        # After an asynchronous timeout, an empty document list is insufficient:
        # queued open/export events could still run. Retain state and files.
        if (closed and published) or not dispatched:
            try:
                render_docx.unlink(missing_ok=True)
                temporary.unlink(missing_ok=True)
                journal.unlink(missing_ok=True)
                files_cleaned = True
            except OSError as cleanup_error:
                _report_word_cleanup_issue(f"Word export file cleanup incomplete: {cleanup_error}")
    if files_cleaned:
        print(f"Exported {pdf} using Microsoft Word; temporary document closure confirmed")
    else:
        _report_word_cleanup_issue(f"PDF exported to {pdf}, but file cleanup remains unresolved: {journal}")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"submission/TEAM_NUMBER_PENDING.docx")
    parser.add_argument("--pdf",action="store_true")
    args=parser.parse_args()
    build(args.output.resolve())
    if args.pdf:export_pdf_with_word(args.output.resolve())


if __name__=="__main__":main()
