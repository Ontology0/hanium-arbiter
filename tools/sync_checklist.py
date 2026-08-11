#!/usr/bin/env python3
"""goal.md(요구사항 정의) 와 checklist.json(상태·이력) 을 대조한다.

방향은 한쪽이다. goal.md 가 "무엇을" 을 갖고, checklist.json 이 "어디까지" 를 갖는다.
따라서 이 도구는 다음만 한다.

  - goal.md 에 새로 생긴 요구사항 -> checklist 에 status=todo 로 추가
  - 문구·우선순위·추적이 바뀐 요구사항 -> checklist 쪽 메타데이터만 갱신
  - goal.md 에서 사라진 요구사항 -> retired=true 로 표시 (삭제하지 않음. 이력이 남아야 한다)

status / tests / history 는 절대 건드리지 않는다. 그건 사람과 작업 도구의 몫이다.

사용법:
    python3 tools/sync_checklist.py            # 대조 후 반영
    python3 tools/sync_checklist.py --check    # 어긋나면 exit 1 (테스트·CI 용)
    python3 tools/sync_checklist.py --quiet    # 변경 없으면 조용히 (훅 용)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOAL = ROOT / "docs" / "goal.md"
CHECKLIST = ROOT / "checklist.json"

REQ_ID = re.compile(r"^(UR|FR|NFR)-\d{2,}$")
CATEGORY = {"UR": "user", "FR": "functional", "NFR": "non_functional"}
VALID_STATUS = {"todo", "in_progress", "blocked", "done"}
VALID_PRIORITY = {"must", "should", "later", "dropped"}

SCHEMA_VERSION = 1


def _cells(line: str) -> list[str]:
    """마크다운 표의 한 행을 셀 목록으로. 앞뒤 파이프는 버린다."""
    if not line.strip().startswith("|"):
        return []
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_goal(text: str) -> list[dict]:
    """goal.md 의 모든 표를 훑어 요구사항 행만 추출한다.

    표마다 열 개수가 달라도(NFR 표엔 '검증 방법' 열이 하나 더 있다) 앞 4개만 본다.
    ID 형식에 맞지 않는 행은 설명용 표로 보고 건너뛴다.
    """
    items: list[dict] = []
    for raw in text.splitlines():
        cells = _cells(raw)
        if len(cells) < 4 or not REQ_ID.match(cells[0]):
            continue
        rid, title, priority, traces = cells[0], cells[1], cells[2], cells[3]
        items.append(
            {
                "id": rid,
                "title": title,
                "category": CATEGORY[rid.split("-")[0]],
                "priority": priority,
                "traces": [t.strip() for t in traces.split(",") if t.strip()],
            }
        )
    return items


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def empty_checklist() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "docs/goal.md",
        "source_digest": "",
        "items": [],
        "decisions": [],
    }


def load_checklist() -> dict:
    if not CHECKLIST.exists():
        return empty_checklist()
    data = json.loads(CHECKLIST.read_text(encoding="utf-8"))
    data.setdefault("decisions", [])
    data.setdefault("items", [])
    return data


def reconcile(goal_items: list[dict], checklist: dict, goal_digest: str) -> tuple[dict, list[str]]:
    """checklist 를 goal 기준으로 맞춘 새 dict 와, 사람이 읽을 변경 요약을 돌려준다."""
    changes: list[str] = []
    existing = {it["id"]: it for it in checklist["items"]}
    goal_ids = {it["id"] for it in goal_items}

    merged: list[dict] = []
    for gi in goal_items:
        prev = existing.get(gi["id"])
        if prev is None:
            merged.append(
                {
                    **gi,
                    "status": "todo",
                    "tests": [],
                    "retired": False,
                    "history": [],
                }
            )
            changes.append(f"+ {gi['id']} 추가 ({gi['title'][:40]})")
            continue

        item = dict(prev)
        for field in ("title", "category", "priority", "traces"):
            if item.get(field) != gi[field]:
                changes.append(f"~ {gi['id']} {field}: {item.get(field)!r} -> {gi[field]!r}")
                item[field] = gi[field]
        if item.get("retired"):
            item["retired"] = False
            changes.append(f"~ {gi['id']} retired 해제 (goal.md 에 다시 등장)")
        item.setdefault("status", "todo")
        item.setdefault("tests", [])
        item.setdefault("history", [])
        merged.append(item)

    # goal.md 에서 사라진 항목은 뒤에 남겨둔다. 지우지 않는다.
    for rid, prev in existing.items():
        if rid in goal_ids:
            continue
        item = dict(prev)
        if not item.get("retired"):
            item["retired"] = True
            changes.append(f"- {rid} retired (goal.md 에서 사라짐)")
        merged.append(item)

    out = dict(checklist)
    out["schema_version"] = SCHEMA_VERSION
    out["source"] = "docs/goal.md"
    out["items"] = merged
    out.setdefault("decisions", [])
    if out.get("source_digest") != goal_digest:
        out["source_digest"] = goal_digest
        if not changes:
            changes.append("~ source_digest 갱신 (요구사항 외 본문 변경)")
    return out, changes


def dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="goal.md <-> checklist.json 대조")
    ap.add_argument("--check", action="store_true", help="어긋나면 쓰지 않고 exit 1")
    ap.add_argument("--quiet", action="store_true", help="변경 없으면 아무것도 출력하지 않음")
    args = ap.parse_args(argv)

    if not GOAL.exists():
        print(f"[sync] {GOAL} 없음", file=sys.stderr)
        return 2

    text = GOAL.read_text(encoding="utf-8")
    goal_items = parse_goal(text)
    if not goal_items:
        print("[sync] goal.md 에서 요구사항을 하나도 못 찾음. 표 형식 확인 필요", file=sys.stderr)
        return 2

    dup = [i for i in {it["id"] for it in goal_items} if [x["id"] for x in goal_items].count(i) > 1]
    if dup:
        print(f"[sync] ID 중복: {sorted(dup)}", file=sys.stderr)
        return 2

    checklist = load_checklist()
    merged, changes = reconcile(goal_items, checklist, digest(text))

    written_before = CHECKLIST.read_text(encoding="utf-8") if CHECKLIST.exists() else ""
    payload = dump(merged)
    drifted = payload != written_before

    if args.check:
        if drifted:
            print("[sync] goal.md 와 checklist.json 이 어긋남. `python3 tools/sync_checklist.py` 실행 필요")
            for c in changes:
                print(f"       {c}")
            return 1
        if not args.quiet:
            print("[sync] 동기화 상태 정상")
        return 0

    if not drifted:
        if not args.quiet:
            print("[sync] 변경 없음")
        return 0

    CHECKLIST.write_text(payload, encoding="utf-8")
    print(f"[sync] checklist.json 갱신 ({len(changes)}건)")
    for c in changes:
        print(f"       {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
