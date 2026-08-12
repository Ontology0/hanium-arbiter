#!/usr/bin/env python3
"""요구사항(goal.md) ↔ 화면(v0.3 S1~S11) ↔ ERD 엔티티 매핑표를 생성한다.

원본은 두 개다. 이 도구는 어느 쪽도 고치지 않는다.

  - docs/goal.md          요구사항·추적(S번호)·엔티티 열
  - docs/design/v0.3.md   화면 목록(S)·ERD 엔티티 목록

출력은 docs/traceability.md 하나다. 손으로 고치지 마라 — 다시 생성하면 덮인다.
goal.md 의 엔티티 열에 v0.3 ERD 에 없는 이름이 있으면 생성하지 않고 실패한다.

사용법:
    python3 tools/gen_traceability.py            # 생성
    python3 tools/gen_traceability.py --check    # 어긋나면 exit 1 (테스트·CI 용)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOAL = ROOT / "docs" / "goal.md"
DESIGN = ROOT / "docs" / "design" / "v0.3.md"
OUT = ROOT / "docs" / "traceability.md"

REQ_ID = re.compile(r"^(UR|FR|NFR)-\d{2,}$")
SCREEN = re.compile(r"^S\d{1,2}$")


def _cells(line: str) -> list[str]:
    if not line.strip().startswith("|"):
        return []
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_goal(text: str) -> list[dict]:
    """goal.md 표에서 요구사항 행을 추출한다. 엔티티 열은 헤더로 위치를 찾는다."""
    items: list[dict] = []
    entity_col: int | None = None
    for raw in text.splitlines():
        cells = _cells(raw)
        if not cells:
            entity_col = None
            continue
        if cells[0] == "ID":  # 헤더 행 — 엔티티 열 위치 기억
            entity_col = cells.index("엔티티") if "엔티티" in cells else None
            continue
        if len(cells) < 4 or not REQ_ID.match(cells[0]):
            continue
        raw_entities = cells[entity_col] if entity_col is not None and entity_col < len(cells) else ""
        entities = [] if raw_entities in ("", "—", "-") else [
            e.strip() for e in raw_entities.split(",") if e.strip()
        ]
        items.append(
            {
                "id": cells[0],
                "title": cells[1],
                "priority": cells[2],
                "screens": [t.strip() for t in cells[3].split(",") if SCREEN.match(t.strip())],
                "entities": entities,
                "has_entity_col": entity_col is not None,
                "entity_cell": raw_entities,
            }
        )
    return items


def parse_design(text: str) -> tuple[dict[str, str], list[str]]:
    """v0.3 에서 (화면번호 -> 이름) 과 ERD 엔티티 이름 목록을 뽑는다."""
    screens: dict[str, str] = {}
    entities: list[str] = []
    for raw in text.splitlines():
        cells = _cells(raw)
        if not cells:
            continue
        # 화면 목록: | S7 충돌 상세 | ... |
        m = re.match(r"^(S\d{1,2})\s+(.+)$", cells[0])
        if m:
            screens[m.group(1)] = m.group(2)
        # ERD 표: | `user` | 사람 ... |
        m = re.match(r"^`([a-z_]+)`$", cells[0])
        if m:
            entities.append(m.group(1))
    return screens, entities


def build(goal_items: list[dict], screens: dict[str, str], entities: list[str]) -> tuple[str, list[str]]:
    errors: list[str] = []
    known = set(entities)
    for it in goal_items:
        for e in it["entities"]:
            if e not in known:
                errors.append(f"{it['id']}: v0.3 ERD 에 없는 엔티티 {e!r}")
    if errors:
        return "", errors

    urfr = [it for it in goal_items if not it["id"].startswith("NFR")]

    lines: list[str] = []
    a = lines.append
    a("# 추적 매핑표 — 요구사항 ↔ 화면 ↔ ERD")
    a("")
    a("> 이 파일은 `tools/gen_traceability.py` 가 생성한다. **손으로 고치지 마라.**")
    a("> 원본: `docs/goal.md` (요구사항·엔티티 열) + `docs/design/v0.3.md` (화면·ERD).")
    a("> 고치려면 원본을 고치고 다시 생성하라.")
    a("")

    a("## 1. 요구사항별 매핑")
    a("")
    a("| ID | 요구사항 | 우선순위 | 화면 | 엔티티 |")
    a("|---|---|---|---|---|")
    for it in urfr:
        scr = ", ".join(f"{s} {screens.get(s, '?')}" for s in it["screens"]) or "— (백엔드)"
        ent = ", ".join(f"`{e}`" for e in it["entities"]) or "**없음**"
        a(f"| {it['id']} | {it['title']} | {it['priority']} | {scr} | {ent} |")
    a("")

    a("## 2. 화면별 요구사항 (역방향)")
    a("")
    a("| 화면 | 요구사항 |")
    a("|---|---|")
    for sid, name in screens.items():
        ids = [it["id"] for it in goal_items if sid in it["screens"]]
        a(f"| {sid} {name} | {', '.join(ids) if ids else '**없음**'} |")
    a("")

    a("## 3. 엔티티별 요구사항 (역방향)")
    a("")
    a("| 엔티티 | 요구사항 |")
    a("|---|---|")
    for e in entities:
        ids = [it["id"] for it in urfr if e in it["entities"]]
        a(f"| `{e}` | {', '.join(ids) if ids else '**없음**'} |")
    a("")

    a("## 4. 공백")
    a("")
    no_entity = [it["id"] for it in urfr if not it["entities"]]
    orphan = [e for e in entities if not any(e in it["entities"] for it in urfr)]
    orphan_screens = [s for s in screens if not any(s in it["screens"] for it in goal_items)]
    if no_entity:
        a(f"- 대응 엔티티 없는 요구사항: {', '.join(no_entity)}")
    if orphan:
        a(f"- 어떤 요구사항도 참조하지 않는 엔티티: {', '.join(f'`{e}`' for e in orphan)}")
    if orphan_screens:
        a(f"- 어떤 요구사항도 참조하지 않는 화면: {', '.join(orphan_screens)}")
    if not no_entity and not orphan and not orphan_screens:
        a("- 없음")
    a("")
    return "\n".join(lines) + "\n", []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="요구사항↔화면↔ERD 매핑표 생성")
    ap.add_argument("--check", action="store_true", help="파일과 어긋나면 exit 1")
    args = ap.parse_args(argv)

    goal_items = parse_goal(GOAL.read_text(encoding="utf-8"))
    screens, entities = parse_design(DESIGN.read_text(encoding="utf-8"))
    if not goal_items or not screens or not entities:
        print("[trace] goal.md 또는 v0.3.md 파싱 실패", file=sys.stderr)
        return 2

    payload, errors = build(goal_items, screens, entities)
    if errors:
        for e in errors:
            print(f"[trace] {e}", file=sys.stderr)
        return 2

    current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    if args.check:
        if payload != current:
            print("[trace] traceability.md 가 원본과 어긋남. `python3 tools/gen_traceability.py` 실행 필요")
            return 1
        print("[trace] 매핑표 최신 상태")
        return 0

    if payload == current:
        print("[trace] 변경 없음")
        return 0
    OUT.write_text(payload, encoding="utf-8")
    print(f"[trace] {OUT.relative_to(ROOT)} 갱신")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
