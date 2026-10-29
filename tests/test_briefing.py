from copy import deepcopy
import threading
import time

import pytest
from fastapi.testclient import TestClient

from arbiter.app import create_app
from arbiter.briefing import build_brief, brief_view
from arbiter.conversations import create_import
from arbiter.providers import ProviderError


def fixture_output():
    evidence = [{"message_id": "m1", "quote": "배포 승인은 누가 결정하나요?"}]
    return {"overview": "Release approval authority is unresolved.", "agreements": [], "open_questions": [], "next_actions": [],
            "decision_points": [{"text": "Release approval authority needs to be assigned.", "scope": "release", "action": "approve",
                                 "agents": ["A", "B"], "state": "unresolved", "evidence": evidence}],
            "input_tokens": 20, "output_tokens": 10, "usage_source": "measured"}


def grant(agent, owner):
    return {"id": "grant-" + agent, "agent": agent, "owner": owner, "scope": "release", "action": "approve",
            "issuer": "local-human", "conditions": [], "revoked": False}


def test_literal_evidence_and_current_authority_precede_model_opinion(monkeypatch):
    state = create_import("A: 배포 승인은 누가 결정하나요?\nB: 제가 먼저 검토하겠습니다.")

    def recorded_response(prompt, schema):
        assert "Return the requested JSON in concise English." in prompt
        assert "Preserve evidence quotes in the original input language." in prompt
        return fixture_output()

    monkeypatch.setattr("arbiter.briefing.run_codex_json", recorded_response)
    registry = {"grants": [grant("A", "owner-a"), grant("B", "owner-b")], "precedence": []}
    state["brief"] = build_brief(state, registry)
    state["brief_status"] = "ready"
    assert state["brief"]["authority_checks"][0]["status"] == "cross_owner_conflict"
    assert state["brief"]["intervention_points"][0]["required_owners"] == ["owner-a", "owner-b"]
    assert state["brief"]["intervention_points"][0]["evidence"][0]["quote"] == "배포 승인은 누가 결정하나요?"
    registry["precedence"] = [{"scope": "release", "action": "approve", "agents": ["B", "A"],
                               "approved_by": ["owner-a", "owner-b"], "issuer": "local-human"}]
    viewed = brief_view(state, registry)
    assert viewed["stale"] is True
    assert viewed["brief"]["authority_checks"][0]["decision_owner"] == "B"
    assert viewed["brief"]["intervention_points"] == []
    assert state["brief"]["authority_checks"][0]["status"] == "cross_owner_conflict"


@pytest.mark.parametrize("citation", [{"message_id": "invented", "quote": "배포"}, {"message_id": "m1", "quote": "승인 완료"}])
def test_unsupported_model_citations_are_rejected(monkeypatch, citation):
    output = fixture_output()
    output["decision_points"][0]["evidence"] = [citation]
    monkeypatch.setattr("arbiter.briefing.run_codex_json", lambda *args: output)
    with pytest.raises(ProviderError, match="citation"):
        build_brief(create_import("A: 배포 승인은 누가 결정하나요?"))


def test_already_authorized_task_gets_execution_guidance_not_reapproval(monkeypatch):
    output = fixture_output()
    output["decision_points"][0]["state"] = "authorized_unexecuted"
    monkeypatch.setattr("arbiter.briefing.run_codex_json", lambda *args: output)
    result = build_brief(create_import("A: 배포 승인은 누가 결정하나요?"), {"grants": [grant("B", "owner-b")], "precedence": []})
    assert result["intervention_points"] == []
    assert "Do not request approval for the same scope again." in result["next_actions"][0]["text"]


def test_cancel_discards_late_result_and_concurrent_events_survive(tmp_path, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow_brief(state, registry):
        started.set()
        assert release.wait(3)
        return {"overview": "late"}

    monkeypatch.setattr("arbiter.app.build_brief", slow_brief)
    monkeypatch.setattr("arbiter.app.codex_available", lambda: True)
    with TestClient(create_app(tmp_path / "db.sqlite3")) as client:
        state = client.post("/api/intake", json={"transcript": "A: 새 작업을 시작합니다."}).json()
        base = f"/api/sessions/{state['id']}"
        assert client.post(base + "/brief").status_code == 202
        assert started.wait(3)
        try:
            assert client.post(base + "/brief").status_code == 409
            client.post(base + "/events", json={"event_id": "later", "agent": "B", "content": "검토합니다."})
            assert client.post(base + "/brief/cancel").json()["cancelled"] is True
        finally:
            release.set()
        client.app.state.workers.shutdown(wait=True)
        assert client.get(base + "/brief").json()["available"] is False
        assert len(client.get(base).json()["messages"]) == 2
