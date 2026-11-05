"""Build the Korean submission draft from Markdown without changing project deps.

    uv run --with python-docx python docs/build_report.py

The supported Markdown subset is intentionally small: headings, paragraphs,
bullets/numbered lists, tables, links, inline bold/code, fenced code, images,
and explicit <!-- pagebreak --> markers.
"""
from __future__ import annotations

import argparse
import html
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION_START, WD_ORIENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.opc.constants import RELATIONSHIP_TYPE as RT


ROOT = Path(__file__).resolve().parent
FONT = "맑은 고딕"
INLINE = re.compile(r"(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\)|`[^`]+`)")


def font(run, *, size=None, bold=None):
    run.font.name = FONT
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    return run


def hyperlink(paragraph, label, target):
    relationship = paragraph.part.relate_to(target, RT.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), relationship)
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    for name in ("ascii", "hAnsi", "eastAsia"):
        fonts.set(qn(f"w:{name}"), FONT)
    properties.append(fonts)
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "244D70")
    properties.append(color)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.append(underline)
    run.append(properties)
    text = OxmlElement("w:t")
    text.text = label
    run.append(text)
    link.append(run)
    paragraph._p.append(link)


def inline(paragraph, text):
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            font(paragraph.add_run(part[2:-2]), bold=True)
        elif part.startswith("["):
            match = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", part)
            hyperlink(paragraph, match.group(1), match.group(2))
        elif part.startswith("`") and part.endswith("`"):
            run = font(paragraph.add_run(part[1:-1]))
            run.font.color.rgb = RGBColor.from_string("444444")
        else:
            font(paragraph.add_run(part))


def set_style(document, name, *, size, bold=False, space_after=5):
    style = document.styles[name]
    style.font.name = FONT
    style.font.size = Pt(size)
    style.font.bold = bold
    style._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT)
    style.paragraph_format.space_after = Pt(space_after)
    style.paragraph_format.line_spacing = Pt(size + 4.5)
    grid = OxmlElement("w:snapToGrid")
    grid.set(qn("w:val"), "0")
    style._element.get_or_add_pPr().append(grid)
    style.font.color.rgb = RGBColor.from_string("171717")
    return style


def configure(document, label="결과보고서 초안", brand="ARBITER"):
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(1.75), Cm(1.7)
    section.left_margin, section.right_margin = Cm(2.0), Cm(2.0)
    section.header_distance, section.footer_distance = Cm(0.7), Cm(0.7)
    set_style(document, "Normal", size=10.5, space_after=5)
    set_style(document, "Title", size=20, bold=True, space_after=10)
    set_style(document, "Heading 1", size=14, bold=True, space_after=7)
    set_style(document, "Heading 2", size=11, bold=True, space_after=5)
    set_style(document, "Heading 3", size=10.5, bold=True, space_after=4)
    set_style(document, "List Bullet", size=10, space_after=3)
    set_style(document, "List Number", size=10, space_after=3)
    set_style(document, "Caption", size=9, space_after=5)
    for name in ("Heading 1", "Heading 2", "Heading 3"):
        document.styles[name].paragraph_format.space_before = Pt(8)
        document.styles[name].paragraph_format.keep_with_next = True
    header = section.header.paragraphs[0]
    font(header.add_run(brand + "  ·  한이음 " + label), size=8)
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    font(footer.add_run("—  "), size=8)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    font(footer.add_run("  —"), size=8)
    document.core_properties.title = "Arbiter: Slack 에이전트 협업 관제"
    document.core_properties.subject = "한이음 결과보고서 초안 · 실제 구현과 통제 시뮬레이션"
    document.core_properties.author = ""
    document.core_properties.comments = "Generated from docs/final-report.md by docs/build_report.py"


def table(document, lines):
    values = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    rows = [row for row in values if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in row)]
    columns = len(rows[0])
    result = document.add_table(rows=1, cols=columns)
    result.style = "Table Grid"
    result.alignment = WD_TABLE_ALIGNMENT.CENTER
    result.autofit = True
    for index, values in enumerate(rows):
        cells = result.rows[0].cells if index == 0 else result.add_row().cells
        for cell, value in zip(cells, values):
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(2)
            paragraph.paragraph_format.space_before = Pt(2)
            paragraph.paragraph_format.line_spacing = Pt(12.5)
            inline(paragraph, value)
            for run in paragraph.runs:
                font(run, size=9, bold=index == 0)
            if index == 0:
                shade = OxmlElement("w:shd")
                shade.set(qn("w:fill"), "F0F0F0")
                cell._tc.get_or_add_tcPr().append(shade)
        row = result.rows[index]
        row_properties = row._tr.get_or_add_trPr()
        row_properties.append(OxmlElement("w:cantSplit"))
        if index == 0:
            row_properties.append(OxmlElement("w:tblHeader"))
    spacer = document.add_paragraph()
    spacer.paragraph_format.line_spacing = Pt(1)
    spacer.paragraph_format.space_after = Pt(4)


def build(source: Path, output: Path):
    document = Document()
    configure(document, "개발보고서" if source.stem == "development-report" else "결과보고서 초안",
              "CULTURE-FIT" if source.stem == "development-report" else "ARBITER")
    lines = source.read_text(encoding="utf-8").splitlines()
    document.core_properties.comments = f"Generated from docs/{source.name} by docs/build_report.py"
    if lines and lines[0].startswith("# "):
        document.core_properties.title = lines[0][2:]
    index = 0
    explicit_pages = 1
    pending_page_break = False
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line in {"<!-- landscape -->", "<!-- portrait -->"}:
            wide = line == "<!-- landscape -->"
            section = document.add_section(WD_SECTION_START.NEW_PAGE)
            section.orientation = WD_ORIENT.LANDSCAPE if wide else WD_ORIENT.PORTRAIT
            section.page_width, section.page_height = (Cm(29.7), Cm(21)) if wide else (Cm(21), Cm(29.7))
            section.top_margin = section.bottom_margin = Cm(1 if wide else 1.5)
            section.left_margin = section.right_margin = Cm(1.4 if wide else 2)
            explicit_pages += 1
            index += 1
            continue
        if line == "<!-- pagebreak -->":
            pending_page_break = True
            explicit_pages += 1
            index += 1
            continue
        if line.startswith("```"):
            block = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(lines[index])
                index += 1
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(6)
            paragraph.paragraph_format.line_spacing = 1.0
            paragraph.paragraph_format.keep_together = True
            font(paragraph.add_run("\n".join(block)), size=8.5)
            index += 1
            continue
        if line.startswith("|"):
            block = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                block.append(lines[index])
                index += 1
            table(document, block)
            continue
        picture = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", line)
        if picture:
            path = (source.parent / picture.group(2)).resolve()
            if not path.is_file():
                raise FileNotFoundError(f"Report image is missing: {path}")
            wide = document.sections[-1].orientation == WD_ORIENT.LANDSCAPE
            width_cm = 24.0 if wide else (15.0 if picture.group(2).startswith("video/captures/") else 16.2)
            document.add_picture(str(path), width=Cm(width_cm))
            image_paragraph = document.paragraphs[-1]
            image_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            image_paragraph.paragraph_format.space_after = Pt(2)
            image_paragraph.paragraph_format.line_spacing = 1.0
            caption = document.add_paragraph(style="Caption")
            caption.paragraph_format.line_spacing = Pt(12)
            caption.paragraph_format.space_after = Pt(0)
            inline(caption, picture.group(1))
            for run in caption.runs:
                font(run, size=8.5)
            index += 1
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            paragraph = document.add_paragraph(style="Title" if level == 1 else f"Heading {level - 1}")
            if document.sections[-1].orientation == WD_ORIENT.LANDSCAPE:
                paragraph.paragraph_format.space_before = Pt(0)
                paragraph.paragraph_format.space_after = Pt(3)
            if pending_page_break:
                paragraph.paragraph_format.page_break_before = True
                pending_page_break = False
            inline(paragraph, heading.group(2))
            index += 1
            continue
        if line.startswith("> "):
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Cm(0.3)
            paragraph.paragraph_format.keep_together = True
            inline(paragraph, line[2:])
            for run in paragraph.runs:
                font(run, size=9)
            index += 1
            continue
        bullet = re.match(r"^([-*]|\d+\.)\s+(.+)$", line)
        if bullet:
            if bullet.group(1) in {"-", "*"}:
                paragraph = document.add_paragraph(style="List Bullet")
                inline(paragraph, bullet.group(2))
            else:
                # Preserve the source's numbering across separate lists instead of
                # letting Word continue a shared automatic numbering definition.
                paragraph = document.add_paragraph()
                paragraph.paragraph_format.left_indent = Cm(0.45)
                paragraph.paragraph_format.first_line_indent = Cm(-0.45)
                inline(paragraph, bullet.group(1) + " " + bullet.group(2))
            index += 1
            continue
        parts = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not re.match(r"^(#|\||>|```|<!--|!\[|[-*] |\d+\. )", lines[index].strip()):
            parts.append(lines[index].strip())
            index += 1
        paragraph = document.add_paragraph()
        inline(paragraph, " ".join(parts))
    # Word's inherited CJK grid can expand explicit line spacing and create
    # orphaned source notes. Honor the typography in the source styles.
    for p in document.element.body.iter(qn("w:p")):
        properties = p.find(qn("w:pPr"))
        if properties is None:
            properties = OxmlElement("w:pPr")
            p.insert(0, properties)
        grid = properties.find(qn("w:snapToGrid"))
        if grid is None:
            grid = OxmlElement("w:snapToGrid")
            properties.append(grid)
        grid.set(qn("w:val"), "0")
    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(output)
    print(f"Generated {output} ({explicit_pages} explicit page sections; final pagination depends on the word processor)")


def build_pdf(source: Path, output: Path):
    """Print a matching HTML edition when local Chrome and markdown are available."""
    try:
        import markdown
    except ImportError as error:
        raise RuntimeError("PDF generation needs markdown: uv run --with python-docx --with markdown python docs/build_report.py --pdf") from error
    browser = shutil.which("google-chrome") or shutil.which("chromium")
    mac_browser = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not browser and mac_browser.exists():
        browser = str(mac_browser)
    if not browser:
        raise RuntimeError("PDF generation needs a local Chrome or Chromium executable")
    text = source.read_text(encoding="utf-8").replace("<!-- pagebreak -->", '<div class="page-break"></div>')
    body = markdown.markdown(text, extensions=["tables", "fenced_code"])
    body = re.sub(
        r'<p><img alt="([^"]*)" src="([^"]*)" /></p>',
        r'<figure><img alt="\1" src="\2"><figcaption>\1</figcaption></figure>', body,
    )
    stylesheet = """
      @page { size: A4; margin: 17.5mm 20mm 17mm;
        @bottom-center { content: "— " counter(page) " —"; font-size: 8pt; }
      }
      * { box-sizing: border-box; }
      body { margin: 0; color: #171717; font: 10.5pt/1.2 "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; }
      h1 { font-size: 20pt; margin: 0 0 10pt; }
      h2 { font-size: 14pt; margin: 8pt 0 7pt; }
      h3 { font-size: 11pt; margin: 8pt 0 5pt; }
      h1,h2,h3 { break-after: avoid; }
      p { margin: 0 0 5pt; orphans: 2; widows: 2; }
      table { width: 100%; border-collapse: collapse; margin: 0 0 7pt; font-size: 9pt; line-height: 1.08; }
      th,td { border: .6pt solid #b8b8b8; padding: 4pt; vertical-align: middle; }
      th { background: #f0f0f0; text-align: left; }
      tr { break-inside: avoid; }
      thead { display: table-header-group; }
      a { color: #244d70; text-decoration: underline; }
      code { font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; font-size: .94em; }
      pre { white-space: pre-wrap; font-size: 8.5pt; line-height: 1.12; margin: 0 0 7pt; break-inside: avoid; }
      blockquote { margin: 4pt 0 8pt; padding-left: 8pt; font-size: 9pt; border-left: 2pt solid #aaa; }
      ol,ul { margin: 0 0 5pt; padding-left: 17pt; }
      li { margin: 0 0 4pt; }
      img { display: block; max-width: 100%; max-height: 175mm; object-fit: contain; margin: 8pt auto; }
      figure { margin: 0 0 8pt; }
      figcaption { font-size: 9pt; color: #525252; }
      .page-break { break-before: page; }
    """
    with tempfile.TemporaryDirectory(prefix="arbiter-report-") as directory:
        folder = Path(directory)
        document = folder / "report.html"
        document.write_text(
            '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<base href="{html.escape(source.parent.as_uri())}/"><title>{html.escape(source.stem)}</title>'
            f"<style>{stylesheet}</style></head><body>{body}</body></html>", encoding="utf-8",
        )
        result = subprocess.run(
            [browser, "--headless", "--disable-gpu", "--disable-background-networking",
             "--no-pdf-header-footer", f"--user-data-dir={folder / 'profile'}",
             f"--print-to-pdf={output}", document.as_uri()],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode or not output.exists():
            raise RuntimeError(f"Chrome PDF generation failed (exit {result.returncode})")
    print(f"Generated {output} (HTML print edition of the same Markdown)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "final-report.md")
    parser.add_argument("--output", type=Path, default=ROOT / "final-report.docx")
    parser.add_argument("--pdf", action="store_true", help="Also generate an HTML print edition as PDF using local Chrome")
    parser.add_argument("--word-pdf", action="store_true", help="Export the generated Word document itself to PDF with Microsoft Word")
    args = parser.parse_args()
    build(args.source.resolve(), args.output.resolve())
    if args.word_pdf:
        from build_submission import export_pdf_with_word
        export_pdf_with_word(args.output.resolve())
    elif args.pdf:
        build_pdf(args.source.resolve(), args.output.resolve().with_suffix(".pdf"))


if __name__ == "__main__":
    main()
