"""goal.md 와 checklist.json 이 서로 어긋나지 않는지 검사한다.

훅은 사람이 안 돌리면 그만이지만 테스트는 CI 가 돌린다.
동기화의 실제 보장은 훅이 아니라 이 파일이다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import sync_checklist as sync  # noqa: E402

VALID_STATUS = {"todo", "in_progress", "blocked", "done"}
VALID_PRIORITY = {"must", "should", "later", "dropped"}
VALID_CATEGORY = {"user", "functional", "non_functional"}


@pytest.fixture(scope="module")
def checklist() -> dict:
    return json.loads((ROOT / "checklist.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def goal_items() -> list[dict]:
    return sync.parse_goal((ROOT / "docs" / "goal.md").read_text(encoding="utf-8"))


# --- 동기화 -------------------------------------------------------------


def test_checklist_is_in_sync_with_goal():
    """어긋나면 `python3 tools/sync_checklist.py` 를 돌려라."""
    assert sync.main(["--check", "--quiet"]) == 0


def test_goal_has_requirements(goal_items):
    assert len(goal_items) > 0


def test_every_goal_item_is_in_checklist(goal_items, checklist):
    listed = {it["id"] for it in checklist["items"]}
    missing = {it["id"] for it in goal_items} - listed
    assert not missing, f"checklist 에 없는 요구사항: {sorted(missing)}"


def test_source_digest_matches(checklist):
    text = (ROOT / "docs" / "goal.md").read_text(encoding="utf-8")
    assert checklist["source_digest"] == sync.digest(text)


# --- 스키마 -------------------------------------------------------------


def test_ids_are_unique(checklist):
    ids = [it["id"] for it in checklist["items"]]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"ID 중복: {sorted(dupes)}"


def test_ids_are_well_formed(checklist):
    for it in checklist["items"]:
        assert sync.REQ_ID.match(it["id"]), f"ID 형식 오류: {it['id']}"


@pytest.mark.parametrize("field,allowed", [
    ("status", VALID_STATUS),
    ("priority", VALID_PRIORITY),
    ("category", VALID_CATEGORY),
])
def test_enum_fields(checklist, field, allowed):
    bad = [(it["id"], it.get(field)) for it in checklist["items"] if it.get(field) not in allowed]
    assert not bad, f"{field} 값 오류: {bad}"


def test_required_fields_present(checklist):
    for it in checklist["items"]:
        for field in ("id", "title", "category", "priority", "traces", "status", "tests", "history"):
            assert field in it, f"{it.get('id')} 에 {field} 없음"


# --- 팀 규칙 (NFR-06) ---------------------------------------------------


def test_done_items_declare_tests(checklist):
    """구현 완료로 표시하려면 대응 테스트를 적어야 한다. 이게 NFR-06 의 실체다."""
    offenders = [
        it["id"] for it in checklist["items"]
        if it["status"] == "done" and not it["tests"]
    ]
    assert not offenders, f"테스트 없이 done 인 요구사항: {offenders}"


def test_declared_tests_actually_exist(checklist):
    """`tests/test_x.py::test_y` 로 적어둔 테스트가 실재하는지 확인한다.

    적어놓기만 하고 안 만든 경우를 잡는다.
    """
    missing: list[str] = []
    for it in checklist["items"]:
        for ref in it["tests"]:
            path, _, func = ref.partition("::")
            f = ROOT / path
            if not f.exists():
                missing.append(f"{it['id']}: 파일 없음 {ref}")
            elif func and not re.search(rf"^\s*def {re.escape(func)}\b", f.read_text(encoding="utf-8"), re.M):
                missing.append(f"{it['id']}: 함수 없음 {ref}")
    assert not missing, "\n".join(missing)


def test_retired_items_are_not_done(checklist):
    bad = [it["id"] for it in checklist["items"] if it.get("retired") and it["status"] == "done"]
    assert not bad, f"retired 인데 done 인 요구사항: {bad}"


def test_must_items_are_not_silently_dropped(checklist):
    """must 인데 goal.md 에서 사라진 게 있으면 알아채야 한다."""
    bad = [it["id"] for it in checklist["items"] if it.get("retired") and it["priority"] == "must"]
    assert not bad, f"must 인데 retired 됨. 의도한 거면 goal.md 에서 priority 를 dropped 로: {bad}"


# --- 결정 이력 -----------------------------------------------------------


def test_decisions_have_rationale(checklist):
    """이유 없는 결정은 기록으로서 값이 없다."""
    bad = [d["id"] for d in checklist["decisions"] if not d.get("why", "").strip()]
    assert not bad, f"why 가 빈 결정: {bad}"


def test_decision_ids_unique(checklist):
    ids = [d["id"] for d in checklist["decisions"]]
    assert len(ids) == len(set(ids))


def test_history_references_real_decisions(checklist):
    known = {d["id"] for d in checklist["decisions"]}
    dangling = [
        (it["id"], h["decision"])
        for it in checklist["items"]
        for h in it["history"]
        if h.get("decision") and h["decision"] not in known
    ]
    assert not dangling, f"존재하지 않는 결정을 참조하는 이력: {dangling}"
