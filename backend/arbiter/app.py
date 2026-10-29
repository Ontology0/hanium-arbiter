from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import lru_cache
import json
import os
from pathlib import Path
import shlex
import shutil
import threading
import time
from typing import Literal
from urllib.parse import urlsplit
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .domain import apply_decision, create_state, evaluate_state, ingest_event, next_demo_event, ontology_graph, scenario_catalog
from .conversations import append_external_event, conversation_graph, create_import, decide_import
from .providers import ProviderError, codex_available, codex_event
from .reporting import session_markdown
from .storage import SessionStore, now
from .briefing import brief_view, build_brief
from .slack_ingest import allowed_channels, ingest_slack


ROOT = Path(__file__).resolve().parents[2]


class NewSession(BaseModel):
    scenario_id: str
    policy: Literal["capped", "periodic", "adaptive"] = "adaptive"
    mode: Literal["demo", "codex"] = "demo"
    max_turns: int = Field(default=18, ge=2, le=60)
    periodic_every: int = Field(default=4, ge=1, le=20)
    stall_window: int = Field(default=3, ge=1, le=12)


class DecisionInput(BaseModel):
    request_id: str = Field(min_length=1, max_length=200)
    choice: str = Field(min_length=1, max_length=200)
    note: str = Field(default="", max_length=4000)


class IntakeInput(BaseModel):
    transcript: str = Field(min_length=1, max_length=40000)
    title: str = Field(default="가져온 협업 대화", min_length=1, max_length=150)
    source: Literal["pickle", "slack", "manual"] = "manual"


class ExternalEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=200)
    agent: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=10000)


class AuthorityGrant(BaseModel):
    agent: str = Field(min_length=1, max_length=100)
    owner: str = Field(min_length=1, max_length=100)
    scope: str = Field(min_length=1, max_length=200)
    action: str = Field(min_length=1, max_length=100)
    conditions: list[str] = Field(default_factory=list, max_length=20)
    expires_at: str | None = None


class AuthorityPrecedence(BaseModel):
    scope: str = Field(min_length=1, max_length=200)
    action: str = Field(min_length=1, max_length=100)
    agents: list[str] = Field(min_length=1, max_length=100)
    approved_by: list[str] = Field(default_factory=list, max_length=100)
    expected_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class AuthorityQuery(BaseModel):
    scope: str = Field(min_length=1, max_length=200)
    action: str = Field(min_length=1, max_length=100)
    agents: list[str] | None = Field(default=None, max_length=100)


def create_app(db_path: str | Path | None = None, *, demo_mode: bool = False) -> FastAPI:
    store = SessionStore(db_path or os.environ.get("ARBITER_DB", str(ROOT / ".runtime" / "arbiter.sqlite3")))
    store.recover()
    locks: dict[str, threading.RLock] = {}
    lock_guard = threading.Lock()
    slack_lock = threading.Lock()
    authority_lock = threading.Lock()
    creation_lock = threading.Lock()
    workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="arbiter")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        for state in store.list():
            with session_lock(state["id"]):
                current = store.get(state["id"])
                if current and current.get("busy"):
                    current["stop_requested"] = True
                    store.save(current)
        workers.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Arbiter", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.workers = workers

    def session_lock(session_id: str) -> threading.RLock:
        with lock_guard:
            return locks.setdefault(session_id, threading.RLock())

    def fetch(session_id: str) -> dict:
        state = store.get(session_id)
        if state is None:
            raise HTTPException(404, "실행을 찾을 수 없습니다.")
        return state

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        # A local CLI runner must not accept browser-triggered requests from another site.
        if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "다른 출처의 실행 요청은 허용하지 않습니다."}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "다른 출처의 실행 요청은 허용하지 않습니다."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/config")
    def config():
        return {
            "deployment": {
                "mode": "visitor_demo" if demo_mode else "local",
                "isolated": demo_mode,
                "live_model_available": not demo_mode and codex_available(),
                "reset_url": "/api/demo/reset" if demo_mode else None,
                "notice": "방문자별로 분리된 예시 체험입니다. 실제 외부 에이전트·소유자와 연결되지 않습니다." if demo_mode else "",
            },
            "scenarios": scenario_catalog(),
            "providers": [
                {"id": "demo", "label": "통제 시뮬레이션", "available": True},
                {"id": "codex", "label": "실제 에이전트 · Codex", "available": not demo_mode and codex_available()},
            ],
            "policies": [
                {"id": "capped", "label": "횟수 제한"},
                {"id": "periodic", "label": "주기적 HITL"},
                {"id": "adaptive", "label": "정체 감지 HITL"},
            ],
        }

    @app.get("/api/integration")
    def integration(request: Request):
        api_base = str(request.base_url).rstrip("/")
        if demo_mode:
            return {
                "deployment_mode": "visitor_demo", "available": False,
                "repository_url": "https://github.com/Ontology0/hanium-arbiter",
                "mcp": {"available": False, "tools": [], "config": None},
                "slack": {"configured": False, "status": "not_connected", "allowed_channels": [], "received_events": 0},
                "limitations": [
                    "이 주소는 방문자별 체험 페이지이며 외부 에이전트용 MCP 서버가 아닙니다.",
                    "MCP·A2A·Slack 연결은 오픈소스를 내려받아 자신의 환경에서 설정할 수 있습니다.",
                    "기록된 모델 분석과 통제 시뮬레이션을 사용하며 외부 모델·Slack을 호출하지 않습니다.",
                ],
            }
        command = shutil.which("uv") or "uv"
        args = ["--directory", str(ROOT), "run", "python", "-m", "arbiter.mcp_server"]
        slack_sessions = [state for state in store.list() if state.get("slack")]
        received = sum(len(state["slack"].get("event_ids", [])) for state in slack_sessions)
        channels = allowed_channels()
        return {
            "api_base": api_base,
            "mcp": {
                "stdio_command": shlex.join([command, *args]),
                "streamable_http_url": "http://127.0.0.1:8788/mcp",
                "config": {"mcpServers": {"arbiter": {"command": command, "args": args,
                            "env": {"ARBITER_API_URL": api_base}}}},
                "tools": ["register_conversation", "record_message", "get_coordination_state",
                          "list_pending_decisions", "get_human_decisions", "get_next_action", "get_authority", "evaluate_authority"],
            },
            "slack": {
                "status": "events_received" if received else "awaiting_events",
                "configured": bool(channels and os.environ.get("SLACK_APP_TOKEN") and os.environ.get("SLACK_BOT_TOKEN")),
                "allowed_channels": channels,
                "received_events": received,
                "last_received_at": max((s["slack"].get("last_received_at", "") for s in slack_sessions), default=None),
                "command": shlex.join([command, "--directory", str(ROOT), "run", "--env-file", ".env", "python", "-m", "arbiter.slack_bridge"]),
                "setup_url": "/api/integration/slack-manifest",
                "limitations": ["앱 설치와 채널 초대, 로컬 .env의 토큰·채널 설정이 필요합니다.",
                                "수신 상태는 저장된 이벤트 기준입니다. 현재 WebSocket 연결 상태를 보장하지 않습니다.",
                                "수신한 스레드만 관찰하며 과거 대화를 자동으로 가져오거나 Slack에 메시지를 보내지 않습니다."],
            },
            "limitations": [
                "MCP를 추가한 뒤 에이전트에게 대화 등록·새 메시지 보고·다음 행동 조회를 지시해야 합니다. 연결만으로 대화를 자동 수집하지 않습니다.",
                "Streamable HTTP 주소는 별도 서버를 --transport streamable-http 옵션으로 실행했을 때 사용할 수 있습니다.",
                "MCP와 API 연결은 같은 컴퓨터에서 사용합니다. Slack 수신은 별도 Socket Mode 연결을 설정해야 합니다.",
                "사람은 관제 화면에서 결정합니다. 에이전트에 사람의 결정을 생성하는 MCP 도구는 제공하지 않습니다.",
                "기록된 다음 행동은 외부 메시지 발송이나 작업 실행 완료를 의미하지 않습니다.",
            ],
        }

    @app.get("/api/integration/slack-manifest")
    def slack_manifest():
        path = ROOT / "slack-app-manifest.json"
        if not path.exists():
            raise HTTPException(404, "Slack 앱 설정 파일을 준비 중입니다.")
        return FileResponse(path, media_type="application/json")

    @app.post("/api/slack/events")
    def slack_events(payload: dict):
        if demo_mode:
            raise HTTPException(403, "공개 체험에서는 외부 Slack 수신을 제공하지 않습니다.")
        try:
            with slack_lock:
                # Session read-modify-write also shares the normal decision lock.
                # Slack ingestion is serial; lock all currently known Slack sessions
                # so human decisions cannot be overwritten by an arriving event.
                from contextlib import ExitStack
                with ExitStack() as stack:
                    for item in store.list():
                        if item.get("slack"):
                            stack.enter_context(session_lock(item["id"]))
                    return ingest_slack(store, payload)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @app.get("/api/sessions")
    def sessions():
        fields = {"id", "title", "scenario_id", "policy", "mode", "status", "turn", "max_turns", "busy", "metrics", "created_at", "updated_at"}
        return [{key: value for key, value in state.items() if key in fields} for state in store.list()]

    @app.get("/api/authority")
    def get_authority():
        from .authority import registry_revision
        registry = store.get_authority()
        return {**registry, "registry_revision": registry_revision(registry), "source": "local_operator_record",
                "notice": "로컬 운영자가 기록한 위임 정보입니다. 외부 소유자의 신원·동의를 인증한 결과는 아닙니다."}

    @app.post("/api/authority/evaluate")
    def check_authority(body: AuthorityQuery):
        from .authority import evaluate_authority
        # A caller-supplied participant list must not hide another owner's rights.
        result = evaluate_authority(store.get_authority(), body.scope, body.action)
        result["evaluation_scope"] = "all_scope_holders"
        if body.agents is not None:
            result["requested_agents"] = body.agents
            result["requested_authorized_agents"] = [agent for agent in result["authorized_agents"] if agent in body.agents]
        return result

    @app.post("/api/authority/grants", status_code=201)
    def add_authority_grant(body: AuthorityGrant):
        if body.expires_at:
            from datetime import datetime
            try:
                expiration = datetime.fromisoformat(body.expires_at.replace("Z", "+00:00"))
                if expiration.tzinfo is None:
                    raise ValueError("timezone missing")
            except ValueError as error:
                raise HTTPException(422, "권한 만료 시각은 시간대가 포함된 ISO 날짜로 입력해 주세요.") from error
        with authority_lock:
            registry = store.get_authority()
            if demo_mode and len(registry["grants"]) >= 100:
                raise HTTPException(429, "체험 위임 기록 한도에 도달했습니다. 내 체험을 초기화해 주세요.")
            grant = {**body.model_dump(), "id": "grant-" + uuid.uuid4().hex, "issuer": "local-human",
                     "source": "local_operator_record", "created_at": now(), "revoked": False}
            registry["grants"].append(grant)
            store.save_authority(registry)
            return grant

    @app.post("/api/authority/grants/{grant_id}/revoke")
    def revoke_authority_grant(grant_id: str):
        with authority_lock:
            registry = store.get_authority()
            grant = next((item for item in registry["grants"] if item["id"] == grant_id), None)
            if not grant:
                raise HTTPException(404, "위임 기록을 찾을 수 없습니다.")
            grant.update(revoked=True, revoked_at=now())
            store.save_authority(registry)
            return grant

    @app.post("/api/authority/precedence", status_code=201)
    def set_authority_precedence(body: AuthorityPrecedence):
        from .authority import evaluate_authority, grant_revision, registry_revision
        if len(set(body.agents)) != len(body.agents):
            raise HTTPException(422, "우선순위에 같은 에이전트를 두 번 지정할 수 없습니다.")
        if (not body.scope.strip() or not body.action.strip()
                or any(not item.strip() for item in body.agents + body.approved_by)
                or len(set(body.approved_by)) != len(body.approved_by)):
            raise HTTPException(422, "범위·행동·에이전트·소유자는 빈 값 없이 입력하고 승인 소유자는 중복 없이 선택해 주세요.")
        with authority_lock:
            registry = store.get_authority()
            if body.expected_revision is not None and body.expected_revision != registry_revision(registry):
                raise HTTPException(409, "확인 중 권한 기록이 바뀌었습니다. 최신 위임과 우선순위를 다시 확인해 주세요.")
            current = evaluate_authority(registry, body.scope, body.action)
            if (current["status"] not in {"authorized", "authority_conflict", "cross_owner_conflict"}
                    or set(body.agents) != set(current["authorized_agents"])):
                raise HTTPException(422, "이 범위·행동에서 현재 유효한 위임을 가진 에이전트를 모두 포함해야 합니다.")
            if not set(body.approved_by).issubset(current["required_owners"]):
                raise HTTPException(422, "이 위임과 관련된 소유자의 승인만 기록할 수 있습니다.")
            record = {**body.model_dump(exclude={"expected_revision"}), "issuer": "local-human",
                      "source": "local_operator_record", "created_at": now(),
                      "grant_revision": grant_revision(registry, body.scope, body.action)}
            registry["precedence"] = [item for item in registry["precedence"] if (item["scope"], item["action"]) != (body.scope, body.action)] + [record]
            store.save_authority(registry)
            return record

    @app.post("/api/sessions", status_code=201)
    def new_session(body: NewSession):
        if demo_mode and body.mode != "demo":
            raise HTTPException(403, "공개 체험에서는 통제 시뮬레이션만 실행할 수 있습니다.")
        if body.mode == "codex" and not codex_available():
            raise HTTPException(422, "Codex CLI 설치와 로그인이 필요합니다.")
        try:
            state = create_state(**body.model_dump())
        except (ValueError, KeyError) as error:
            raise HTTPException(422, str(error)) from error
        state.update(id=uuid.uuid4().hex, created_at=now(), busy=False, stop_requested=False, last_error=None)
        state["validation"] = evaluate_state(state)
        with creation_lock:
            if demo_mode and len(store.list()) >= 12:
                raise HTTPException(429, "체험 대화 한도에 도달했습니다. 내 체험을 초기화해 주세요.")
            store.save(state)
        return state

    def coordination_snapshot(session_id: str, dashboard_url: str):
        from .coordination_advice import next_action_from_state
        state = fetch(session_id)
        view = brief_view(state, store.get_authority())
        # Return fresh authority without rewriting the original model evidence.
        snapshot = {**state, "brief": view["brief"], "brief_view": view}
        snapshot["coordination_advice"] = next_action_from_state(snapshot, dashboard_url)
        return snapshot

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str, request: Request):
        return coordination_snapshot(session_id, str(request.base_url).rstrip("/") + "/workspace")

    @app.get("/api/sessions/{session_id}/next-action")
    def get_next_action(session_id: str, request: Request):
        return coordination_snapshot(session_id, str(request.base_url).rstrip("/") + "/workspace")["coordination_advice"]

    @app.get("/api/sessions/{session_id}/brief")
    def get_brief(session_id: str):
        return brief_view(fetch(session_id), store.get_authority())

    def generate_brief(session_id: str, snapshot: dict, generation_id: str):
        try:
            result = build_brief(snapshot, store.get_authority())
            with session_lock(session_id):
                current = fetch(session_id)
                if current.get("brief_generation_id") == generation_id:
                    current.update(brief=result, brief_status="ready", brief_error=None)
                    store.save(current)
        except Exception as error:
            with session_lock(session_id):
                current = fetch(session_id)
                if current.get("brief_generation_id") == generation_id:
                    current.update(brief_status="error", brief_error=str(error) if isinstance(error, ProviderError) else "브리핑 생성에 실패했습니다.")
                    store.save(current)

    @app.post("/api/sessions/{session_id}/brief", status_code=202)
    def start_brief(session_id: str):
        if demo_mode:
            raise HTTPException(403, "공개 체험은 기록된 분석을 사용합니다. 새 모델 호출은 자신의 설치 환경에서 사용할 수 있습니다.")
        with session_lock(session_id):
            state = fetch(session_id)
            if state.get("brief_status") == "generating":
                raise HTTPException(409, "브리핑을 생성 중입니다.")
            if not codex_available():
                raise HTTPException(422, "브리핑에는 설치·로그인된 Codex CLI가 필요합니다.")
            generation_id = uuid.uuid4().hex
            state.update(brief_status="generating", brief_error=None, brief_generation_id=generation_id)
            store.save(state)
            workers.submit(generate_brief, session_id, state, generation_id)
            return brief_view(state, store.get_authority())

    @app.post("/api/sessions/{session_id}/brief/cancel")
    def cancel_brief(session_id: str):
        with session_lock(session_id):
            state = fetch(session_id)
            state.update(brief_generation_id=None, brief_status="ready" if state.get("brief") else "idle",
                         brief_error=None)
            store.save(state)
            return {**brief_view(state, store.get_authority()), "cancelled": True,
                    "note": "진행 중인 모델 호출은 끝날 수 있지만 결과는 적용하지 않습니다. 외부 에이전트는 중단하지 않습니다."}

    @app.post("/api/intake", status_code=201)
    def intake(body: IntakeInput):
        try:
            state = create_import(body.transcript, body.title, body.source)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        state.update(created_at=now(), busy=False, stop_requested=False, last_error=None)
        if demo_mode and len(state.get("messages", [])) > 200:
            raise HTTPException(422, "체험 대화는 200개 메시지 이내로 입력해 주세요.")
        with creation_lock:
            if demo_mode and len(store.list()) >= 12:
                raise HTTPException(429, "체험 대화 한도에 도달했습니다. 내 체험을 초기화해 주세요.")
            store.save(state)
        return state

    @app.post("/api/sessions/{session_id}/events")
    def external_event(session_id: str, body: ExternalEvent):
        with session_lock(session_id):
            state = fetch(session_id)
            if state["mode"] != "import":
                raise HTTPException(409, "가져온 대화 세션에서만 외부 이벤트를 받을 수 있습니다.")
            append_external_event(state, body.model_dump())
            if demo_mode and len(state.get("messages", [])) > 200:
                raise HTTPException(429, "체험 메시지 한도에 도달했습니다. 새 대화를 만들거나 내 체험을 초기화해 주세요.")
            store.save(state)
            return state

    @app.get("/api/sessions/{session_id}/decisions")
    def decisions(session_id: str):
        state = fetch(session_id)
        return {"session_id": session_id, "decisions": state["decisions"],
                "next_actions": state.get("coordination", {}).get("next_actions", [])}

    def begin(session_id: str) -> dict:
        with session_lock(session_id):
            state = fetch(session_id)
            if demo_mode and state["mode"] == "codex":
                raise HTTPException(403, "공개 체험에서는 외부 모델을 실행할 수 없습니다.")
            if state["mode"] == "import":
                raise HTTPException(409, "가져온 대화는 새 에이전트 발화를 생성하지 않습니다. 이벤트 API로 후속 대화를 추가해 주세요.")
            if state.get("busy"):
                raise HTTPException(409, "이미 실행 중입니다.")
            if state["status"] == "waiting":
                raise HTTPException(409, "대기 중인 결정에 먼저 응답해 주세요.")
            if state["status"] in {"completed", "budget_exhausted"}:
                raise HTTPException(409, "완료되었거나 실행 예산에 도달했습니다.")
            state.update(busy=True, stop_requested=False, status="running", last_error=None)
            store.save(state)
            return state

    def execute(session_id: str, continuous: bool) -> dict:
        try:
            while True:
                with session_lock(session_id):
                    snapshot = fetch(session_id)
                    if snapshot.get("stop_requested"):
                        snapshot.update(status="stopped", busy=False)
                        store.save(snapshot)
                        return snapshot
                event = next_demo_event(snapshot) if snapshot["mode"] == "demo" else codex_event(snapshot)
                with session_lock(session_id):
                    state = fetch(session_id)
                    ingest_event(state, event)
                    state["validation"] = evaluate_state(state)
                    if state.get("stop_requested") and state["status"] == "running":
                        state["status"] = "stopped"
                    if state["status"] == "running" and state["detector"].get("intentional_human_wait"):
                        # A verified handoff awaiting a person needs no more generated reminders.
                        state["status"] = "stopped"
                    done = not continuous or state["status"] != "running" or state.get("stop_requested")
                    state["busy"] = not done
                    store.save(state)
                    if done:
                        return state
                # Make a scripted run observable and allow stop between events.
                if snapshot["mode"] == "demo":
                    time.sleep(0.12)
        except Exception as error:
            with session_lock(session_id):
                state = fetch(session_id)
                state.update(status="error", busy=False,
                             last_error=str(error) if isinstance(error, (ProviderError, ValueError)) else "실행 처리 중 오류가 발생했습니다.")
                store.save(state)
                return state

    @app.post("/api/sessions/{session_id}/step")
    def step(session_id: str):
        begin(session_id)
        return execute(session_id, continuous=False)

    @app.post("/api/sessions/{session_id}/run", status_code=202)
    def run(session_id: str):
        state = begin(session_id)
        workers.submit(execute, session_id, True)
        return state

    @app.post("/api/sessions/{session_id}/stop")
    def stop(session_id: str):
        with session_lock(session_id):
            state = fetch(session_id)
            state["stop_requested"] = True
            if not state.get("busy") and state["status"] == "running":
                state["status"] = "stopped"
            store.save(state)
            return state

    @app.post("/api/sessions/{session_id}/decisions")
    def decide(session_id: str, body: DecisionInput):
        with session_lock(session_id):
            state = fetch(session_id)
            if state.get("busy"):
                raise HTTPException(409, "실행이 멈춘 뒤 결정할 수 있습니다.")
            try:
                if state["mode"] == "import":
                    decide_import(state, body.request_id, body.choice, body.note)
                else:
                    apply_decision(state, body.request_id, body.choice, body.note)
            except ValueError as error:
                raise HTTPException(409, str(error)) from error
            if state["mode"] != "import":
                state["validation"] = evaluate_state(state)
            state["stop_requested"] = False
            store.save(state)
            return state

    @app.get("/api/sessions/{session_id}/graph")
    def graph(session_id: str):
        state = fetch(session_id)
        return conversation_graph(state) if state["mode"] == "import" else ontology_graph(state)

    @app.get("/api/sessions/{session_id}/export")
    def export(session_id: str, format: Literal["json", "markdown"] = "json"):
        state = fetch(session_id)
        extension = "json" if format == "json" else "md"
        content = json.dumps(state, ensure_ascii=False, indent=2) if format == "json" else session_markdown(state)
        return Response(content, media_type="application/json" if format == "json" else "text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="arbiter-{session_id}.{extension}"'})

    @app.get("/api/experiments")
    def experiments():
        path = ROOT / "experiments" / "results" / "latest" / "summary.json"
        if not path.exists():
            return {"available": False, "description": "아직 비교 실험 결과가 없습니다."}
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"available": True, **data}

    @app.get("/")
    def index():
        return FileResponse(ROOT / "frontend" / "landing.html")

    @app.get("/workspace")
    def workspace():
        return FileResponse(ROOT / "frontend" / "index.html")

    frontend = ROOT / "frontend"
    frontend.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=frontend), name="static")
    return app


@lru_cache(maxsize=1)
def default_app() -> FastAPI:
    # Importing create_app for visitor routing must not open a shared default DB.
    return create_app()


async def app(scope, receive, send):
    await default_app()(scope, receive, send)
