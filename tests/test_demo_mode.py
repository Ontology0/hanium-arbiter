"""Public demo boundaries, resource caps, and local-mode compatibility.

All databases are temporary. CLI/Slack entry points are spies or deterministic
fixtures; these tests never invoke an external model or Slack connection.
"""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from arbiter.app import create_app
from arbiter.domain import create_state


ROOT = Path(__file__).resolve().parents[1]


def transcript(count):
    return "\n".join(f"A: 항목 {index}" for index in range(count))


def new_record(client, index):
    if index % 2:
        return client.post("/api/intake", json={"title": f"대화 {index}", "transcript": f"A: 항목 {index}"})
    return client.post("/api/sessions", json={"scenario_id": "healthy-progress", "mode": "demo"})


def test_public_config_and_routes_never_probe_or_invoke_local_integrations(tmp_path, monkeypatch):
    available = Mock(side_effect=AssertionError("public mode must not probe the local Codex CLI"))
    model = Mock(side_effect=AssertionError("public mode must not invoke Codex"))
    briefing = Mock(side_effect=AssertionError("public mode must not invoke the briefing model"))
    slack = Mock(side_effect=AssertionError("public mode must not ingest Slack"))
    channels = Mock(side_effect=AssertionError("public integration config must not read local Slack setup"))
    for name, replacement in (("codex_available", available), ("codex_event", model), ("build_brief", briefing),
                              ("ingest_slack", slack), ("allowed_channels", channels)):
        monkeypatch.setattr("arbiter.app." + name, replacement)
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-not-a-real-token")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-not-a-real-token")
    with TestClient(create_app(tmp_path / "demo.sqlite3", demo_mode=True)) as client:
        assert client.get("/api/health").status_code == 200
        configuration = client.get("/api/config").json()
        assert configuration["deployment"]["mode"] == "visitor_demo"
        assert configuration["deployment"]["isolated"]
        assert not configuration["deployment"]["live_model_available"]
        assert not next(item for item in configuration["providers"] if item["id"] == "codex")["available"]
        integration = client.get("/api/integration").json()
        assert not integration["available"] and integration["mcp"]["config"] is None
        assert not integration["slack"]["configured"]
        assert integration["slack"]["allowed_channels"] == []
        assert "xapp-test" not in json.dumps(integration)
        assert str(ROOT) not in json.dumps(integration)
        blocked = client.post("/api/sessions", json={"scenario_id": "healthy-progress", "mode": "codex"})
        assert blocked.status_code == 403
        demo = client.post("/api/sessions", json={"scenario_id": "healthy-progress"})
        assert demo.status_code == 201
        sid = demo.json()["id"]
        assert client.post(f"/api/sessions/{sid}/brief").status_code == 403
        assert client.post("/api/slack/events", json={"event_id": "external-event"}).status_code == 403
        step = client.post(f"/api/sessions/{sid}/step")
        assert step.status_code == 200 and step.json()["turn"] == 1
    for spy in (available, model, briefing, slack, channels):
        spy.assert_not_called()


@pytest.mark.parametrize("route", ["step", "run"])
def test_public_mode_rejects_preexisting_live_session_before_any_provider_call(tmp_path, monkeypatch, route):
    model = Mock(return_value={"agent": "A", "content": "must not execute", "claims": [], "evidence": []})
    monkeypatch.setattr("arbiter.app.codex_event", model)
    application = create_app(tmp_path / "persisted-live.sqlite3", demo_mode=True)
    saved = create_state("healthy-progress", mode="codex")
    saved.update(id="preexisting-live", busy=False, stop_requested=False)
    application.state.store.save(saved)
    with TestClient(application) as client:
        # A database restored with a live session must not bypass the public
        # creation restriction by using its already-known session ID.
        submitted = Mock()
        monkeypatch.setattr(application.state.workers, "submit", submitted)
        response = client.post(f"/api/sessions/preexisting-live/{route}")
        assert response.status_code == 403
        assert application.state.store.get("preexisting-live")["turn"] == 0
        assert not application.state.store.get("preexisting-live")["busy"]
        model.assert_not_called()
        submitted.assert_not_called()


def test_local_mode_retains_cli_briefing_and_slack_routes(tmp_path, monkeypatch):
    available = Mock(return_value=True)
    model = Mock(return_value={"agent": "A", "content": "로컬 테스트 발화", "claims": [], "evidence": [],
                               "input_tokens": None, "output_tokens": None, "usage_source": "unavailable"})
    slack = Mock(return_value={"accepted": True, "fixture": True})
    monkeypatch.setattr("arbiter.app.codex_available", available)
    monkeypatch.setattr("arbiter.app.codex_event", model)
    monkeypatch.setattr("arbiter.app.ingest_slack", slack)
    application = create_app(tmp_path / "local.sqlite3")
    with TestClient(application) as client:
        config = client.get("/api/config").json()
        assert config["deployment"]["mode"] == "local"
        assert config["deployment"]["live_model_available"]
        assert "mcpServers" in client.get("/api/integration").json()["mcp"]["config"]
        created = client.post("/api/sessions", json={"scenario_id": "healthy-progress", "mode": "codex"})
        assert created.status_code == 201
        sid = created.json()["id"]
        assert client.post(f"/api/sessions/{sid}/step").status_code == 200
        model.assert_called_once()
        submitted = Mock()
        monkeypatch.setattr(application.state.workers, "submit", submitted)
        assert client.post(f"/api/sessions/{sid}/brief").status_code == 202
        submitted.assert_called_once()
        event = {"event_id": "local-fixture"}
        assert client.post("/api/slack/events", json=event).json() == {"accepted": True, "fixture": True}
        assert slack.call_args.args[1] == event


@pytest.mark.parametrize("demo_mode", [True, False])
def test_session_limit_is_shared_by_intake_and_simulation_but_not_applied_locally(tmp_path, demo_mode):
    with TestClient(create_app(tmp_path / "sessions.sqlite3", demo_mode=demo_mode)) as client:
        for index in range(12):
            response = new_record(client, index)
            assert response.status_code == 201, response.text
        expected = 429 if demo_mode else 201
        assert new_record(client, 12).status_code == expected
        assert new_record(client, 13).status_code == expected
        assert len(client.get("/api/sessions").json()) == (12 if demo_mode else 14)


def test_simultaneous_creations_cannot_exceed_public_session_limit(tmp_path):
    with TestClient(create_app(tmp_path / "concurrent.sqlite3", demo_mode=True)) as client:
        for index in range(11):
            assert new_record(client, index).status_code == 201
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda index: new_record(client, index), [12, 13]))
        assert sorted(response.status_code for response in responses) == [201, 429]
        assert len(client.get("/api/sessions").json()) == 12


@pytest.mark.parametrize("demo_mode", [True, False])
def test_grant_record_limit_and_revocation_do_not_drop_history(tmp_path, demo_mode):
    with TestClient(create_app(tmp_path / "grants.sqlite3", demo_mode=demo_mode)) as client:
        grant_ids = []
        for index in range(100):
            response = client.post("/api/authority/grants", json={
                "agent": f"agent-{index}", "owner": "owner-a", "scope": "review:proposal", "action": "approve",
            })
            assert response.status_code == 201, response.text
            grant_ids.append(response.json()["id"])
        assert client.post(f"/api/authority/grants/{grant_ids[0]}/revoke").status_code == 200
        response = client.post("/api/authority/grants", json={
            "agent": "agent-extra", "owner": "owner-a", "scope": "review:proposal", "action": "approve",
        })
        assert response.status_code == (429 if demo_mode else 201)
        registry = client.get("/api/authority").json()
        assert len(registry["grants"]) == (100 if demo_mode else 101)
        assert next(grant for grant in registry["grants"] if grant["id"] == grant_ids[0])["revoked"]


@pytest.mark.parametrize("demo_mode", [True, False])
def test_intake_message_limit_rejects_whole_oversize_transcript_only_in_demo(tmp_path, demo_mode):
    with TestClient(create_app(tmp_path / "intake.sqlite3", demo_mode=demo_mode)) as client:
        accepted = client.post("/api/intake", json={"transcript": transcript(200)})
        assert accepted.status_code == 201 and len(accepted.json()["messages"]) == 200
        oversize = client.post("/api/intake", json={"transcript": transcript(201)})
        assert oversize.status_code == (422 if demo_mode else 201)
        assert len(client.get("/api/sessions").json()) == (1 if demo_mode else 2)


@pytest.mark.parametrize("demo_mode", [True, False])
def test_event_limit_preserves_idempotent_retry_and_never_persists_rejected_message(tmp_path, demo_mode):
    application = create_app(tmp_path / "events.sqlite3", demo_mode=demo_mode)
    with TestClient(application) as client:
        created = client.post("/api/intake", json={"transcript": transcript(199)})
        assert created.status_code == 201
        sid = created.json()["id"]
        event = {"event_id": "stable-source-id", "agent": "B", "content": "마지막 허용 메시지"}
        first = client.post(f"/api/sessions/{sid}/events", json=event)
        assert first.status_code == 200 and len(first.json()["messages"]) == 200
        for _ in range(2):
            retry = client.post(f"/api/sessions/{sid}/events", json=event)
            assert retry.status_code == 200
            assert retry.json()["messages"] == first.json()["messages"]
        before = application.state.store.get(sid)
        overflow = client.post(f"/api/sessions/{sid}/events", json={**event, "event_id": "new-source-id", "content": "한도 초과 새 메시지"})
        assert overflow.status_code == (429 if demo_mode else 200)
        after = application.state.store.get(sid)
        if demo_mode:
            assert after == before
            retry = client.post(f"/api/sessions/{sid}/events", json=event)
            assert retry.status_code == 200 and len(retry.json()["messages"]) == 200
        else:
            assert len(after["messages"]) == 201


def test_importing_lazy_asgi_does_not_create_default_database(tmp_path):
    database = tmp_path / "lazy.sqlite3"
    code = """from pathlib import Path
import os
from arbiter.app import app
assert not Path(os.environ['ARBITER_DB']).exists()
from fastapi.testclient import TestClient
with TestClient(app) as client:
    assert client.get('/api/health').json()['status'] == 'ok'
assert Path(os.environ['ARBITER_DB']).exists()
"""
    response = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                              env={**os.environ, "ARBITER_DB": str(database), "PYTHONPATH": str(ROOT / "backend")},
                              text=True, capture_output=True, timeout=15)
    assert response.returncode == 0, response.stderr
