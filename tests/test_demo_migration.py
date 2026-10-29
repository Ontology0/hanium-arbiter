"""Persisted stock demo translations must never create or invalidate authority."""
import asyncio
from copy import deepcopy

import httpx
import pytest

from arbiter.authority import evaluate_authority, grant_revision
from arbiter.briefing import authority_digest, brief_view, conversation_digest
from arbiter.conversations import append_external_event
from arbiter.demo_seed import (ACTION, LEGACY_DISPLAY_ALIASES, LEGACY_MESSAGES,
                               MESSAGES, SCOPE, migrate_legacy_demo, seed_demo)
from arbiter.deployment import create_deployment_app
from arbiter.storage import SessionStore


def legacy_store(path):
    """Reconstruct the persisted v1 sample without depending on a git checkout."""
    store = SessionStore(path)
    sid = seed_demo(store)
    state, registry = store.get(sid), store.get_authority()
    agents = {"Release Agent": "배포봇A", "Review Agent": "검토봇B"}
    owners = {"Owner A": "시연 소유자A", "Owner B": "시연 소유자B"}
    for grant in registry["grants"]:
        grant["agent"], grant["owner"] = agents[grant["agent"]], owners[grant["owner"]]
    for i, message in enumerate(state["messages"]):
        message.update(agent=LEGACY_MESSAGES[i][0], content=LEGACY_MESSAGES[i][1])
        state["evidence"][i]["summary"] = LEGACY_MESSAGES[i][1]
    state["title"] = "공개 합성 예시 · 서로 다른 소유자의 승인권 충돌"
    state["description"] = "제공된 대화에 근거한 확인 요청·대기 관계 점검"
    state["task"]["description"] = "담당자와 다음 확인 행동을 명확히 한다."
    state["validation"]["reason"] = "실제 외부 작업의 완료는 대화 가져오기만으로 판정하지 않습니다."
    state["coordination"]["summary"] = "기록된 결정 대상과 두 소유자의 위임을 대조하는 합성 예시"
    state["coordination"]["analyzer"] = "기록된 모델 추출 + 현재 범위별 권한 규칙"
    state["detector"]["reason"] = "2개 발화 주체, 확인 약속 0건, 대기 관계 0건을 추출했습니다. 다른 채널에서 이루어진 요청·응답 여부는 알 수 없습니다."
    state["demo"]["notice"] = "익명 합성 대화와 과거 모델 분석의 재생 예시입니다. 방문자 쿠키는 소유자의 신원을 인증하지 않으며, 외부 작업은 실행하지 않습니다."
    state["demo"]["seed_notice"] = "권한 충돌 한 건에 초점을 맞춘 전용 예시입니다. 별도의 일반 표현 기반 질문은 포함하지 않았습니다."
    brief = state["brief"]
    brief["overview"] = "결제 서비스 1.2 배포 승인권에 이견이 있으며, 검토봇B는 우선권 결정까지 실행을 보류하고 있습니다."
    brief["notice"] = "과거 단일 합성 사례의 실제 Codex 분석 기록입니다. 이 방문에서 모델을 호출하거나 토큰을 사용하지 않았습니다."
    brief["decision_points"][0]["text"] = "결제 서비스 1.2 배포 승인이 미해결 상태이며, 승인권에 대한 이견이 제기됐습니다."
    brief["decision_points"][0]["agents"] = ["배포봇A", "검토봇B"]
    brief["open_questions"][0]["text"] = "배포봇A의 승인 결정 주장과 검토봇B의 소유자 승인 요구 사이에서 최종 승인 기준이 정해지지 않았습니다."
    brief["next_actions"][0]["text"] = "검토봇B는 우선권이 정해질 때까지 실행을 보류하겠다고 밝혔습니다."
    for group in ("agreements", "open_questions", "decision_points", "next_actions", "intervention_points"):
        for item in brief[group]:
            for evidence in item["evidence"]:
                evidence["quote"] = LEGACY_MESSAGES[int(evidence["message_id"][1:]) - 1][1]
    for metadata in (state["demo"], brief):
        for key in ("translated_replay", "source_language", "language"):
            metadata.pop(key, None)
    brief["source_digest"] = conversation_digest(state)
    brief["authority_digest"] = authority_digest(registry)
    store.save_authority(registry)
    store.save(state)
    return store, sid


def registry_bytes(store):
    with store.connect() as db:
        return db.execute("SELECT value FROM configuration WHERE key='authority'").fetchone()[0]


def test_stock_translation_is_exact_fresh_and_idempotent_without_model(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Migrating a recorded sample must not call a model")
    monkeypatch.setattr("arbiter.briefing.run_codex_json", forbidden)
    store, sid = legacy_store(tmp_path / "legacy.sqlite3")
    before, raw_registry = store.get(sid), registry_bytes(store)
    assert migrate_legacy_demo(store) == 1
    after = store.get(sid)
    assert after["id"] == sid
    assert after["title"] == "Public sample · Approval conflict between owners"
    assert after["demo"]["display_aliases"] == LEGACY_DISPLAY_ALIASES
    assert after["brief"]["language"] == after["demo"]["language"] == "en"
    assert after["brief"]["source_language"] == "ko"
    assert [m["content"] for m in after["messages"]] == [m[1] for m in MESSAGES]
    assert [m["agent"] for m in after["messages"]] == [m[0] for m in LEGACY_MESSAGES]
    assert registry_bytes(store) == raw_registry
    assert after["brief"]["authority_digest"] == before["brief"]["authority_digest"]
    assert after["brief"]["source_digest"] == conversation_digest(after)
    for group in ("open_questions", "decision_points", "next_actions", "intervention_points"):
        for item in after["brief"][group]:
            for citation in item["evidence"]:
                assert citation["quote"] in after["messages"][int(citation["message_id"][1:]) - 1]["content"]
    for key in ("input_tokens", "output_tokens", "duration_seconds"):
        assert after["brief"][key] == before["brief"][key]
    assert migrate_legacy_demo(store) == 0
    assert store.get(sid) == after


@pytest.mark.parametrize("valid_approval", [True, False])
def test_valid_and_stale_priorities_and_custom_grants_are_preserved(tmp_path, valid_approval):
    store, sid = legacy_store(tmp_path / "authority.sqlite3")
    registry = store.get_authority()
    registry["grants"].append({"id": "custom", "agent": "My Agent", "owner": "개인 소유자",
                               "scope": "custom-work", "action": "review", "issuer": "local-human"})
    registry["precedence"] = [{"scope": SCOPE, "action": ACTION, "issuer": "local-human",
                               "agents": ["검토봇B", "배포봇A"], "approved_by": ["시연 소유자A", "시연 소유자B"],
                               "grant_revision": grant_revision(registry, SCOPE, ACTION) if valid_approval else "0" * 64,
                               "source": "local_operator_record", "note": "이 승인 기록 보존"}]
    store.save_authority(registry)
    before, raw_registry = evaluate_authority(registry, SCOPE, ACTION), registry_bytes(store)
    assert before["status"] == ("authorized" if valid_approval else "cross_owner_conflict")
    migrate_legacy_demo(store)
    assert registry_bytes(store) == raw_registry
    assert evaluate_authority(store.get_authority(), SCOPE, ACTION) == before
    current = brief_view(store.get(sid), store.get_authority())
    assert current["brief"]["authority_checks"][0]["status"] == before["status"]
    assert current["brief"]["authority_checks"][0]["decision_owner"] == before["decision_owner"]


def test_added_messages_custom_text_and_human_history_stay_unchanged_and_stale(tmp_path):
    store, sid = legacy_store(tmp_path / "extended.sqlite3")
    state = store.get(sid)
    append_external_event(state, {"event_id": "user-event", "agent": "배포봇A", "content": "제가 직접 추가한 문장 보존"})
    state["decisions"].append({"id": "human-history", "choice": "custom", "note": "원래 승인 메모"})
    state["title"] = "사용자가 바꾼 제목"
    state["task"]["description"] = "사용자 설명"
    state["requests"].append({"id": "custom-request", "status": "pending", "question": "보존할 질문"})
    store.save(state)
    before = deepcopy(state)
    assert brief_view(state, store.get_authority())["conversation_stale"] is True
    migrate_legacy_demo(store)
    after = store.get(sid)
    for key in ("title", "task", "decisions", "requests", "metrics"):
        assert after[key] == before[key]
    assert {key: value for key, value in after["coordination"].items() if key != "analyzer"} == {
        key: value for key, value in before["coordination"].items() if key != "analyzer"}
    assert after["messages"][4:] == before["messages"][4:]
    assert after["brief"]["source_digest"] == before["brief"]["source_digest"]
    assert brief_view(after, store.get_authority())["conversation_stale"] is True


@pytest.mark.parametrize("change", ["edited", "deleted", "not-demo", "different-source"])
def test_non_stock_or_edited_conversations_are_not_rewritten(tmp_path, change):
    store, sid = legacy_store(tmp_path / "custom.sqlite3")
    state = store.get(sid)
    if change == "edited":
        state["messages"][0]["content"] = "A user edited the original message"
    elif change == "deleted":
        state["messages"][0]["deleted"] = True
    elif change == "not-demo":
        state["demo"]["synthetic"] = False
    else:
        state["demo"]["source_path"] = "custom.json"
    store.save(state)
    assert migrate_legacy_demo(store) == 0
    assert store.get(sid) == state


def test_persisted_visitor_load_migrates_before_session_list_without_reset(tmp_path):
    async def run():
        data = tmp_path / "visitors"
        app = create_deployment_app(data)
        await app.startup()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
                initial = (await client.get("/api/sessions")).json()[0]["id"]
                cookies = httpx.Cookies(client.cookies)
                visitor_id = next(iter(app.residents))
                store = app.residents[visitor_id].app.state.store
                old_store, old_id = legacy_store(tmp_path / "fixture.sqlite3")
                legacy = old_store.get(old_id)
                legacy["id"] = initial
                store.save(legacy)
                store.save_authority(old_store.get_authority())
                registry = registry_bytes(store)
        finally:
            await app.shutdown()
        restarted = create_deployment_app(data)
        await restarted.startup()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(restarted), base_url="http://testserver", cookies=cookies) as client:
                response = await client.get("/api/sessions")
                assert response.status_code == 200
                assert response.json()[0]["id"] == initial
                assert response.json()[0]["title"] == "Public sample · Approval conflict between owners"
                assert "set-cookie" not in response.headers
                state = (await client.get(f"/api/sessions/{initial}")).json()
                assert state["demo"]["display_aliases"] == LEGACY_DISPLAY_ALIASES
                authority = (await client.get("/api/authority")).json()
                assert authority["display_aliases"] == LEGACY_DISPLAY_ALIASES
                assert authority["grants"][0]["agent"] == "배포봇A"
                assert registry_bytes(restarted.residents[visitor_id].app.state.store) == registry
                assert restarted.registry.execute("SELECT COUNT(*) FROM visitors").fetchone()[0] == 1
        finally:
            await restarted.shutdown()
    asyncio.run(run())
