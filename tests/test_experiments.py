"""Evaluation integrity checks, including failure retention and unknown usage."""

import csv
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "experiments" / "run_comparison.py"
SPEC = importlib.util.spec_from_file_location("run_comparison", SCRIPT_PATH)
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


def test_all_policy_scenario_pairs_have_auditable_results(tmp_path):
    summary = comparison.run_comparison(tmp_path)
    scenarios = comparison.scenario_catalog()
    expected = {(scenario["id"], policy) for scenario in scenarios for policy in comparison.POLICIES}
    assert {(row["scenario_id"], row["policy"]) for row in summary["runs"]} == expected
    assert len(summary["runs"]) == len(expected)
    assert summary["assigned_run_count"] == len(expected)
    assert summary["runs_per_scenario_policy"] == 1
    assert summary["usage"]["input_tokens"] is None
    assert summary["provenance"]["source_sha256"]
    for row in summary["runs"]:
        assert row["error"] is None, row["error"]
        assert row["turns"] <= row["max_turns"]
        assert row["input_tokens"] is None
        assert row["output_tokens"] is None
        session = json.loads((tmp_path / row["session_file"]).read_text(encoding="utf-8"))
        assert session["result"] == row
        assert session["evaluation"]["success"] == row["success"]
        assert session["parameters"] == summary["parameters"]
        assert sum(item["kind"] == "scripted_human_answer" for item in session["trace"]) == row["human_answers"]
        assert sum(item["kind"] == "agent_event" for item in session["trace"]) == row["turns"]
    for policy in comparison.POLICIES:
        metrics = summary["policies"][policy]
        assert metrics["runs"] == len(scenarios)
        assert metrics["successes"] + metrics["failures"] + metrics["unknown_outcomes"] == len(scenarios)
    with (tmp_path / "runs.csv").open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert len(csv_rows) == len(expected)
    assert all(row["input_tokens"] == "" for row in csv_rows)
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "통제 시뮬레이션" in report
    assert "실제 LLM 실험이나 사람 대상 사용자 연구가 아니다" in report


def test_controller_exceptions_stay_in_denominator_and_batch_continues(tmp_path, monkeypatch):
    scenario = comparison.scenario_catalog()[0]
    monkeypatch.setattr(comparison, "scenario_catalog", lambda: [scenario])
    original = comparison.next_demo_event

    def fail_capped(state):
        if state["policy"] == "capped":
            raise RuntimeError("injected provider failure")
        return original(state)

    monkeypatch.setattr(comparison, "next_demo_event", fail_capped)
    summary = comparison.run_comparison(tmp_path)
    assert len(summary["runs"]) == 3
    capped = next(row for row in summary["runs"] if row["policy"] == "capped")
    assert capped["status"] == "error"
    assert capped["success"] is None
    assert "injected provider failure" in capped["error"]
    assert summary["policies"]["capped"]["failures"] == 0
    assert summary["policies"]["capped"]["unknown_outcomes"] == 1
    assert summary["policies"]["capped"]["success_rate"] == 0
    assert all(row["error"] is None for row in summary["runs"] if row["policy"] != "capped")
    session = json.loads((tmp_path / capped["session_file"]).read_text(encoding="utf-8"))
    assert "RuntimeError" in session["error_traceback"]


def test_scripted_answer_policy_requires_an_offered_meaningful_choice():
    state = {"task": {"oracle_choice": "speed"}}
    assert comparison.choose_scripted_answer(state, {"options": [{"id": "continue"}, {"id": "speed"}]}) == "speed"
    assert comparison.choose_scripted_answer(state, {"options": [{"id": "continue"}, {"id": "stop"}]}) == "continue"
    with pytest.raises(ValueError, match="neither"):
        comparison.choose_scripted_answer(state, {"options": [{"id": "stop"}]})


def test_invalid_budget_does_not_write_a_result(tmp_path):
    output = tmp_path / "invalid"
    with pytest.raises(ValueError, match="positive"):
        comparison.run_comparison(output, max_turns=0)
    assert not output.exists()
