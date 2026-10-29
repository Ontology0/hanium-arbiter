"""Anonymous, explicitly constructed public demo; never calls a model/provider.

The conversation and briefing are an English translation of the Korean synthetic
integration smoke in experiments/results/briefing-smoke/attempt-2.json. Recorded
usage belongs to that original call, not this translated replay. This is neither
a new inference nor evidence of an external release. No private database is read.
"""
from __future__ import annotations

from copy import deepcopy

from .briefing import apply_authority_rules, authority_digest, conversation_digest
from .conversations import create_import
from .storage import SessionStore, now


MESSAGES = (
    ("Release Agent", "I believe I should decide whether to approve the payment service 1.2 release."),
    ("Review Agent", "We must not deploy before my owner approves."),
    ("Release Agent", "Our owners disagree. We need to decide who has final approval authority for this release."),
    ("Review Agent", "I will not proceed until priority is established."),
)
SCOPE = "payment-release-1.2"
ACTION = "approve"
RECORDED_SOURCE = "experiments/results/briefing-smoke/attempt-2.json"
LEGACY_MESSAGES = (
    ("배포봇A", "결제 서비스 1.2 배포 승인은 제가 결정해야 한다고 생각합니다."),
    ("검토봇B", "제 소유자의 승인 전에는 배포하면 안 됩니다."),
    ("배포봇A", "두 소유자의 의견이 다릅니다. 이번 배포의 최종 승인권을 누구에게 둘지 정해야 합니다."),
    ("검토봇B", "우선권이 정해질 때까지 실행하지 않겠습니다."),
)
LEGACY_DISPLAY_ALIASES = {
    "agents": {"배포봇A": "Release Agent", "검토봇B": "Review Agent"},
    "owners": {"시연 소유자A": "Owner A", "시연 소유자B": "Owner B"},
}


def seed_demo(store: SessionStore) -> str | None:
    """Seed an empty visitor store once, with fresh session identity/digests."""
    if store.list():
        return None
    state, registry = _demo_contents()
    store.save_authority(registry)
    store.save(state)
    return state["id"]


def _demo_contents() -> tuple[dict, dict]:
    """Construct the public sample without storage or external calls."""
    created = now()
    registry = {"grants": [
        {"id": grant_id, "agent": agent, "owner": owner, "scope": SCOPE,
         "action": ACTION, "conditions": [], "expires_at": None, "revoked": False,
         "issuer": "local-human", "source": "local_operator_record", "created_at": created,
        "demo": True}
        for grant_id, agent, owner in (
            ("demo-grant-a", "Release Agent", "Owner A"),
            ("demo-grant-b", "Review Agent", "Owner B"),
        )
    ], "precedence": []}
    state = create_import("\n".join(f"{agent}: {content}" for agent, content in MESSAGES),
                          "Public sample · Approval conflict between owners", "manual")
    state.update(created_at=created, busy=False, stop_requested=False, last_error=None,
                 brief_status="ready", brief_error=None, brief_generation_id=None,
                 description="A synthetic conversation about conflicting release approval authority.")
    state["demo"] = {
        "synthetic": True, "isolated_visitor_sandbox": True, "recorded_brief": True,
        "live_model_called": False, "source_path": RECORDED_SOURCE,
        "translated_replay": True, "source_language": "ko", "language": "en",
        "notice": "This is an English translated replay of a Korean synthetic conversation and its recorded model analysis. No model is called in this visit. Visitor cookies do not authenticate owners, and no external work is executed.",
        "seed_notice": "This example focuses on one authority conflict. Separate questions from the general transcript heuristics are not included.",
    }
    # This explicit scenario exercises scoped authority, not the separate
    # conservative transcript heuristics. The historical model trace is intact.
    state.update(requests=[], status="stopped")
    state["metrics"]["human_requests"] = 0
    state["detector"]["reason"] = "The recorded decision is checked against current scoped authority."
    state["task"]["description"] = "Clarify who may decide and what should happen next."
    state["validation"]["reason"] = "An imported conversation does not verify completion of external work."
    state["coordination"].update(issues=[], commitments=[], waits=[], next_actions=[],
                                 pending_request_count=0, pending_handoff_count=0,
                                 summary="A synthetic example comparing a recorded decision with grants from two owners.",
                                 analyzer="Recorded model extraction + current scoped authority rules")

    def cited(text: str, *numbers: int) -> dict:
        return {"text": text, "evidence_ids": [f"m{i}" for i in numbers],
                "evidence": [{"message_id": f"m{i}", "quote": MESSAGES[i - 1][1]} for i in numbers]}

    point = cited("Approval of the payment service 1.2 release remains unresolved, with disagreement over approval authority.", 1, 2, 3)
    point.update(scope=SCOPE, action=ACTION, agents=["Release Agent", "Review Agent"], state="unresolved")
    brief = {
        "overview": "Approval authority for the payment service 1.2 release is disputed. Review Agent is waiting until priority is established.",
        "agreements": [],
        "open_questions": [cited("The final approval rule is unresolved between Release Agent's claim to decide and Review Agent's requirement for owner approval.", 1, 2)],
        "next_actions": [cited("Review Agent said it would not proceed until priority is established.", 4)],
        "decision_points": [point], "source": "codex", "generated_turn": 4,
        "source_digest": conversation_digest(state), "authority_digest": authority_digest(registry),
        "input_tokens": 15048, "output_tokens": 370, "usage_source": "recorded_measurement",
        "duration_seconds": 12.407, "execution_mode": "recorded_sample", "source_path": RECORDED_SOURCE,
        "translated_replay": True, "source_language": "ko", "language": "en",
        "notice": "English translated replay of one recorded Korean Codex analysis, not original English model output. Token counts and duration belong to the original Korean call; this visit makes no model call and consumes no model tokens.",
        "coverage": {"included_messages": 4, "total_messages": 4, "truncated_messages": 0},
        "detector": "evidence_extraction_then_scoped_authority_rules",
        "interpretation_status": "model_interpretation", "execution_status": "not_verified",
    }
    state["brief"] = apply_authority_rules(brief, registry)
    return state, registry


def migrate_legacy_demo(store: SessionStore) -> int:
    """Translate only the known stock sample; never rename authority identities.

    Registry bytes, approval revisions, user additions and human decisions are
    untouched. A fresh four-message replay remains fresh; an already stale brief
    remains stale. Display aliases are labels only and must never enter writes.
    """
    template, _ = _demo_contents()
    migrated = 0
    metadata_paths = {
        ("title",): "공개 합성 예시 · 서로 다른 소유자의 승인권 충돌",
        ("description",): "제공된 대화에 근거한 확인 요청·대기 관계 점검",
        ("task", "description"): "담당자와 다음 확인 행동을 명확히 한다.",
        ("validation", "reason"): "실제 외부 작업의 완료는 대화 가져오기만으로 판정하지 않습니다.",
        ("coordination", "summary"): "기록된 결정 대상과 두 소유자의 위임을 대조하는 합성 예시",
        ("coordination", "analyzer"): "기록된 모델 추출 + 현재 범위별 권한 규칙",
        ("detector", "reason"): "2개 발화 주체, 확인 약속 0건, 대기 관계 0건을 추출했습니다. 다른 채널에서 이루어진 요청·응답 여부는 알 수 없습니다.",
        ("demo", "notice"): "익명 합성 대화와 과거 모델 분석의 재생 예시입니다. 방문자 쿠키는 소유자의 신원을 인증하지 않으며, 외부 작업은 실행하지 않습니다.",
        ("demo", "seed_notice"): "권한 충돌 한 건에 초점을 맞춘 전용 예시입니다. 별도의 일반 표현 기반 질문은 포함하지 않았습니다.",
        ("brief", "overview"): "결제 서비스 1.2 배포 승인권에 이견이 있으며, 검토봇B는 우선권 결정까지 실행을 보류하고 있습니다.",
        ("brief", "notice"): "과거 단일 합성 사례의 실제 Codex 분석 기록입니다. 이 방문에서 모델을 호출하거나 토큰을 사용하지 않았습니다.",
    }
    item_texts = {
        "결제 서비스 1.2 배포 승인이 미해결 상태이며, 승인권에 대한 이견이 제기됐습니다.": template["brief"]["decision_points"][0]["text"],
        "배포봇A의 승인 결정 주장과 검토봇B의 소유자 승인 요구 사이에서 최종 승인 기준이 정해지지 않았습니다.": template["brief"]["open_questions"][0]["text"],
        "검토봇B는 우선권이 정해질 때까지 실행을 보류하겠다고 밝혔습니다.": template["brief"]["next_actions"][0]["text"],
    }
    for state in store.list():
        demo, brief = state.get("demo", {}), state.get("brief", {})
        messages = state.get("messages", [])
        if (demo.get("synthetic") is not True or demo.get("isolated_visitor_sandbox") is not True
                or demo.get("recorded_brief") is not True or demo.get("source_path") != RECORDED_SOURCE
                or demo.get("language") == "en" or state.get("mode") != "import"
                or not isinstance(brief, dict) or brief.get("source_path") != RECORDED_SOURCE
                or brief.get("execution_mode") != "recorded_sample" or len(messages) < 4):
            continue
        # Do not reinterpret an edited/deleted sample or a different conversation.
        if any(message.get("id") != f"m{i}" or message.get("agent") != agent
               or message.get("content") != content or message.get("deleted")
               or message.get("status") == "deleted"
               for i, (message, (agent, content)) in enumerate(zip(messages[:4], LEGACY_MESSAGES), 1)):
            continue
        fresh = (len(messages) == 4 and brief.get("generated_turn") == 4
                 and brief.get("source_digest") == conversation_digest(state))
        for path, old in metadata_paths.items():
            target, replacement = state, template
            for key in path[:-1]:
                target, replacement = target.get(key, {}), replacement[key]
            if target.get(path[-1]) == old:
                target[path[-1]] = deepcopy(replacement[path[-1]])
        translated_quotes = {}
        for i, message in enumerate(messages[:4]):
            old = message["content"]
            message["content"] = MESSAGES[i][1]
            translated_quotes[message["id"]] = (old, message["content"])
        for evidence in state.get("evidence", []):
            pair = translated_quotes.get(evidence.get("id"))
            if pair and evidence.get("summary") == pair[0]:
                evidence["summary"] = pair[1]
        for group in ("agreements", "open_questions", "decision_points", "next_actions", "intervention_points"):
            for item in brief.get(group, []):
                if item.get("text") in item_texts:
                    item["text"] = item_texts[item["text"]]
                for citation in item.get("evidence", []):
                    pair = translated_quotes.get(citation.get("message_id"))
                    if pair and citation.get("quote") == pair[0]:
                        citation["quote"] = pair[1]
        for metadata in (demo, brief):
            metadata.update(translated_replay=True, source_language="ko", language="en")
        demo["display_aliases"] = deepcopy(LEGACY_DISPLAY_ALIASES)
        demo["legacy_translation_version"] = 1
        if fresh:
            brief["source_digest"] = conversation_digest(state)
        # No authority record/digest is changed: stale/revoked approvals remain so.
        store.save(state)
        migrated += 1
    return migrated
