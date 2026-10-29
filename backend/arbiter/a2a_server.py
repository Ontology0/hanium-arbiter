"""Local A2A 1.0 analysis adapter (a2a-sdk 1.3); never executes Slack actions."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from urllib.parse import urlsplit

import httpx
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from a2a import types
from a2a.helpers.proto_helpers import new_data_part, new_task_from_user_message, new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.context import ServerCallContext
from a2a.server.events import EventQueue
from a2a.server.owner_resolver import resolve_user_scope
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import TaskStore, TaskUpdater
from a2a.utils.errors import InvalidParamsError, UnsupportedOperationError


ROOT = Path(__file__).resolve().parents[2]
TERMINAL = {types.TaskState.TASK_STATE_COMPLETED, types.TaskState.TASK_STATE_FAILED,
            types.TaskState.TASK_STATE_CANCELED, types.TaskState.TASK_STATE_REJECTED}


class LocalOriginGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "POST":
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            if (origin and urlsplit(origin).netloc != headers.get("host")) or headers.get("sec-fetch-site") == "cross-site":
                response = JSONResponse({"detail": "다른 웹사이트에서 보낸 로컬 분석 요청은 허용하지 않습니다."}, status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class SQLiteTaskStore(TaskStore):
    """Single-process local task persistence, scoped by tenant and SDK user."""

    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        with self.connection:
            self.connection.execute("CREATE TABLE IF NOT EXISTS tasks (owner TEXT, id TEXT, payload BLOB, PRIMARY KEY(owner,id))")
            self.connection.execute("CREATE TABLE IF NOT EXISTS bindings (owner TEXT, id TEXT, session_id TEXT, PRIMARY KEY(owner,id))")
        # A restarted adapter cannot resume a lost polling coroutine. Expose failure,
        # rather than leaving durable tasks marked as working indefinitely.
        with self.lock, self.connection:
            for owner, task_id, payload in self.connection.execute("SELECT owner,id,payload FROM tasks").fetchall():
                task = types.Task.FromString(payload)
                if task.status.state not in TERMINAL:
                    task.status.state = types.TaskState.TASK_STATE_FAILED
                    task.status.message.CopyFrom(new_text_message("분석 서비스가 재시작되어 결과 전달이 중단되었습니다. 새 분석을 요청하세요."))
                    task.status.timestamp.GetCurrentTime()
                    self.connection.execute("UPDATE tasks SET payload=? WHERE owner=? AND id=?", (task.SerializeToString(), owner, task_id))

    @staticmethod
    def owner(context: ServerCallContext) -> str:
        return json.dumps([context.tenant, resolve_user_scope(context)], ensure_ascii=False)

    async def save(self, task: types.Task, context: ServerCallContext) -> None:
        with self.lock, self.connection:
            self.connection.execute("INSERT OR REPLACE INTO tasks VALUES (?,?,?)", (self.owner(context), task.id, task.SerializeToString()))

    async def get(self, task_id: str, context: ServerCallContext) -> types.Task | None:
        with self.lock:
            row = self.connection.execute("SELECT payload FROM tasks WHERE owner=? AND id=?", (self.owner(context), task_id)).fetchone()
        return types.Task.FromString(row[0]) if row else None

    async def list(self, params: types.ListTasksRequest, context: ServerCallContext) -> types.ListTasksResponse:
        raise UnsupportedOperationError("이 로컬 어댑터는 SendMessage, GetTask, CancelTask만 지원합니다.")

    async def delete(self, task_id: str, context: ServerCallContext) -> None:
        with self.lock, self.connection:
            self.connection.execute("DELETE FROM tasks WHERE owner=? AND id=?", (self.owner(context), task_id))
            self.connection.execute("DELETE FROM bindings WHERE owner=? AND id=?", (self.owner(context), task_id))

    def bind(self, task_id: str, session_id: str, context: ServerCallContext) -> None:
        with self.lock, self.connection:
            self.connection.execute("INSERT OR REPLACE INTO bindings VALUES (?,?,?)", (self.owner(context), task_id, session_id))

    def session_id(self, task_id: str, context: ServerCallContext) -> str | None:
        with self.lock:
            row = self.connection.execute("SELECT session_id FROM bindings WHERE owner=? AND id=?", (self.owner(context), task_id)).fetchone()
        return row[0] if row else None

    def close(self) -> None:
        self.connection.close()


def _local_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("인증 없는 로컬 어댑터의 URL은 http://127.0.0.1:포트 형식이어야 합니다.")
    return value.rstrip("/")


class AnalysisExecutor(AgentExecutor):
    def __init__(self, client: httpx.AsyncClient, store: SQLiteTaskStore, api_url: str,
                 poll_interval: float = 0.5, analysis_timeout: float = 300):
        self.client, self.store, self.api_url = client, store, api_url
        self.poll_interval, self.analysis_timeout = poll_interval, analysis_timeout

    async def _json(self, method: str, path: str, **kwargs) -> dict:
        response = await self.client.request(method, self.api_url + path, **kwargs)
        if response.is_error:
            try:
                detail = response.json().get("detail", "로컬 분석 API 오류")
            except (ValueError, AttributeError):
                detail = "로컬 분석 API 오류"
            raise RuntimeError(f"{response.status_code}: {str(detail)[:300]}")
        return response.json()

    async def _cancel_brief(self, context: RequestContext) -> bool:
        session_id = self.store.session_id(context.task_id, context.call_context)
        if not session_id:
            return True
        try:
            await self._json("POST", f"/api/sessions/{session_id}/brief/cancel")
            return True
        except (httpx.HTTPError, RuntimeError, ValueError):
            return False

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        text = context.get_user_input().strip()
        if not text or len(text) > 40000:
            raise InvalidParamsError("분석할 대화 텍스트를 1~40,000자로 입력하세요.")
        if context.current_task is not None:
            raise UnsupportedOperationError("기존 작업에 메시지를 추가하지 않습니다. 새 분석 작업을 요청하세요.")
        source = context.metadata.get("source", "manual")
        title = context.metadata.get("title", "A2A로 요청한 협업 대화 분석")
        if not isinstance(source, str) or source not in {"slack", "pickle", "manual"} or not isinstance(title, str) or not 1 <= len(title.strip()) <= 150:
            raise InvalidParamsError("metadata.source는 slack/pickle/manual, title은 1~150자여야 합니다.")
        title = title.strip()
        task = new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work(new_text_message("대화의 근거와 인간 개입 지점을 분석합니다."))
        try:
            state = await self._json("POST", "/api/intake", json={"transcript": text, "title": title, "source": source})
            session_id = state["id"]
            self.store.bind(task.id, session_id, context.call_context)
            await self._json("POST", f"/api/sessions/{session_id}/brief")
            deadline = time.monotonic() + self.analysis_timeout
            while time.monotonic() < deadline:
                result = await self._json("GET", f"/api/sessions/{session_id}/brief")
                if result.get("status") == "error":
                    raise RuntimeError(result.get("error") or "브리핑 생성에 실패했습니다.")
                if result.get("status") == "ready" and result.get("available") and result.get("brief"):
                    if result.get("stale"):
                        raise RuntimeError("분석 중 원문이 변경되었습니다. 새 분석을 요청하세요.")
                    artifact = {"session_id": session_id, "dashboard_url": self.api_url + "/workspace",
                                "analysis_status": "completed", "execution_status": "not_verified",
                                "brief": result["brief"],
                                "scope": "대화 분석 완료. 사람의 결정·Slack 전송·외부 업무 실행을 의미하지 않습니다."}
                    await updater.add_artifact([new_data_part(artifact, "application/json")], name="coordination-analysis", last_chunk=True)
                    await updater.complete(new_text_message("대화 분석을 완료했습니다. 제안된 인간 개입은 대시보드에서 확인하세요."))
                    return
                await asyncio.sleep(self.poll_interval)
            await self._cancel_brief(context)
            raise RuntimeError("분석 제한 시간을 초과했습니다. 결과 전달을 중단했습니다.")
        except asyncio.CancelledError:
            # The SDK calls cancel() after stopping this coroutine. It performs the
            # backend invalidation and emits the terminal CANCELED event.
            raise
        except (httpx.HTTPError, RuntimeError, ValueError, KeyError) as error:
            await updater.failed(new_text_message(f"분석 실패: {str(error)[:400]}"))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        invalidated = await self._cancel_brief(context)
        message = "분석 결과 전달을 취소했습니다. 외부 에이전트와 Slack 작업은 중단하지 않습니다."
        if not invalidated:
            message += " 로컬 브리핑 취소 API 응답은 확인하지 못했습니다."
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel(new_text_message(message))


def agent_card(public_url: str) -> types.AgentCard:
    return types.AgentCard(
        name="Arbiter HITL Conversation Analyst",
        description="에이전트 협업 대화에서 합의·쟁점·결정 책임과 인간 개입 지점을 근거와 함께 분석하는 로컬 서비스. 외부 업무를 실행하지 않습니다.",
        supported_interfaces=[types.AgentInterface(url=public_url + "/", protocol_binding="JSONRPC", protocol_version="1.0")],
        version="0.1.0", capabilities=types.AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain"], default_output_modes=["application/json", "text/plain"],
        skills=[types.AgentSkill(id="hitl-conversation-analysis", name="협업 대화 및 HITL 분석",
                                description="대화 입력 → 온톨로지 상태 추출과 인간 개입 후보 검출 → 인용 근거가 있는 브리핑.",
                                tags=["HITL", "ontology", "coordination", "Slack"],
                                examples=["agent-a: B의 검토를 기다립니다.\nagent-b: A가 먼저 결정해 주세요."])],
    )


def create_app(*, api_url: str = "http://127.0.0.1:8787", public_url: str = "http://127.0.0.1:8789",
               db_path: str | Path | None = None, poll_interval: float = 0.5,
               analysis_timeout: float = 300) -> Starlette:
    api_url, public_url = _local_url(api_url), _local_url(public_url)
    if poll_interval <= 0 or analysis_timeout <= 0:
        raise ValueError("poll_interval과 analysis_timeout은 양수여야 합니다.")
    store = SQLiteTaskStore(db_path or ROOT / ".runtime" / "a2a.sqlite3")
    client = httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False)
    card = agent_card(public_url)
    executor = AnalysisExecutor(client, store, api_url, poll_interval, analysis_timeout)
    handler = DefaultRequestHandler(executor, store, card)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await handler.aclose()
        await client.aclose()
        store.close()

    app = Starlette(routes=[*create_agent_card_routes(card), *create_jsonrpc_routes(handler, "/")], lifespan=lifespan)

    app.add_middleware(LocalOriginGuard)
    app.state.task_store = store
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8789)
    parser.add_argument("--api-url", default=os.environ.get("ARBITER_API_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--db", default=os.environ.get("ARBITER_A2A_DB", str(ROOT / ".runtime" / "a2a.sqlite3")))
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(api_url=args.api_url, public_url=f"http://127.0.0.1:{args.port}", db_path=args.db,
                           analysis_timeout=args.timeout), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
