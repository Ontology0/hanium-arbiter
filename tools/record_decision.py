#!/usr/bin/env python3
"""사람이 내린 결정을 checklist.json 에 남긴다.

왜 '사람의 결정'만 남기는가
---------------------------
AI 가 코딩한 내역은 git log 에 이미 다 있다. 다시 적으면 중복이고, 양이 많아서 아무도 안 읽는다.
반면 **왜 그 방향으로 갔는지** 는 어디에도 안 남는다. 그게 사라지면 3개월 뒤에 같은 논쟁을 다시 한다.
그래서 이 도구는 사람이 갈림길에서 고른 것만 기록한다.

이 프로젝트 자체가 "근거 없는 주장은 CLAIMED" 라고 말하는 시스템이다.
우리 저장소의 결정도 같은 기준을 지킨다. --why 없이는 기록되지 않는다.

상태 변경은 반드시 결정과 함께 일어난다. 이유 없이 status 를 바꾸는 경로는 두지 않았다.

사용 예:
    python3 tools/record_decision.py \\
        --by 세령 \\
        --affects FR-11,FR-12 \\
        --question "근거 재현 실행을 어디서 할까" \\
        --decision "Docker 로컬 샌드박스" \\
        --why "외부 서비스는 비용·보안 승인이 필요해 11주 안에 못 끝냄" \\
        --rejected "외부 샌드박스 서비스" \\
        --set-status FR-11=in_progress
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKLIST = ROOT / "checklist.json"

VALID_STATUS = {"todo", "in_progress", "blocked", "done"}
GLOBAL = "GLOBAL"
REQ_ID = re.compile(r"^(UR|FR|NFR)-\d{2,}$")


def next_decision_id(decisions: list[dict]) -> str:
    used = []
    for d in decisions:
        m = re.match(r"^D-(\d+)$", d.get("id", ""))
        if m:
            used.append(int(m.group(1)))
    return f"D-{max(used, default=0) + 1:04d}"


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def parse_status_pairs(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--set-status 형식 오류: {pair!r} (예: FR-11=done)")
        rid, status = (p.strip() for p in pair.split("=", 1))
        if status not in VALID_STATUS:
            raise SystemExit(f"알 수 없는 status: {status!r} (가능: {sorted(VALID_STATUS)})")
        out[rid] = status
    return out


def record(data: dict, *, by: str, question: str, decision: str, why: str,
           affects: list[str], rejected: list[str], status_changes: dict[str, str],
           at: str) -> tuple[dict, str]:
    """결정을 반영한 새 checklist dict 와 결정 ID 를 돌려준다."""
    items = {it["id"]: it for it in data["items"]}

    targets = affects or [GLOBAL]
    for rid in targets:
        if rid != GLOBAL and rid not in items:
            raise SystemExit(f"checklist 에 없는 요구사항: {rid} (goal.md 에 먼저 추가하고 sync 실행)")
    for rid in status_changes:
        if rid not in items:
            raise SystemExit(f"checklist 에 없는 요구사항: {rid}")
        if items[rid].get("retired"):
            raise SystemExit(f"{rid} 은 retired 상태. goal.md 에 되살린 뒤 다시 시도")

    did = next_decision_id(data["decisions"])
    entry = {
        "id": did,
        "at": at,
        "by": by,
        "affects": targets,
        "question": question,
        "decision": decision,
        "why": why,
        "rejected": rejected,
        "status_changes": [{"id": k, "to": v} for k, v in sorted(status_changes.items())],
    }
    data["decisions"].append(entry)

    for rid in targets:
        if rid == GLOBAL:
            continue
        items[rid]["history"].append({"at": at, "decision": did, "summary": decision})

    for rid, status in status_changes.items():
        item = items[rid]
        before = item.get("status", "todo")
        item["status"] = status
        if rid not in targets:
            item["history"].append({"at": at, "decision": did, "summary": decision})
        item["history"].append(
            {"at": at, "decision": did, "summary": f"status {before} -> {status}"}
        )

    return data, did


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="사람의 결정을 checklist.json 에 기록")
    ap.add_argument("--by", required=True, help="결정한 사람 이름. AI 이름을 넣지 말 것")
    ap.add_argument("--question", required=True, help="무엇을 두고 갈렸는가")
    ap.add_argument("--decision", required=True, help="무엇으로 정했는가")
    ap.add_argument("--why", required=True, help="왜. 이게 없으면 기록의 의미가 없다")
    ap.add_argument("--affects", help="영향받는 요구사항 ID 쉼표 구분. 생략 시 GLOBAL")
    ap.add_argument("--rejected", help="선택하지 않은 대안 쉼표 구분")
    ap.add_argument("--set-status", action="append", default=[], metavar="ID=STATUS",
                    help="상태 변경. 반복 지정 가능")
    ap.add_argument("--at", help="ISO 시각 (테스트용, 기본값은 현재 UTC)")
    args = ap.parse_args(argv)

    if not CHECKLIST.exists():
        print("[decision] checklist.json 없음. 먼저 tools/sync_checklist.py 실행", file=sys.stderr)
        return 2

    data = json.loads(CHECKLIST.read_text(encoding="utf-8"))
    data.setdefault("decisions", [])

    affects = split_csv(args.affects)
    bad = [a for a in affects if a != GLOBAL and not REQ_ID.match(a)]
    if bad:
        print(f"[decision] ID 형식 오류: {bad}", file=sys.stderr)
        return 2

    at = args.at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    data, did = record(
        data,
        by=args.by,
        question=args.question,
        decision=args.decision,
        why=args.why,
        affects=affects,
        rejected=split_csv(args.rejected),
        status_changes=parse_status_pairs(args.set_status),
        at=at,
    )

    CHECKLIST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[decision] {did} 기록됨 — {args.decision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
