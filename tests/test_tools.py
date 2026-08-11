"""동기화·기록 도구 자체의 동작 검증.

실제 checklist.json 을 건드리지 않도록 순수 함수(reconcile / record)만 호출한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import record_decision as rec  # noqa: E402
from tools import sync_checklist as sync  # noqa: E402

AT = "2026-08-11T15:00:00+00:00"


def make_checklist(*items: dict) -> dict:
    base = sync.empty_checklist()
    base["items"] = [
        {
            "id": i["id"],
            "title": i.get("title", "t"),
            "category": "functional",
            "priority": i.get("priority", "must"),
            "traces": [],
            "status": i.get("status", "todo"),
            "tests": i.get("tests", []),
            "retired": i.get("retired", False),
            "history": [],
        }
        for i in items
    ]
    return base


# --- parse_goal ---------------------------------------------------------


def test_parse_goal_extracts_requirement_rows():
    md = """
| ID | 요구사항 | 우선순위 | 추적 |
|---|---|---|---|
| FR-01 | 무언가를 한다 | must | R5, F5 |
| NFR-01 | 성질을 지킨다 | should | N1 | 테스트로 검증 |
"""
    items = sync.parse_goal(md)
    assert [i["id"] for i in items] == ["FR-01", "NFR-01"]
    assert items[0]["traces"] == ["R5", "F5"]
    assert items[0]["category"] == "functional"
    assert items[1]["category"] == "non_functional"


def test_parse_goal_ignores_non_requirement_tables():
    md = """
| 열 | 뜻 |
|---|---|
| ID | 식별자 |
| 우선순위 | must / should |
"""
    assert sync.parse_goal(md) == []


def test_parse_goal_tolerates_extra_columns():
    """NFR 표에는 '검증 방법' 열이 하나 더 있다. 앞 4개만 읽어야 한다."""
    md = "| NFR-09 | 성질 | must | N9 | 이건 검증방법 열 | 이건 여분 |"
    assert sync.parse_goal(md)[0]["priority"] == "must"


# --- reconcile ----------------------------------------------------------


def test_reconcile_adds_new_requirement():
    goal = [{"id": "FR-01", "title": "새 요구", "category": "functional",
             "priority": "must", "traces": ["R1"]}]
    merged, changes = sync.reconcile(goal, sync.empty_checklist(), "sha256:x")
    assert merged["items"][0]["status"] == "todo"
    assert any("추가" in c for c in changes)


def test_reconcile_preserves_status_and_history():
    """문구가 바뀌어도 진행 상태와 이력은 살아남아야 한다."""
    before = make_checklist({"id": "FR-01", "title": "옛 문구", "status": "in_progress",
                             "tests": ["tests/test_x.py::test_y"]})
    before["items"][0]["history"] = [{"at": AT, "decision": "D-0001", "summary": "시작"}]

    goal = [{"id": "FR-01", "title": "새 문구", "category": "functional",
             "priority": "must", "traces": []}]
    merged, _ = sync.reconcile(goal, before, "sha256:x")

    item = merged["items"][0]
    assert item["title"] == "새 문구"
    assert item["status"] == "in_progress"
    assert item["tests"] == ["tests/test_x.py::test_y"]
    assert len(item["history"]) == 1


def test_reconcile_retires_instead_of_deleting():
    before = make_checklist({"id": "FR-99", "title": "사라질 요구", "status": "done"})
    merged, changes = sync.reconcile([], before, "sha256:x")
    assert len(merged["items"]) == 1, "삭제하면 이력이 사라진다"
    assert merged["items"][0]["retired"] is True
    assert any("retired" in c for c in changes)


def test_reconcile_unretires_when_requirement_returns():
    before = make_checklist({"id": "FR-01", "title": "돌아온 요구", "retired": True})
    goal = [{"id": "FR-01", "title": "돌아온 요구", "category": "functional",
             "priority": "must", "traces": []}]
    merged, _ = sync.reconcile(goal, before, "sha256:x")
    assert merged["items"][0]["retired"] is False


def test_reconcile_is_idempotent():
    goal = [{"id": "FR-01", "title": "요구", "category": "functional",
             "priority": "must", "traces": []}]
    once, _ = sync.reconcile(goal, sync.empty_checklist(), "sha256:x")
    twice, changes = sync.reconcile(goal, once, "sha256:x")
    assert once == twice
    assert changes == []


# --- record_decision ----------------------------------------------------


def _record(data, **kw):
    args = dict(by="세령", question="q", decision="d", why="w",
                affects=[], rejected=[], status_changes={}, at=AT)
    args.update(kw)
    return rec.record(data, **args)


def test_record_assigns_sequential_ids():
    data = make_checklist({"id": "FR-01"})
    data, first = _record(data)
    data, second = _record(data)
    assert (first, second) == ("D-0001", "D-0002")


def test_record_attaches_history_to_affected_items():
    data = make_checklist({"id": "FR-01"}, {"id": "FR-02"})
    data, did = _record(data, affects=["FR-01"], decision="Docker 로컬")
    items = {i["id"]: i for i in data["items"]}
    assert items["FR-01"]["history"][0]["decision"] == did
    assert items["FR-02"]["history"] == []


def test_record_without_affects_is_global():
    data = make_checklist({"id": "FR-01"})
    data, _ = _record(data)
    assert data["decisions"][0]["affects"] == ["GLOBAL"]
    assert data["items"][0]["history"] == []


def test_status_change_is_logged_with_before_and_after():
    data = make_checklist({"id": "FR-01", "status": "todo"})
    data, _ = _record(data, affects=["FR-01"], status_changes={"FR-01": "done"})
    item = data["items"][0]
    assert item["status"] == "done"
    assert any("todo -> done" in h["summary"] for h in item["history"])


def test_status_change_on_unaffected_item_still_gets_history():
    data = make_checklist({"id": "FR-01"})
    data, did = _record(data, status_changes={"FR-01": "blocked"})
    assert data["items"][0]["history"][0]["decision"] == did


def test_record_rejects_unknown_requirement():
    data = make_checklist({"id": "FR-01"})
    with pytest.raises(SystemExit):
        _record(data, affects=["FR-77"])


def test_record_rejects_status_change_on_retired_item():
    data = make_checklist({"id": "FR-01", "retired": True})
    with pytest.raises(SystemExit):
        _record(data, status_changes={"FR-01": "done"})


def test_parse_status_pairs_rejects_bad_status():
    with pytest.raises(SystemExit):
        rec.parse_status_pairs(["FR-01=완료"])


def test_parse_status_pairs_rejects_missing_equals():
    with pytest.raises(SystemExit):
        rec.parse_status_pairs(["FR-01"])
