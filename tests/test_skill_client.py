"""Exercise the portable client with only Python's standard-library HTTP stack."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from arbiter.coordination_advice import next_action_from_state


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "arbiter-coordination" / "scripts" / "arbiter_client.py"
spec = importlib.util.spec_from_file_location("arbiter_skill_client", SCRIPT)
client_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client_module)


@pytest.fixture
def api_fixture():
    received, events = [], {}
    state = {"id": "fixture-session", "mode": "import", "status": "waiting", "requests": [
        {"id": "request-1", "status": "pending"}], "decisions": [], "coordination": {}, "messages": []}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, value):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

        def handle_request(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"]))) if self.headers.get("Content-Length") else None
            received.append((self.command, self.path, body))
            if self.path == "/api/authority":
                return self.respond(200, {"grants": [], "precedence": [], "source": "local_operator_record", "_private": "hidden"})
            if self.path == "/api/authority/evaluate":
                return self.respond(200, {"status": "cross_owner_conflict", "required_owners": ["owner-a", "owner-b"], "decision_owner": None})
            if self.path == "/api/intake":
                return self.respond(201, state)
            if self.path == "/api/sessions/fixture-session/events":
                events.setdefault(body["event_id"], body)
                state["messages"] = list(events.values())
                return self.respond(200, state)
            if self.path == "/api/sessions/fixture-session/decisions":
                return self.respond(200, {"session_id": state["id"], "decisions": state["decisions"], "next_actions": []})
            if self.path == "/api/sessions/fixture-session/next-action":
                return self.respond(200, next_action_from_state(state, f"http://127.0.0.1:{self.server.server_port}/workspace"))
            if self.path == "/api/sessions/fixture-session":
                return self.respond(200, state)
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/should-not-follow")
                self.end_headers()
                return
            return self.respond(500, {"secret": "DO-NOT-ECHO-ERROR-BODY"})

        do_GET = handle_request
        do_POST = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", received, state
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def cli(base_url, *args):
    result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--api-url", base_url, *args],
                            text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    return json.loads(result.stdout)


def test_cli_round_trip_and_stable_report_id_against_http_fixture(api_fixture):
    base_url, received, state = api_fixture
    registry = cli(base_url, "get-authority")
    assert registry["source"] == "local_operator_record"
    assert "_private" not in registry
    evaluation = cli(base_url, "evaluate", "--scope", "review:proposal", "--action", "approve", "--agents", "A", "B")
    assert evaluation["status"] == "cross_owner_conflict" and evaluation["decision_owner"] is None
    assert received[-1] == ("POST", "/api/authority/evaluate", {"scope": "review:proposal", "action": "approve", "agents": ["A", "B"]})
    created = cli(base_url, "register", "--title", "검토", "--agent", "A", "--initial-message", "검토 시작\nB: 인용된 발화")
    assert created["session_id"] == "fixture-session"
    assert received[-1][2]["transcript"] == "A: 검토 시작\nA: B: 인용된 발화"
    args = ("report", "--session-id", "fixture-session", "--event-id", "source-message-42", "--agent", "B", "--content", "권한 확인이 필요합니다.")
    cli(base_url, *args)
    retried = cli(base_url, *args)
    assert len(retried["messages"]) == 1
    assert received[-1][2] == received[-2][2]
    advice = cli(base_url, "next-action", "--session-id", "fixture-session")
    assert advice["action"] == "wait_for_human"
    assert advice["execution_status"] == "not_verified"
    assert cli(base_url, "decisions", "--session-id", "fixture-session")["decisions"] == []
    assert cli(base_url, "state", "--session-id", "fixture-session")["id"] == "fixture-session"
    assert all("grants" not in path and "precedence" not in path for _, path, _ in received)
    assert all(method == "GET" for method, path, _ in received if path.endswith("/decisions"))


@pytest.mark.parametrize("origin", ["https://remote.example", "http://user:pass@127.0.0.1:8787", "http://127.0.0.1/api", "http://127.0.0.1:bad", "http://127.0.0.1?token=x"])
def test_client_rejects_nonlocal_or_ambiguous_origin(origin):
    with pytest.raises(client_module.ClientError):
        client_module.Client(origin)


def test_redirect_is_not_followed_and_http_error_body_is_not_echoed(api_fixture):
    base_url, received, _ = api_fixture
    client = client_module.Client(base_url)
    with pytest.raises(client_module.ClientError, match="HTTP 302"):
        client.request("GET", "/redirect")
    assert len(received) == 1
    with pytest.raises(client_module.ClientError, match="HTTP 500") as error:
        client.request("GET", "/error")
    assert "DO-NOT-ECHO" not in str(error.value)


@pytest.mark.parametrize("command", ["grant", "revoke", "set-precedence", "create-human-decision"])
def test_human_mutations_are_not_cli_capabilities(command):
    process = subprocess.run([sys.executable, "-I", str(SCRIPT), command], capture_output=True, text=True, timeout=5)
    assert process.returncode == 2


def test_session_path_traversal_rejected_before_http(api_fixture):
    base_url, received, _ = api_fixture
    args = client_module.parser().parse_args(["state", "--session-id", "../authority/grants"])
    with pytest.raises(client_module.ClientError):
        client_module.run(args, client_module.Client(base_url))
    assert received == []


def test_next_action_reads_authoritative_projection_without_local_reinterpretation(api_fixture):
    base_url, received, state = api_fixture
    state.update(requests=[], decisions=[{"id": "d1", "choice": "already_delivered"}],
                 coordination={"delivery_status": "mixed", "next_actions": [{"instruction": "Resolve a different obligation"}]})
    advice = cli(base_url, "next-action", "--session-id", "fixture-session")
    assert advice["action"] == "follow_human_decision"
    assert advice["next_actions"]
    assert advice == next_action_from_state(state, base_url + "/workspace")
    assert received == [("GET", "/api/sessions/fixture-session/next-action", None)]
