"""Human-recorded scoped priorities stay current across API and agent reads."""
from copy import deepcopy

from fastapi.testclient import TestClient
import pytest

from arbiter.app import create_app
from arbiter.briefing import authority_digest, conversation_digest
from arbiter.conversations import create_import
from arbiter.storage import SessionStore


QUERY = {"scope": "release", "action": "approve"}


def add_holders(client):
    grants = []
    for agent, owner in (("A", "owner-a"), ("B", "owner-b")):
        response = client.post("/api/authority/grants", json={**QUERY, "agent": agent, "owner": owner})
        assert response.status_code == 201
        grants.append(response.json())
    return grants


def record_priority(client, approvals, **changes):
    return client.post("/api/authority/precedence", json={
        **QUERY, "agents": ["B", "A"], "approved_by": approvals,
        "expected_revision": client.get("/api/authority").json()["registry_revision"], **changes,
    })


def test_partial_approval_then_joint_approval_is_scoped_and_survives_restart(tmp_path):
    path = tmp_path / "authority.sqlite3"
    with TestClient(create_app(path)) as client:
        add_holders(client)
        assert record_priority(client, ["owner-a"]).status_code == 201
        partial = client.post("/api/authority/evaluate", json=QUERY).json()
        assert partial["status"] == "cross_owner_conflict"
        assert partial["decision_owner"] is None
        assert record_priority(client, ["owner-a", "owner-b"]).status_code == 201
        resolved = client.post("/api/authority/evaluate", json=QUERY).json()
        assert resolved["decision_owner"] == "B"
        assert resolved["registry_revision"] != partial["registry_revision"]
        other = client.post("/api/authority/evaluate", json={**QUERY, "action": "deploy"}).json()
        assert other["status"] == "authority_gap"
    with TestClient(create_app(path)) as client:
        assert client.post("/api/authority/evaluate", json=QUERY).json()["decision_owner"] == "B"


def test_stale_operator_form_cannot_overwrite_newer_priority(tmp_path):
    with TestClient(create_app(tmp_path / "authority.sqlite3")) as client:
        add_holders(client)
        old_revision = client.get("/api/authority").json()["registry_revision"]
        assert record_priority(client, ["owner-a", "owner-b"]).status_code == 201
        before = client.get("/api/authority").json()
        rejected = record_priority(client, ["owner-a", "owner-b"],
                                   agents=["A", "B"], expected_revision=old_revision)
        assert rejected.status_code == 409
        assert client.get("/api/authority").json() == before
        assert client.post("/api/authority/evaluate", json=QUERY).json()["decision_owner"] == "B"


def test_new_grants_do_not_reuse_approvals_for_revoked_grants(tmp_path):
    with TestClient(create_app(tmp_path / "authority.sqlite3")) as client:
        old = add_holders(client)
        assert record_priority(client, ["owner-a", "owner-b"]).status_code == 201
        for grant in old:
            assert client.post(f"/api/authority/grants/{grant['id']}/revoke").status_code == 200
        add_holders(client)
        result = client.post("/api/authority/evaluate", json=QUERY).json()
        assert result["status"] == "cross_owner_conflict"
        assert result["decision_owner"] is None


@pytest.mark.parametrize("agents", [["A"], []])
def test_agent_filter_cannot_hide_another_owners_authority(tmp_path, agents):
    with TestClient(create_app(tmp_path / "authority.sqlite3")) as client:
        add_holders(client)
        result = client.post("/api/authority/evaluate", json={**QUERY, "agents": agents}).json()
        assert result["status"] == "cross_owner_conflict"
        assert result["decision_owner"] is None
        assert result["required_owners"] == ["owner-a", "owner-b"]
        assert result["evaluation_scope"] == "all_scope_holders"
        assert result["requested_authorized_agents"] == agents


@pytest.mark.parametrize("changes", [{"agents": ["A"]}, {"agents": ["B", "A", "unregistered"]},
                                      {"approved_by": ["unrelated-owner"]}])
def test_priority_rejects_missing_holders_and_unrelated_approvals(tmp_path, changes):
    with TestClient(create_app(tmp_path / "authority.sqlite3")) as client:
        add_holders(client)
        assert record_priority(client, ["owner-a", "owner-b"], **changes).status_code == 422
        assert client.get("/api/authority").json()["precedence"] == []


def test_session_read_rechecks_authority_without_rewriting_model_evidence(tmp_path, monkeypatch):
    path = tmp_path / "authority.sqlite3"
    def forbidden_model_call(*args):
        pytest.fail("Authority re-evaluation must not call the model")
    monkeypatch.setattr("arbiter.briefing.run_codex_json", forbidden_model_call)
    with TestClient(create_app(path)) as client:
        grants = add_holders(client)
        store = SessionStore(path)
        state = create_import("A: 배포 승인권을 정해주세요.")
        evidence = [{"message_id": "m1", "quote": "배포 승인권을 정해주세요."}]
        state["brief"] = {"source": "test_fixture", "source_digest": conversation_digest(state),
                          "authority_digest": authority_digest(store.get_authority()), "next_actions": [],
                          "decision_points": [{**QUERY, "state": "unresolved", "evidence_ids": ["m1"],
                                               "evidence": evidence}]}
        state["brief_status"] = "ready"
        store.save(state)
        stored = deepcopy(store.get(state["id"]))
        endpoint = f"/api/sessions/{state['id']}"
        assert client.get(endpoint).json()["brief"]["authority_checks"][0]["status"] == "cross_owner_conflict"
        assert record_priority(client, ["owner-a", "owner-b"]).status_code == 201
        ready = client.get(endpoint).json()
        assert ready["brief"]["authority_checks"][0]["decision_owner"] == "B"
        assert ready["brief_view"]["authority_stale"] is True
        assert ready["brief_view"]["conversation_stale"] is False
        for grant in grants:
            client.post(f"/api/authority/grants/{grant['id']}/revoke")
        revoked = client.get(endpoint).json()
        assert revoked["brief"]["authority_checks"][0]["status"] == "authority_gap"
        assert revoked["brief"]["authority_checks"][0]["decision_owner"] is None
        assert store.get(state["id"]) == stored
