from concurrent.futures import ThreadPoolExecutor
import threading
import time

from fastapi.testclient import TestClient

from arbiter.app import create_app
from arbiter.providers import build_prompt
from arbiter.domain import create_state


def client_for(tmp_path):
    return TestClient(create_app(tmp_path / "test.sqlite3"))


def test_import_decision_is_local_not_completed_and_survives_restart(tmp_path):
    path = tmp_path / "test.sqlite3"
    with TestClient(create_app(path)) as client:
        state = client.post("/api/intake", json={"transcript": "피클A: 주인에게 확인해 볼게요.\n피클B: 저도 확인하고 알려드릴게요.", "source": "pickle"}).json()
        sid = state["id"]
        request = state["requests"][0]
        assert state["coordination"]["delivery_status"] == "unknown"
        assert client.post(f"/api/sessions/{sid}/run").status_code == 409
        decision = {"request_id": request["id"], "choice": "already_delivered", "note": "담당자 A가 사용자에게 물었음을 직접 확인함. 응답 대기."}
        assert client.post(f"/api/sessions/{sid}/decisions", json={**decision, "note": ""}).status_code == 409
        updated = client.post(f"/api/sessions/{sid}/decisions", json=decision).json()
        assert updated["metrics"]["success"] is None
        assert updated["coordination"]["delivery_status"] == "mixed"
        assert updated["requests"][0]["delivery_status"] == "human_reported_delivered"
        assert updated["decisions"][0]["delivery_status"] == "not_sent"
        assert client.post(f"/api/sessions/{sid}/decisions", json=decision).status_code == 409
        event = {"event_id": "external-1", "agent": "피클A", "content": "응답을 기다립니다."}
        first = client.post(f"/api/sessions/{sid}/events", json=event).json()
        second = client.post(f"/api/sessions/{sid}/events", json=event).json()
        assert len(first["messages"]) == len(second["messages"])
        assert len(second["decisions"]) == 1
        assert second["requests"][0]["status"] == "resolved"
        assert client.get(f"/api/sessions/{sid}/export?format=markdown").status_code == 200
    with TestClient(create_app(path)) as client:
        assert client.get(f"/api/sessions/{sid}").json()["decisions"][0]["note"] == decision["note"]


def test_explicit_reciprocal_wait_is_candidate_not_proven_deadlock(tmp_path):
    with client_for(tmp_path) as client:
        state = client.post("/api/intake", json={"transcript": "A: B의 검토가 끝나면 진행하겠습니다.\nB: A의 검토가 끝나면 진행하겠습니다."}).json()
        assert {issue["id"] for issue in state["coordination"]["issues"]} == {"wait-cycle", "decision-owner"}
        assert all(not wait["confirmed"] for wait in state["coordination"]["waits"])
        graph = client.get(f"/api/sessions/{state['id']}/graph").json()
        assert sum(edge["label"] == "waitsFor" for edge in graph["edges"]) == 2


def test_adaptive_demo_pauses_decision_resumes_and_exports(tmp_path):
    with client_for(tmp_path) as client:
        state = client.post("/api/sessions", json={"scenario_id": "priority-choice"}).json()
        sid = state["id"]
        for _ in range(10):
            state = client.post(f"/api/sessions/{sid}/step").json()
            if state["status"] == "waiting":
                break
        assert state["status"] == "waiting"
        assert client.post(f"/api/sessions/{sid}/step").status_code == 409
        pending = next(item for item in state["requests"] if item["status"] == "pending")
        result = client.post(f"/api/sessions/{sid}/decisions", json={"request_id": pending["id"], "choice": "reliable"})
        assert result.status_code == 200
        state = client.post(f"/api/sessions/{sid}/step").json()
        assert state["status"] == "completed", state
        assert state["metrics"]["success"] is True
        assert state["metrics"]["measured_calls"] == 0
        assert client.get(f"/api/sessions/{sid}/export").json()["id"] == sid


def test_cross_origin_execution_is_rejected(tmp_path):
    with client_for(tmp_path) as client:
        response = client.post("/api/sessions", json={"scenario_id": "healthy-progress"}, headers={"Origin": "https://another-site.example"})
        assert response.status_code == 403


def test_mock_human_answer_is_not_leaked_into_live_prompt():
    state = create_state("priority-choice", mode="codex")
    state["task"]["oracle_choice"] = "private-evaluation-answer"
    assert "private-evaluation-answer" not in build_prompt(state)


def test_two_steps_cannot_spend_two_calls_concurrently(tmp_path, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow_event(state):
        started.set()
        assert release.wait(3)
        return {"agent": "a", "content": "작업 중", "claims": [], "artifact": {}, "evidence": [],
                "input_tokens": 1, "output_tokens": 1, "usage_source": "measured"}

    monkeypatch.setattr("arbiter.app.codex_available", lambda: True)
    monkeypatch.setattr("arbiter.app.codex_event", slow_event)
    with client_for(tmp_path) as client:
        state = client.post("/api/sessions", json={"scenario_id": "healthy-progress", "mode": "codex"}).json()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(client.post, f"/api/sessions/{state['id']}/step")
            assert started.wait(3)
            try:
                assert client.post(f"/api/sessions/{state['id']}/step").status_code == 409
            finally:
                release.set()
            assert first.result().json()["turn"] == 1


def test_automatic_runner_pauses_after_verified_handoff(tmp_path, monkeypatch):
    calls = []

    def handed_off(state):
        calls.append(state["turn"])
        return {"agent": "pickle-a", "content": "사람의 응답을 기다립니다.", "claims": [], "evidence": [],
                "coordination": {"human_input_requests": [{"id": "r1", "recipient": "person-a", "topic": "attendance",
                                                          "delivery_receipt_id": "receipt-1"}]}}

    monkeypatch.setattr("arbiter.app.next_demo_event", handed_off)
    with client_for(tmp_path) as client:
        state = client.post("/api/sessions", json={"scenario_id": "social-handoff"}).json()
        state["task"]["delivery_receipts"] = [{"id": "receipt-1", "request_id": "r1", "recipient": "person-a", "topic": "attendance"}]
        client.app.state.store.save(state)
        assert client.post(f"/api/sessions/{state['id']}/run").status_code == 202
        for _ in range(100):
            result = client.get(f"/api/sessions/{state['id']}").json()
            if not result["busy"]:
                break
            time.sleep(0.01)
        assert calls == [0]
        assert result["status"] == "stopped"
        assert result["detector"]["intentional_human_wait"] is True
        assert result["requests"] == []
