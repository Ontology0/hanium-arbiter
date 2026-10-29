import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import time

import httpx
import pytest

from arbiter.deployment import COOKIE_NAME, DemoConfig, create_deployment_app
from arbiter.demo_seed import ACTION, RECORDED_SOURCE, SCOPE
from arbiter.briefing import authority_digest, conversation_digest


@asynccontextmanager
async def sandbox(tmp_path, **config):
    app = create_deployment_app(tmp_path, config=DemoConfig(**config))
    await app.startup()
    try:
        yield app
    finally:
        await app.shutdown()


def client(app, **kwargs):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver", **kwargs)


async def seeded(client):
    response = await client.get("/api/sessions")
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    return response.json()[0]["id"]


def test_health_creates_no_tenant_and_import_does_not_create_storage(tmp_path):
    async def run():
        app = create_deployment_app(tmp_path / "untouched")
        async with client(app) as c:
            response = await c.get("/api/health")
        assert response.status_code == 200
        assert "set-cookie" not in response.headers
        assert not app.data_dir.exists()
        async with sandbox(tmp_path / "started") as app:
            async with client(app) as c:
                await c.get("/api/health")
            assert app.registry.execute("SELECT COUNT(*) FROM visitors").fetchone()[0] == 0
            assert not app.residents
    asyncio.run(run())


def test_two_visitors_have_isolated_approvals_and_session_access(tmp_path):
    async def run():
        async with sandbox(tmp_path) as app:
            async with client(app) as a, client(app) as b:
                sid_a, sid_b = await seeded(a), await seeded(b)
                assert sid_a != sid_b
                assert (await a.get(f"/api/sessions/{sid_b}")).status_code == 404
                assert (await b.get(f"/api/sessions/{sid_a}/export")).status_code == 404
                first = (await a.get(f"/api/sessions/{sid_a}/brief")).json()
                assert not first["stale"]
                assert first["brief"]["authority_checks"][0]["status"] == "cross_owner_conflict"
                registry = (await a.get("/api/authority")).json()
                response = await a.post("/api/authority/precedence", json={
                    "scope": SCOPE, "action": ACTION, "agents": ["Review Agent", "Release Agent"],
                    "approved_by": ["Owner A", "Owner B"], "expected_revision": registry["registry_revision"]})
                assert response.status_code == 201, response.text
                after = (await a.get(f"/api/sessions/{sid_a}/brief")).json()["brief"]
                assert after["authority_checks"][0]["status"] == "authorized"
                assert after["authority_checks"][0]["decision_owner"] == "Review Agent"
                assert after["intervention_points"] == []
                advice = (await a.get(f"/api/sessions/{sid_a}/next-action")).json()
                assert advice["action"] == "follow_authority"
                assert advice["decision_owner"] == "Review Agent"
                other = (await b.get(f"/api/sessions/{sid_b}/brief")).json()["brief"]
                assert other["authority_checks"][0]["status"] == "cross_owner_conflict"
                assert (await b.get("/api/authority")).json()["precedence"] == []
                assert after["execution_status"] == "not_verified"
    asyncio.run(run())


def test_recorded_seed_citations_are_exact_and_never_call_a_model(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("public demo must not invoke a model")
    monkeypatch.setattr("arbiter.providers.run_codex_json", forbidden)
    monkeypatch.setattr("arbiter.briefing.run_codex_json", forbidden)
    monkeypatch.setattr("arbiter.app.codex_event", forbidden)
    monkeypatch.setattr("arbiter.app.build_brief", forbidden)

    async def run():
        async with sandbox(tmp_path) as app:
            async with client(app) as c:
                sid = await seeded(c)
                state = (await c.get(f"/api/sessions/{sid}")).json()
                brief = state["brief"]
                assert state["demo"]["live_model_called"] is False
                assert brief["execution_mode"] == "recorded_sample"
                assert brief["usage_source"] == "recorded_measurement"
                for metadata in (state["demo"], brief):
                    assert metadata["translated_replay"] is True
                    assert metadata["source_language"] == "ko"
                    assert metadata["language"] == "en"
                    assert metadata["source_path"] == RECORDED_SOURCE
                    assert "translated replay" in metadata["notice"]
                original = json.loads((Path(__file__).resolve().parents[1] / RECORDED_SOURCE).read_text())
                for key in ("input_tokens", "output_tokens", "duration_seconds"):
                    assert brief[key] == original["brief"][key]
                assert brief["source_digest"] == conversation_digest(state)
                assert brief["source_digest"] != original["brief"]["source_digest"]
                registry = (await c.get("/api/authority")).json()
                assert brief["authority_digest"] == authority_digest({key: registry[key] for key in ("grants", "precedence")})
                assert {grant["agent"] for grant in registry["grants"]} == {"Release Agent", "Review Agent"}
                assert {grant["owner"] for grant in registry["grants"]} == {"Owner A", "Owner B"}
                assert {message["agent"] for message in state["messages"]} == {"Release Agent", "Review Agent"}
                assert state["brief_view"]["conversation_stale"] is False
                assert state["brief_view"]["authority_stale"] is False
                assert state["metrics"]["measured_calls"] == 0
                messages = {m["id"]: m["content"] for m in state["messages"]}
                for group in ("open_questions", "decision_points", "next_actions", "intervention_points"):
                    for item in brief[group]:
                        for evidence in item["evidence"]:
                            assert evidence["quote"] in messages[evidence["message_id"]]
                assert (await c.post(f"/api/sessions/{sid}/brief")).status_code == 403
                assert (await c.post("/api/sessions", json={"scenario_id": "healthy-progress", "mode": "codex"})).status_code == 403
                assert (await c.post("/api/slack/events", json={})).status_code == 403
                config = (await c.get("/api/config")).json()
                assert config["deployment"]["isolated"] is True
                assert config["deployment"]["live_model_available"] is False
    asyncio.run(run())


@pytest.mark.parametrize("forgery", ["../outside.sqlite3", "../../.runtime/arbiter.sqlite3", "f" * 48 + "." + "0" * 64, "unknown"])
def test_untrusted_cookie_cannot_select_a_path_or_other_visitor(tmp_path, forgery):
    async def run():
        async with sandbox(tmp_path) as app:
            async with client(app) as a, client(app, cookies={COOKIE_NAME: forgery}) as b:
                sid = await seeded(a)
                response = await b.get(f"/api/sessions/{sid}")
                assert response.status_code == 404
                assert "set-cookie" in response.headers
                assert len(app.residents) == 2
                assert all(len(p.stem) == 48 for p in (tmp_path / "visitors").glob("*.sqlite3"))
    asyncio.run(run())


def test_cookie_signature_cannot_be_reused_for_a_different_identifier(tmp_path):
    async def run():
        async with sandbox(tmp_path) as app:
            async with client(app) as a, client(app) as b:
                sid = await seeded(a)
                await seeded(b)
                a_id, _ = a.cookies[COOKIE_NAME].split(".")
                _, b_signature = b.cookies[COOKIE_NAME].split(".")
                b.cookies.clear()
                b.cookies.set(COOKIE_NAME, a_id + "." + b_signature)
                assert (await b.get(f"/api/sessions/{sid}")).status_code == 404
    asyncio.run(run())


def test_cookie_and_data_survive_restart(tmp_path):
    async def run():
        async with sandbox(tmp_path) as app:
            async with client(app) as c:
                sid = await seeded(c)
                cookie = c.cookies[COOKIE_NAME]
                response = await c.post("/api/authority/grants/demo-grant-a/revoke")
                assert response.status_code == 200
        async with sandbox(tmp_path) as app:
            async with client(app, cookies={COOKIE_NAME: cookie}) as c:
                assert (await c.get(f"/api/sessions/{sid}")).status_code == 200
                assert (await c.get("/api/authority")).json()["grants"][0]["revoked"] is True
                assert len((await c.get("/api/sessions")).json()) == 1
    asyncio.run(run())


def test_reset_removes_only_own_sandbox_and_rotates_cookie(tmp_path):
    async def run():
        async with sandbox(tmp_path) as app:
            async with client(app) as a, client(app) as b:
                sid_a, sid_b = await seeded(a), await seeded(b)
                old_cookie = a.cookies[COOKIE_NAME]
                response = await a.post("/api/demo/reset")
                assert response.status_code == 200
                assert response.json()["identity_authenticated"] is False
                assert a.cookies[COOKIE_NAME] != old_cookie
                assert (await a.get(f"/api/sessions/{sid_a}")).status_code == 404
                assert (await b.get(f"/api/sessions/{sid_b}")).status_code == 200
                assert len((await a.get("/api/sessions")).json()) == 1
                assert app.registry.execute("SELECT COUNT(*) FROM visitors").fetchone()[0] == 2
                assert not app._db_path(old_cookie.split(".")[0]).exists()
    asyncio.run(run())


def test_ttl_cleanup_defers_active_work_then_removes_it(tmp_path):
    async def run():
        async with sandbox(tmp_path) as app:
            async with client(app) as c:
                sid = await seeded(c)
                visitor_id = c.cookies[COOKIE_NAME].split(".")[0]
                resident = app.residents[visitor_id]
                state = resident.app.state.store.get(sid)
                state["busy"] = True
                resident.app.state.store.save(state)
                app.registry.execute("UPDATE visitors SET created_at = ?", (time.time() - 90000,))
                app.registry.commit()
                async with app.lock:
                    await app._cleanup()
                assert app._db_path(visitor_id).exists()
                state["busy"] = False
                resident.app.state.store.save(state)
                async with app.lock:
                    await app._cleanup()
                assert not app._db_path(visitor_id).exists()
                assert resident.app.state.workers._shutdown
                assert visitor_id not in app.residents
    asyncio.run(run())


def test_resident_lru_preserves_database_and_never_evicts_busy_work(tmp_path):
    async def run():
        async with sandbox(tmp_path, max_resident=1) as app:
            async with client(app) as a, client(app) as b:
                sid = await seeded(a)
                visitor_id = a.cookies[COOKIE_NAME].split(".")[0]
                resident = app.residents[visitor_id]
                resident.references += 1
                assert (await b.get("/api/sessions")).status_code == 503
                assert not resident.app.state.workers._shutdown
                resident.references -= 1
                await seeded(b)
                assert resident.app.state.workers._shutdown
                assert app._db_path(visitor_id).exists()
                assert (await a.get(f"/api/sessions/{sid}")).status_code == 200
    asyncio.run(run())


def test_body_limits_and_cross_origin_fail_before_tenant_creation(tmp_path):
    async def run():
        async with sandbox(tmp_path, body_limit=32) as app:
            async with client(app) as c:
                assert (await c.post("/api/intake", content=b"x" * 33)).status_code == 413
                async def chunks():
                    yield b"x" * 20
                    yield b"x" * 20
                assert (await c.post("/api/intake", content=chunks())).status_code == 413
                assert (await c.post("/api/demo/reset", headers={"Origin": "https://other.example"})).status_code == 403
                assert (await c.post("/api/demo/reset", headers={"Sec-Fetch-Site": "cross-site"})).status_code == 403
                assert app.registry.execute("SELECT COUNT(*) FROM visitors").fetchone()[0] == 0
    asyncio.run(run())


def test_body_timeout_does_not_allocate_a_tenant(tmp_path, monkeypatch):
    monkeypatch.setattr("arbiter.deployment.BODY_TIMEOUT_SECONDS", 0.01)
    async def run():
        async with sandbox(tmp_path) as app:
            async with client(app) as c:
                async def slow():
                    yield b"x"
                    await asyncio.sleep(1)
                assert (await c.post("/api/intake", content=slow())).status_code == 408
                assert app.registry.execute("SELECT COUNT(*) FROM visitors").fetchone()[0] == 0
    asyncio.run(run())


def test_cookie_security_and_private_api_cache_headers(tmp_path):
    async def run():
        async with sandbox(tmp_path, secure_cookie=True) as app:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://testserver") as c:
                response = await c.get("/api/sessions")
                cookie = response.headers["set-cookie"]
                assert all(value in cookie for value in ("HttpOnly", "SameSite=Lax", "Secure", "Path=/"))
                assert "no-store" in response.headers["cache-control"]
                assert "private" in response.headers["cache-control"]
                assert "Cookie" in response.headers["vary"]
                sid = response.json()[0]["id"]
                response = await c.get(f"/api/sessions/{sid}/export")
                assert response.status_code == 200
                assert "no-store" in response.headers["cache-control"]
    asyncio.run(run())


def test_capacity_rate_and_disk_limits_allow_reset(tmp_path):
    async def run():
        async with sandbox(tmp_path / "capacity", max_visitors=1) as app:
            async with client(app) as a, client(app) as b:
                await seeded(a)
                assert (await b.get("/api/sessions")).status_code == 503
                assert (await a.post("/api/demo/reset")).status_code == 200
        async with sandbox(tmp_path / "rate", requests_per_minute=1) as app:
            async with client(app) as c:
                await seeded(c)
                assert (await c.get("/api/sessions")).status_code == 429
        async with sandbox(tmp_path / "disk", visitor_bytes=1) as app:
            async with client(app) as c:
                await seeded(c)
                assert (await c.post("/api/authority/grants/demo-grant-a/revoke")).status_code == 429
                assert (await c.post("/api/demo/reset")).status_code == 200
        async with sandbox(tmp_path / "newrate", new_visitors_per_ip_minute=1) as app:
            async with client(app) as a, client(app) as b:
                await seeded(a)
                assert (await b.get("/api/sessions")).status_code == 429
    asyncio.run(run())


def test_only_one_worker_can_own_a_volume_and_limits_are_bounded(tmp_path):
    async def run():
        async with sandbox(tmp_path):
            duplicate = create_deployment_app(tmp_path)
            with pytest.raises(RuntimeError, match="one worker"):
                await duplicate.startup()
            await duplicate.shutdown()
    asyncio.run(run())
    with pytest.raises(ValueError):
        DemoConfig(max_visitors=0)
    with pytest.raises(ValueError):
        DemoConfig(body_limit=10 * 1024 * 1024)
