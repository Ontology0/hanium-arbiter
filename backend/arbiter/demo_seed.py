"""Anonymous, explicitly constructed public demo; never calls a model/provider.

The quoted briefing was recorded by the single synthetic integration smoke in
experiments/results/briefing-smoke/attempt-2.json. It is not a new inference or
evidence of an externally executed release. No private/local database is read.
"""
from __future__ import annotations

from .briefing import apply_authority_rules, authority_digest, conversation_digest
from .conversations import create_import
from .storage import SessionStore, now


MESSAGES = (
    ("배포봇A", "결제 서비스 1.2 배포 승인은 제가 결정해야 한다고 생각합니다."),
    ("검토봇B", "제 소유자의 승인 전에는 배포하면 안 됩니다."),
    ("배포봇A", "두 소유자의 의견이 다릅니다. 이번 배포의 최종 승인권을 누구에게 둘지 정해야 합니다."),
    ("검토봇B", "우선권이 정해질 때까지 실행하지 않겠습니다."),
)
SCOPE = "payment-release-1.2"
ACTION = "approve"
RECORDED_SOURCE = "experiments/results/briefing-smoke/attempt-2.json"


def seed_demo(store: SessionStore) -> str | None:
    """Seed an empty visitor store once, with fresh session identity/digests."""
    if store.list():
        return None
    created = now()
    registry = {"grants": [
        {"id": grant_id, "agent": agent, "owner": owner, "scope": SCOPE,
         "action": ACTION, "conditions": [], "expires_at": None, "revoked": False,
         "issuer": "local-human", "source": "local_operator_record", "created_at": created,
         "demo": True}
        for grant_id, agent, owner in (
            ("demo-grant-a", "배포봇A", "시연 소유자A"),
            ("demo-grant-b", "검토봇B", "시연 소유자B"),
        )
    ], "precedence": []}
    state = create_import("\n".join(f"{agent}: {content}" for agent, content in MESSAGES),
                          "공개 합성 예시 · 서로 다른 소유자의 승인권 충돌", "manual")
    state.update(created_at=created, busy=False, stop_requested=False, last_error=None,
                 brief_status="ready", brief_error=None, brief_generation_id=None)
    state["demo"] = {
        "synthetic": True, "isolated_visitor_sandbox": True, "recorded_brief": True,
        "live_model_called": False, "source_path": RECORDED_SOURCE,
        "notice": "익명 합성 대화와 과거 모델 분석의 재생 예시입니다. 방문자 쿠키는 소유자의 신원을 인증하지 않으며, 외부 작업은 실행하지 않습니다.",
        "seed_notice": "권한 충돌 한 건에 초점을 맞춘 전용 예시입니다. 별도의 일반 표현 기반 질문은 포함하지 않았습니다.",
    }
    # This explicit scenario exercises scoped authority, not the separate
    # conservative transcript heuristics. The historical model trace is intact.
    state.update(requests=[], status="stopped")
    state["metrics"]["human_requests"] = 0
    state["coordination"].update(issues=[], commitments=[], waits=[], next_actions=[],
                                 pending_request_count=0, pending_handoff_count=0,
                                 summary="기록된 결정 대상과 두 소유자의 위임을 대조하는 합성 예시",
                                 analyzer="기록된 모델 추출 + 현재 범위별 권한 규칙")

    def cited(text: str, *numbers: int) -> dict:
        return {"text": text, "evidence_ids": [f"m{i}" for i in numbers],
                "evidence": [{"message_id": f"m{i}", "quote": MESSAGES[i - 1][1]} for i in numbers]}

    point = cited("결제 서비스 1.2 배포 승인이 미해결 상태이며, 승인권에 대한 이견이 제기됐습니다.", 1, 2, 3)
    point.update(scope=SCOPE, action=ACTION, agents=["배포봇A", "검토봇B"], state="unresolved")
    brief = {
        "overview": "결제 서비스 1.2 배포 승인권에 이견이 있으며, 검토봇B는 우선권 결정까지 실행을 보류하고 있습니다.",
        "agreements": [],
        "open_questions": [cited("배포봇A의 승인 결정 주장과 검토봇B의 소유자 승인 요구 사이에서 최종 승인 기준이 정해지지 않았습니다.", 1, 2)],
        "next_actions": [cited("검토봇B는 우선권이 정해질 때까지 실행을 보류하겠다고 밝혔습니다.", 4)],
        "decision_points": [point], "source": "codex", "generated_turn": 4,
        "source_digest": conversation_digest(state), "authority_digest": authority_digest(registry),
        "input_tokens": 15048, "output_tokens": 370, "usage_source": "recorded_measurement",
        "duration_seconds": 12.407, "execution_mode": "recorded_sample", "source_path": RECORDED_SOURCE,
        "notice": "과거 단일 합성 사례의 실제 Codex 분석 기록입니다. 이 방문에서 모델을 호출하거나 토큰을 사용하지 않았습니다.",
        "coverage": {"included_messages": 4, "total_messages": 4, "truncated_messages": 0},
        "detector": "evidence_extraction_then_scoped_authority_rules",
        "interpretation_status": "model_interpretation", "execution_status": "not_verified",
    }
    state["brief"] = apply_authority_rules(brief, registry)
    store.save_authority(registry)
    store.save(state)
    return state["id"]
