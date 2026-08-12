"""매핑표(docs/traceability.md)가 원본(goal.md + v0.3)과 어긋나 있지 않은지 검사."""

from __future__ import annotations

from pathlib import Path

from tools.gen_traceability import GOAL, DESIGN, OUT, build, parse_design, parse_goal

ROOT = Path(__file__).resolve().parent.parent


def _sources():
    goal_items = parse_goal(GOAL.read_text(encoding="utf-8"))
    screens, entities = parse_design(DESIGN.read_text(encoding="utf-8"))
    return goal_items, screens, entities


def test_goal_entities_exist_in_erd():
    goal_items, _, entities = _sources()
    payload, errors = build(goal_items, {"S1": "x"}, entities)
    assert not errors, "goal.md 엔티티 열에 v0.3 ERD 에 없는 이름: " + "; ".join(errors)


def test_every_ur_fr_row_has_entity_cell():
    """UR/FR 행은 엔티티 열이 채워져 있어야 한다. 없으면 '—' 라고 명시적으로 쓴다."""
    goal_items, _, _ = _sources()
    missing = [
        it["id"]
        for it in goal_items
        if not it["id"].startswith("NFR") and it["has_entity_col"] and it["entity_cell"] == ""
    ]
    assert not missing, f"엔티티 열이 빈 요구사항 (— 라도 써야 함): {missing}"


def test_traceability_doc_is_up_to_date():
    goal_items, screens, entities = _sources()
    payload, errors = build(goal_items, screens, entities)
    assert not errors
    assert OUT.exists(), "docs/traceability.md 없음. `python3 tools/gen_traceability.py` 실행 필요"
    assert payload == OUT.read_text(encoding="utf-8"), (
        "docs/traceability.md 가 원본과 어긋남. `python3 tools/gen_traceability.py` 실행 필요"
    )
