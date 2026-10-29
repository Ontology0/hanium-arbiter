"""Anonymous, explicitly constructed public demo; never calls a model/provider.

The conversation and briefing are an English translation of the Korean synthetic
integration smoke in experiments/results/briefing-smoke/attempt-2.json. Recorded
usage belongs to that original call, not this translated replay. This is neither
a new inference nor evidence of an external release. No private database is read.
"""
from __future__ import annotations

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
    store.save_authority(registry)
    store.save(state)
    return state["id"]
