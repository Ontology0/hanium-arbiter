"""MCP protocol checks, including a real stdio -> HTTP -> SQLite round trip."""

import asyncio
from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.memory import create_connected_server_and_client_session

from arbiter.mcp_server import create_server, next_action_from_state


ROOT = Path(__file__).resolve().parents[1]


def structured(result):
    assert not result.isError, result.content
    assert isinstance(result.structuredContent, dict)
    return result.structuredContent


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def local_process(args, *, env, log_path):
    with log_path.open("w+") as log:
        process = subprocess.Popen([sys.executable, *args], cwd=ROOT, env={**os.environ, **env},
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        try:
            yield process
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def await_http(url, process, log_path, *, expected=200):
    deadline = time.monotonic() + 15
    with httpx.Client(timeout=0.5, trust_env=False) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"Local process exited during startup: {log_path.read_text()}")
            try:
                if client.get(url).status_code == expected:
                    return
            except httpx.RequestError:
                pass
            time.sleep(0.05)
    pytest.fail(f"Local process did not become ready: {log_path.read_text()}")


@pytest.fixture
def live_api(tmp_path):
    port = unused_port()
    base_url = f"http://127.0.0.1:{port}"
    log = tmp_path / "api.log"
    environment = {"ARBITER_DB": str(tmp_path / "mcp-test.sqlite3"), "PYTHONPATH": str(ROOT / "backend")}
    args = ["-m", "uvicorn", "arbiter.app:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"]
    with local_process(args, env=environment, log_path=log) as process:
        await_http(base_url + "/api/health", process, log)
        yield base_url


def test_real_stdio_two_agents_human_dashboard_decision_and_resume(live_api):
    async def run():
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "arbiter.mcp_server"], cwd=ROOT,
                                           env={"ARBITER_API_URL": live_api, "PYTHONPATH": str(ROOT / "backend")})
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=15)) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "Hanium Arbiter"
                tools = (await session.list_tools()).tools
                assert {item.name for item in tools} == {
                    "register_conversation", "record_message", "get_coordination_state",
                    "list_pending_decisions", "get_human_decisions", "get_next_action",
                    "get_authority", "evaluate_authority",
                }
                created = structured(await session.call_tool("register_conversation", {
                    "title": "MCP protocol integration", "source": "slack", "agent": "A",
                    "initial_message": "제안서를 함께 검토합니다.",
                }))
                sid = created["session_id"]
                assert created["observation_mode"] == "explicit_tool_calls_only"
                first = {"session_id": sid, "event_id": "slack-thread-1-message-2", "agent": "A", "content": "B의 검토가 끝나면 진행하겠습니다."}
                second = {"session_id": sid, "event_id": "slack-thread-1-message-3", "agent": "B", "content": "A의 검토가 끝나면 진행하겠습니다."}
                structured(await session.call_tool("record_message", first))
                state = structured(await session.call_tool("record_message", second))
                duplicate = structured(await session.call_tool("record_message", second))
                assert len(state["messages"]) == len(duplicate["messages"]) == 3
                assert state["decisions"] == []
                waiting = structured(await session.call_tool("get_next_action", {"session_id": sid}))
                assert waiting["action"] == "wait_for_human"
                assert waiting["pending_decisions"]
                assert waiting["execution_status"] == "not_verified"
                assert waiting["delivery_status"] == "unknown"
                pending = structured(await session.call_tool("list_pending_decisions", {"session_id": sid}))["pending_decisions"]

                # A human-side HTTP operation is deliberately separate from MCP.
                # No tool in this server can impersonate this input.
                async with httpx.AsyncClient(base_url=live_api, trust_env=False) as human:
                    for question in pending:
                        option_ids = {option["id"] for option in question["options"]}
                        choice = "assign_owner" if "assign_owner" in option_ids else "assign_sender"
                        response = await human.post(f"/api/sessions/{sid}/decisions", json={
                            "request_id": question["id"], "choice": choice,
                            "note": "최종 책임자 A. A가 먼저 제안서를 검토하고 B에게 결과 전달을 준비한다.",
                        })
                        assert response.status_code == 200, response.text
                decisions = structured(await session.call_tool("get_human_decisions", {"session_id": sid}))
                assert len(decisions["decisions"]) == len(pending)
                assert all(item["source"] == "human_input" for item in decisions["decisions"])
                assert all(item["delivery_status"] == "not_sent" for item in decisions["decisions"])
                for _ in range(2):
                    advice = structured(await session.call_tool("get_next_action", {"session_id": sid}))
                    assert advice["action"] == "follow_human_decision"
                    assert advice["pending_decisions"] == []
                    assert advice["execution_status"] == "not_verified"
                after_retry = structured(await session.call_tool("record_message", second))
                assert len(after_retry["messages"]) == 3
                assert all(item["status"] == "resolved" for item in after_retry["requests"])
                assert len(after_retry["decisions"]) == len(pending)
                rejected = await session.call_tool("create_human_decision", {"session_id": sid, "choice": "assign_owner"})
                assert rejected.isError
    asyncio.run(run())


def test_streamable_http_initializes_and_reads_api(live_api, tmp_path):
    port = unused_port()
    url = f"http://127.0.0.1:{port}/mcp"
    log = tmp_path / "mcp-http.log"
    args = ["-m", "arbiter.mcp_server", "--transport", "streamable-http", "--port", str(port), "--api-url", live_api]
    with local_process(args, env={"PYTHONPATH": str(ROOT / "backend")}, log_path=log) as process:
        # A plain GET is not a negotiated Streamable HTTP request; 406 confirms
        # that the MCP endpoint, rather than a guessed health endpoint, is up.
        await_http(url, process, log, expected=406)
        async def run():
            async with streamable_http_client(url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    assert len((await session.list_tools()).tools) == 8
                    response = await session.call_tool("get_coordination_state", {"session_id": "missing-session"})
                    assert response.isError
                    assert "HTTP 404" in response.content[0].text
        asyncio.run(run())


def test_metadata_and_report_idempotency_pass_through_with_mock_http():
    requests = []
    saved = {}
    def handler(request):
        requests.append(request)
        if request.method == "POST":
            event = json.loads(request.content)
            saved.setdefault(event["event_id"], event)
        return httpx.Response(200, json={"id": "session-1", "messages": list(saved.values()), "_internal": "hidden",
                                        "task": {"api_key": "not-returned", "description": "visible"}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as api:
            server = create_server(client=api)
            async with create_connected_server_and_client_session(server) as session:
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                assert not tools["register_conversation"].annotations.idempotentHint
                assert not tools["register_conversation"].annotations.readOnlyHint
                assert tools["record_message"].annotations.idempotentHint
                assert not tools["record_message"].annotations.destructiveHint
                assert tools["get_human_decisions"].annotations.readOnlyHint
                assert not tools["get_human_decisions"].annotations.openWorldHint
                event = {"session_id": "session-1", "event_id": "source-stable-id", "agent": "pickle", "content": "주인에게 확인하겠습니다."}
                structured(await session.call_tool("record_message", event))
                result = structured(await session.call_tool("record_message", event))
                assert len(result["messages"]) == 1
                assert "_internal" not in result
                assert result["task"] == {"description": "visible"}
                assert len(requests) == 2  # The API, not a bridge cache, decides idempotence.
                assert all(request.url.path == "/api/sessions/session-1/events" for request in requests)
                assert all(json.loads(request.content)["event_id"] == "source-stable-id" for request in requests)
    asyncio.run(run())


def test_protocol_error_does_not_leak_server_response_or_retry_registration():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(500, text="internal credentials must never be echoed")
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as api:
            async with create_connected_server_and_client_session(create_server(client=api)) as session:
                result = await session.call_tool("register_conversation", {
                    "title": "failure", "source": "manual", "agent": "A", "initial_message": "안녕하세요",
                })
                assert result.isError
                assert "HTTP 500" in result.content[0].text
                assert "credentials" not in result.content[0].text
                assert len(requests) == 1
                invalid = await session.call_tool("get_coordination_state", {"session_id": "../api/config"})
                assert invalid.isError
                assert len(requests) == 1
    asyncio.run(run())


def test_report_timeout_preserves_event_id_and_never_claims_delivery():
    def handler(request):
        raise httpx.ReadTimeout("internal timeout details", request=request)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as api:
            async with create_connected_server_and_client_session(create_server(client=api)) as session:
                result = await session.call_tool("record_message", {
                    "session_id": "session-1", "event_id": "stable-id", "agent": "A", "content": "전달 예정",
                })
                assert result.isError
                assert "same event_id" in result.content[0].text
    asyncio.run(run())


def test_next_action_preserves_wait_and_prioritizes_new_pending_decision():
    state = {"id": "s", "mode": "import", "status": "stopped", "requests": [],
             "decisions": [{"id": "d1", "choice": "already_delivered", "source": "human_input"}],
             "coordination": {"delivery_status": "human_reported_delivered", "next_actions": []}}
    assert next_action_from_state(state, "http://127.0.0.1:8787/")["action"] == "wait_for_response"
    state["requests"].append({"id": "new-obligation", "status": "pending"})
    assert next_action_from_state(state, "http://127.0.0.1:8787/")["action"] == "wait_for_human"
    state["requests"].clear()
    state["coordination"]["delivery_status"] = "mixed"
    assert next_action_from_state(state, "http://127.0.0.1:8787/")["action"] == "follow_human_decision"


def test_http_binding_is_local_and_backend_url_cannot_be_redirected_to_remote_service():
    server = create_server()
    assert server.settings.host == "127.0.0.1"
    assert server.settings.port == 8788
    for invalid in ("https://remote.example", "http://127.0.0.1/another-api", "http://user:secret@127.0.0.1:8787"):
        with pytest.raises(ValueError):
            create_server(invalid)


def test_authority_tools_read_registry_and_evaluate_without_human_writes():
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.path == "/api/authority":
            return httpx.Response(200, json={"grants": [], "precedence": [], "source": "local_operator_record"})
        return httpx.Response(200, json={"status": "cross_owner_conflict", "decision_owner": None,
                                        "required_owners": ["owner-a", "owner-b"], "source": "local_operator_record"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as api:
            async with create_connected_server_and_client_session(create_server(client=api)) as session:
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                for name in ("get_authority", "evaluate_authority"):
                    assert tools[name].annotations.readOnlyHint
                    assert tools[name].annotations.idempotentHint
                    assert not tools[name].annotations.destructiveHint
                assert not {"grant_authority", "set_precedence", "create_human_decision"} & tools.keys()
                assert structured(await session.call_tool("get_authority", {}))["source"] == "local_operator_record"
                result = structured(await session.call_tool("evaluate_authority", {
                    "scope": "review:proposal", "action": "approve", "agents": ["A", "B"],
                }))
                assert result["status"] == "cross_owner_conflict"
                assert result["decision_owner"] is None
                assert [(request.method, request.url.path) for request in requests] == [
                    ("GET", "/api/authority"), ("POST", "/api/authority/evaluate"),
                ]
                assert json.loads(requests[-1].content) == {"scope": "review:proposal", "action": "approve", "agents": ["A", "B"]}
                bad = await session.call_tool("evaluate_authority", {"scope": "", "action": "approve"})
                assert bad.isError
                assert len(requests) == 2
    asyncio.run(run())


def test_real_stdio_and_skill_client_read_human_authority_then_scoped_priority(live_api):
    async def run():
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "arbiter.mcp_server"], cwd=ROOT,
                                           env={"ARBITER_API_URL": live_api, "PYTHONPATH": str(ROOT / "backend")})
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                query = {"scope": "review:proposal", "action": "approve", "agents": ["A", "B"]}
                empty = structured(await session.call_tool("evaluate_authority", query))
                assert empty["status"] == "authority_gap"
                async with httpx.AsyncClient(base_url=live_api, trust_env=False) as human:
                    for agent, owner in (("A", "owner-a"), ("B", "owner-b")):
                        response = await human.post("/api/authority/grants", json={
                            "agent": agent, "owner": owner, "scope": query["scope"], "action": query["action"],
                        })
                        assert response.status_code == 201, response.text
                    registry = structured(await session.call_tool("get_authority", {}))
                    assert len(registry["grants"]) == 2
                    conflict = structured(await session.call_tool("evaluate_authority", query))
                    assert conflict["status"] == "cross_owner_conflict"
                    assert conflict["decision_owner"] is None
                    assert conflict["required_owners"] == ["owner-a", "owner-b"]
                    response = await human.post("/api/authority/precedence", json={
                        **query, "agents": ["B", "A"], "approved_by": ["owner-a", "owner-b"],
                    })
                    assert response.status_code == 201, response.text
                priority = structured(await session.call_tool("evaluate_authority", query))
                assert priority["status"] == "authorized"
                assert priority["decision_owner"] == "B"
                assert priority["source"] == "local_operator_record" and priority["authority_only"]
                wrong_scope = structured(await session.call_tool("evaluate_authority", {**query, "scope": "review:other"}))
                assert wrong_scope["status"] == "authority_gap"
                rejected = await session.call_tool("grant_authority", {"agent": "A"})
                assert rejected.isError
                helper = ROOT / "skills/arbiter-coordination/scripts/arbiter_client.py"
                process = subprocess.run([sys.executable, "-I", str(helper), "--api-url", live_api, "evaluate",
                                          "--scope", query["scope"], "--action", query["action"], "--agents", "A", "B"],
                                         text=True, capture_output=True, timeout=10)
                assert process.returncode == 0, process.stderr
                assert json.loads(process.stdout) == priority
    asyncio.run(run())


def authority_advice_fixture():
    check = {"scope": "review:proposal", "action": "approve", "status": "authorized", "decision_owner": "B",
             "evidence_ids": ["m1", "m2"]}
    request = {"id": "old-authority-question", "status": "pending", "kind": "authority", "issue_type": "decision-owner", "evidence_ids": ["m1"]}
    return {"id": "s", "mode": "import", "status": "waiting", "requests": [request], "decisions": [], "coordination": {},
            "brief_view": {"available": True, "conversation_stale": False, "authority_stale": True, "stale": True,
                           "brief": {"authority_checks": [check], "intervention_points": [],
                                     "next_actions": [{"text": "B에게 현재 범위의 결정을 맡깁니다.", "basis": "authority_registry"}]}}}


def test_current_authority_covers_only_unambiguous_generic_questions_without_mutating_history():
    state = authority_advice_fixture()
    original = deepcopy(state)
    advice = next_action_from_state(state, "http://127.0.0.1/workspace")
    assert advice["action"] == "follow_authority" and advice["decision_owner"] == "B"
    assert len(advice["covered_pending_decisions"]) == 1
    assert advice["remaining_pending_decisions"] == []
    assert advice["pending_decisions"] == []
    assert advice["recorded_pending_decisions"][0]["status"] == "pending"
    assert advice["authority_next_actions"]
    assert state == original


@pytest.mark.parametrize("question_change", [
    {"kind": "handoff", "issue_type": "handoff-status"},
    {"kind": "coordination", "issue_type": "wait-cycle"},
    {"evidence_ids": []},
    {"evidence_ids": ["unmapped-message"]},
    {"evidence_ids": ["m1", "another-topic"]},
])
def test_unrelated_or_ambiguous_pending_dependency_is_not_cleared_by_authority(question_change):
    state = authority_advice_fixture()
    state["requests"][0].update(question_change)
    advice = next_action_from_state(state, "/workspace")
    assert advice["action"] == "wait_for_human"
    assert advice["remaining_pending_decisions"] == state["requests"]
    assert advice["covered_pending_decisions"] == []
    assert advice["authorized_scope_actions"][0]["decision_owner"] == "B"
    assert advice["authority_next_actions"] == []


def test_evidence_shared_by_two_scopes_cannot_cover_generic_question():
    state = authority_advice_fixture()
    check = state["brief_view"]["brief"]["authority_checks"][0]
    state["brief_view"]["brief"]["authority_checks"].append({**check, "scope": "review:other"})
    advice = next_action_from_state(state, "/workspace")
    assert advice["action"] == "wait_for_human"
    assert advice["covered_pending_decisions"] == []


def test_conversation_change_withholds_old_scope_actions_even_when_registry_is_current():
    state = authority_advice_fixture()
    state["brief_view"].update(conversation_stale=True, authority_stale=False)
    advice = next_action_from_state(state, "/workspace")
    assert advice["action"] == "refresh_coordination_context"
    assert advice["authority_context"] == "stale_conversation"
    assert advice["authorized_scope_actions"] == []
    assert advice["authority_next_actions"] == []
    assert advice["covered_pending_decisions"] == []


def test_revoked_or_conflicting_authority_requires_human_without_reusing_old_approval():
    state = authority_advice_fixture()
    state["brief_view"]["brief"]["authority_checks"][0].update(status="authority_gap", decision_owner=None)
    state["brief_view"]["brief"]["intervention_points"] = [{"text": "권한을 확인해 주세요."}]
    advice = next_action_from_state(state, "/workspace")
    assert advice["action"] == "wait_for_human"
    assert advice["authorized_scope_actions"] == []
    assert advice["authority_next_actions"] == []
    assert advice["authority_interventions"]
    assert advice["blocked_scope_actions"][0]["status"] == "authority_gap"


def test_current_authority_does_not_override_recorded_human_response_wait():
    state = authority_advice_fixture()
    state["detector"] = {"intentional_human_wait": True}
    advice = next_action_from_state(state, "/workspace")
    assert advice["action"] == "wait_for_response"
    assert advice["authorized_scope_actions"][0]["decision_owner"] == "B"
    assert advice["authority_next_actions"] == []


def test_real_stdio_authority_resolution_revoke_and_new_conversation_without_model_call(live_api, tmp_path):
    from arbiter.briefing import apply_authority_rules, authority_digest, conversation_digest
    from arbiter.storage import SessionStore

    store = SessionStore(tmp_path / "mcp-test.sqlite3")
    async def run():
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "arbiter.mcp_server"], cwd=ROOT,
                                           env={"ARBITER_API_URL": live_api, "PYTHONPATH": str(ROOT / "backend")})
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session, httpx.AsyncClient(base_url=live_api, trust_env=False) as human:
                await session.initialize()
                query = {"scope": "review:proposal", "action": "approve"}
                grant_ids = []
                for agent, owner in (("A", "owner-a"), ("B", "owner-b")):
                    response = await human.post("/api/authority/grants", json={**query, "agent": agent, "owner": owner})
                    assert response.status_code == 201, response.text
                    grant_ids.append(response.json()["id"])
                state = structured(await session.call_tool("register_conversation", {
                    "title": "Authority advice integration", "source": "manual", "agent": "A", "initial_message": "제안서를 검토합니다.",
                }))
                sid = state["session_id"]
                structured(await session.call_tool("record_message", {
                    "session_id": sid, "event_id": "review-2", "agent": "B", "content": "제안서 승인권을 논의합니다.",
                }))
                # Seed the extractor's structured result; no model is invoked.
                saved = store.get(sid)
                registry = store.get_authority()
                evidence = [{"message_id": message["id"], "quote": message["content"]} for message in saved["messages"]]
                brief = {"source": "test_fixture", "source_digest": conversation_digest(saved), "authority_digest": authority_digest(registry),
                         "next_actions": [], "decision_points": [{**query, "agents": ["A", "B"], "state": "unresolved",
                                                                 "evidence_ids": [item["message_id"] for item in evidence], "evidence": evidence}]}
                saved.update(brief=apply_authority_rules(brief, registry), brief_status="ready")
                store.save(saved)
                original_brief = deepcopy(saved["brief"])

                initial = structured(await session.call_tool("get_next_action", {"session_id": sid}))
                assert initial["action"] == "wait_for_human"
                assert initial["blocked_scope_actions"][0]["status"] == "cross_owner_conflict"
                subset = structured(await session.call_tool("evaluate_authority", {**query, "agents": ["A"]}))
                assert subset["status"] == "cross_owner_conflict"
                assert subset["evaluation_scope"] == "all_scope_holders"
                assert subset["requested_authorized_agents"] == ["A"]

                async def precedence(approvals):
                    registry = (await human.get("/api/authority")).json()
                    response = await human.post("/api/authority/precedence", json={
                        **query, "agents": ["B", "A"], "approved_by": approvals, "expected_revision": registry["registry_revision"],
                    })
                    assert response.status_code == 201, response.text

                await precedence(["owner-a"])
                partial = structured(await session.call_tool("get_next_action", {"session_id": sid}))
                assert partial["action"] == "wait_for_human"
                assert partial["covered_pending_decisions"] == []
                await precedence(["owner-a", "owner-b"])
                authorized = structured(await session.call_tool("get_next_action", {"session_id": sid}))
                assert authorized["action"] == "follow_authority" and authorized["decision_owner"] == "B"
                assert len(authorized["covered_pending_decisions"]) == 2
                assert authorized["remaining_pending_decisions"] == []
                questions = structured(await session.call_tool("list_pending_decisions", {"session_id": sid}))
                assert questions["pending_decisions"] == []
                assert len(questions["recorded_pending_decisions"]) == 2
                assert len(questions["covered_pending_decisions"]) == 2
                assert structured(await session.call_tool("get_human_decisions", {"session_id": sid}))["decisions"] == []
                fresh = structured(await session.call_tool("get_coordination_state", {"session_id": sid}))
                assert fresh["brief_view"]["authority_stale"] and not fresh["brief_view"]["conversation_stale"]
                assert fresh["brief"]["authority_checks"][0]["decision_owner"] == "B"
                assert store.get(sid)["brief"] == original_brief
                assert all(item["status"] == "pending" for item in store.get(sid)["requests"])
                helper = ROOT / "skills/arbiter-coordination/scripts/arbiter_client.py"
                process = subprocess.run([sys.executable, "-I", str(helper), "--api-url", live_api,
                                          "next-action", "--session-id", sid], text=True, capture_output=True, timeout=10)
                assert process.returncode == 0, process.stderr
                assert json.loads(process.stdout) == authorized

                for grant_id in grant_ids:
                    assert (await human.post(f"/api/authority/grants/{grant_id}/revoke")).status_code == 200
                revoked = structured(await session.call_tool("get_next_action", {"session_id": sid}))
                assert revoked["action"] == "wait_for_human"
                assert revoked["authorized_scope_actions"] == []
                assert revoked["blocked_scope_actions"][0]["status"] == "authority_gap"
                fresh = structured(await session.call_tool("get_coordination_state", {"session_id": sid}))
                assert fresh["brief"]["authority_checks"][0]["status"] == "authority_gap"

                # Regrant and approve the same scope, then change the transcript.
                for agent, owner in (("A", "owner-a"), ("B", "owner-b")):
                    assert (await human.post("/api/authority/grants", json={**query, "agent": agent, "owner": owner})).status_code == 201
                await precedence(["owner-a", "owner-b"])
                structured(await session.call_tool("record_message", {
                    "session_id": sid, "event_id": "changed-topic", "agent": "A", "content": "대상이 다른 제안서로 바뀌었습니다.",
                }))
                changed = structured(await session.call_tool("get_next_action", {"session_id": sid}))
                assert changed["action"] == "refresh_coordination_context"
                assert changed["authorized_scope_actions"] == [] and changed["authority_next_actions"] == []
                assert store.get(sid)["brief"] == original_brief
    asyncio.run(run())
