"""Official A2A SDK over real local HTTP; briefing responses are controlled fakes."""

import asyncio
from contextlib import asynccontextmanager
import socket
import uuid

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from a2a import types
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.helpers.proto_helpers import get_data_parts, new_text_message
from a2a.server.context import ServerCallContext

from arbiter.a2a_server import SQLiteTaskStore, create_app


@asynccontextmanager
async def serve(app, port=None):
    sock = socket.socket()
    sock.bind(("127.0.0.1", port or 0))
    sock.listen()
    address = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(100):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.01)
        assert server.started
        yield address
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        sock.close()


class FakeBriefing:
    """No model, Codex CLI, Slack, or human participant is invoked."""

    def __init__(self, mode="ready"):
        self.mode, self.intakes, self.cancelled, self.started = mode, [], [], []
        self.app = FastAPI()

        @self.app.post("/api/intake")
        async def intake(body: dict):
            self.intakes.append(body)
            return {"id": "test-session"}

        @self.app.post("/api/sessions/{session_id}/brief")
        async def start(session_id: str):
            self.started.append(session_id)
            return {"status": "generating", "available": False}

        @self.app.get("/api/sessions/{session_id}/brief")
        async def brief(session_id: str):
            if self.mode == "ready":
                return {"status": "ready", "available": True, "stale": False,
                        "brief": {"summary": "테스트용 모의 분석", "detector": {"reason": "authority_gap"},
                                  "citations": ["msg-1"]}}
            if self.mode == "error":
                return {"status": "error", "available": False, "error": "테스트 분석 실패"}
            return {"status": "generating", "available": False}

        @self.app.post("/api/sessions/{session_id}/brief/cancel")
        async def cancel(session_id: str):
            self.cancelled.append(session_id)
            return {"cancelled": True}


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(text="agent-a: B의 검토를 기다립니다.\nagent-b: A가 먼저 결정해 주세요."):
    return types.SendMessageRequest(message=new_text_message(text, role=types.Role.ROLE_USER),
                                    configuration=types.SendMessageConfiguration(return_immediately=True))


async def connect(http, base):
    card = await A2ACardResolver(http, base).get_agent_card()
    assert card.name == "Arbiter HITL Conversation Analyst"
    assert not card.capabilities.streaming and not card.capabilities.push_notifications
    assert card.supported_interfaces[0].protocol_version == "1.0"
    return ClientFactory(ClientConfig(streaming=False, polling=True, httpx_client=http)).create(card)


async def submit(client, req=None):
    responses = [response async for response in client.send_message(req or request())]
    tasks = [response.task for response in responses if response.HasField("task")]
    assert tasks
    return tasks[-1]


async def terminal(client, task_id):
    for _ in range(100):
        task = await client.get_task(types.GetTaskRequest(id=task_id))
        if task.status.state in {3, 4, 5, 7}:
            return task
        await asyncio.sleep(0.02)
    pytest.fail("A2A task did not reach a terminal state")


def test_official_client_discovers_sends_gets_analysis_and_persistence(tmp_path):
    async def run():
        fake = FakeBriefing()
        db = tmp_path / "tasks.sqlite3"
        async with serve(fake.app) as backend:
            port = free_port()
            app = create_app(api_url=backend, public_url=f"http://127.0.0.1:{port}", db_path=db, poll_interval=0.01)
            async with serve(app, port) as base, httpx.AsyncClient(timeout=5, trust_env=False) as http:
                client = await connect(http, base)
                task = await terminal(client, (await submit(client)).id)
                assert task.status.state == types.TaskState.TASK_STATE_COMPLETED
                data = get_data_parts(task.artifacts[0].parts)[0]
                assert data["execution_status"] == "not_verified"
                assert data["brief"]["detector"]["reason"] == "authority_gap"
                assert data["brief"]["citations"] == ["msg-1"]
                assert fake.intakes[0]["source"] == "manual"
                assert fake.started == ["test-session"]
                task_id = task.id
        # Durable protobuf task and artifact survive a fresh store instance.
        reopened = SQLiteTaskStore(db)
        saved = await reopened.get(task_id, ServerCallContext())
        assert saved.status.state == types.TaskState.TASK_STATE_COMPLETED
        assert len(saved.artifacts) == 1
        reopened.close()
    asyncio.run(run())


def test_cancel_invalidates_local_brief_and_prevents_late_artifact(tmp_path):
    async def run():
        fake = FakeBriefing("pending")
        async with serve(fake.app) as backend:
            port = free_port()
            app = create_app(api_url=backend, public_url=f"http://127.0.0.1:{port}", db_path=tmp_path / "tasks.sqlite3", poll_interval=0.01)
            async with serve(app, port) as base, httpx.AsyncClient(timeout=5, trust_env=False) as http:
                client = await connect(http, base)
                task = await submit(client)
                for _ in range(100):
                    if fake.started:
                        break
                    await asyncio.sleep(0.01)
                assert fake.started
                cancelled = await client.cancel_task(types.CancelTaskRequest(id=task.id))
                assert cancelled.status.state == types.TaskState.TASK_STATE_CANCELED
                assert fake.cancelled == ["test-session"]
                fake.mode = "ready"
                await asyncio.sleep(0.05)
                final = await client.get_task(types.GetTaskRequest(id=task.id))
                assert final.status.state == types.TaskState.TASK_STATE_CANCELED
                assert not final.artifacts
    asyncio.run(run())


def test_empty_input_is_protocol_error_without_backend_intake(tmp_path):
    async def run():
        fake = FakeBriefing()
        async with serve(fake.app) as backend:
            port = free_port()
            app = create_app(api_url=backend, public_url=f"http://127.0.0.1:{port}", db_path=tmp_path / "tasks.sqlite3")
            async with serve(app, port) as base, httpx.AsyncClient(timeout=5, trust_env=False) as http:
                client = await connect(http, base)
                with pytest.raises(Exception, match="40,000|Invalid"):
                    await submit(client, request("   "))
                assert not fake.intakes
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["error", "pending"])
def test_backend_failure_and_deadline_are_failed_tasks(tmp_path, mode):
    async def run():
        fake = FakeBriefing(mode)
        async with serve(fake.app) as backend:
            port = free_port()
            app = create_app(api_url=backend, public_url=f"http://127.0.0.1:{port}", db_path=tmp_path / "tasks.sqlite3",
                             poll_interval=0.01, analysis_timeout=0.05)
            async with serve(app, port) as base, httpx.AsyncClient(timeout=5, trust_env=False) as http:
                client = await connect(http, base)
                task = await terminal(client, (await submit(client)).id)
                assert task.status.state == types.TaskState.TASK_STATE_FAILED
                assert not task.artifacts
                if mode == "pending":
                    assert fake.cancelled == ["test-session"]
    asyncio.run(run())


def test_restart_marks_unfinished_task_failed_and_preserves_scope(tmp_path):
    async def run():
        path = tmp_path / "tasks.sqlite3"
        context = ServerCallContext(tenant="workspace-a")
        store = SQLiteTaskStore(path)
        task = types.Task(id=str(uuid.uuid4()), context_id="test-context", status=types.TaskStatus(state=types.TaskState.TASK_STATE_WORKING))
        await store.save(task, context)
        store.close()
        reopened = SQLiteTaskStore(path)
        assert await reopened.get(task.id, ServerCallContext(tenant="workspace-b")) is None
        assert (await reopened.get(task.id, context)).status.state == types.TaskState.TASK_STATE_FAILED
        reopened.close()
    asyncio.run(run())
