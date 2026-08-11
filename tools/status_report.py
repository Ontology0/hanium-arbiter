#!/usr/bin/env python3
"""checklist.json 을 사람이 읽을 진행 현황으로 출력한다.

숫자를 지어내지 않는다. checklist.json 에 적힌 것만 센다.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKLIST = ROOT / "checklist.json"

CATEGORY_LABEL = {"user": "사용자요구사항", "functional": "기능요구사항", "non_functional": "비기능요구사항"}
STATUS_ORDER = ["done", "in_progress", "blocked", "todo"]
STATUS_LABEL = {"done": "완료", "in_progress": "진행중", "blocked": "막힘", "todo": "미착수"}


def bar(done: int, total: int, width: int = 24) -> str:
    if total == 0:
        return " " * width
    filled = round(width * done / total)
    return "█" * filled + "·" * (width - filled)


def main() -> int:
    if not CHECKLIST.exists():
        print("checklist.json 없음. tools/sync_checklist.py 를 먼저 실행")
        return 2

    data = json.loads(CHECKLIST.read_text(encoding="utf-8"))
    live = [i for i in data["items"] if not i.get("retired")]

    print("=" * 56)
    print(" 진행 현황")
    print("=" * 56)

    for cat, label in CATEGORY_LABEL.items():
        rows = [i for i in live if i["category"] == cat]
        if not rows:
            continue
        counts = Counter(i["status"] for i in rows)
        done = counts.get("done", 0)
        detail = "  ".join(
            f"{STATUS_LABEL[s]} {counts.get(s, 0)}" for s in STATUS_ORDER if counts.get(s)
        )
        print(f"\n{label}  {done}/{len(rows)}")
        print(f"  {bar(done, len(rows))}  {detail}")

    must = [i for i in live if i["priority"] == "must"]
    must_done = sum(1 for i in must if i["status"] == "done")
    print(f"\nMVP(must) 전체  {must_done}/{len(must)}")
    print(f"  {bar(must_done, len(must))}")

    blocked = [i for i in live if i["status"] == "blocked"]
    if blocked:
        print(f"\n막힌 항목 {len(blocked)}건")
        for i in blocked:
            print(f"  {i['id']}  {i['title'][:44]}")

    no_tests = [i for i in live if i["status"] == "done" and not i["tests"]]
    if no_tests:
        print(f"\n⚠ 테스트 없이 done 인 항목 {len(no_tests)}건 — pytest 가 실패한다")
        for i in no_tests:
            print(f"  {i['id']}")

    decisions = data.get("decisions", [])
    print(f"\n기록된 사람 결정  {len(decisions)}건")
    for d in decisions[-5:]:
        who = d.get("by", "?")
        affects = ", ".join(d.get("affects", [])) or "GLOBAL"
        print(f"  {d['id']}  [{affects}]  {d['decision'][:36]}  — {who}")

    retired = [i for i in data["items"] if i.get("retired")]
    if retired:
        print(f"\n폐기된 요구사항 {len(retired)}건: {', '.join(i['id'] for i in retired)}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
