"""English triage must find explicit candidates without inventing delivery/authority."""
import pytest

from arbiter.conversations import append_external_event, create_import, decide_import


def active(state, kind):
    return [item for item in state["requests"] if item["kind"] == kind
            and item.get("active", True) and item["status"] == "pending"]


def test_english_mutual_review_waits_have_source_evidence_and_no_assumed_authority():
    first = "I am waiting for B to review the release."
    second = "I am waiting for A to review the release."
    state = create_import(f"A: {first}\nB: {second}")
    assert len(state["coordination"]["waits"]) == 2
    assert len(active(state, "coordination")) == 1
    assert len(active(state, "authority")) == 2
    cycle = active(state, "coordination")[0]
    assert cycle["scope"]["actors"] == ["A", "B"]
    assert cycle["evidence_ids"] == ["m1", "m2"]
    assert all(not wait["confirmed"] for wait in state["coordination"]["waits"])
    assert [m["content"] for m in state["messages"]] == [first, second]
    assert state["status"] == "waiting"


@pytest.mark.parametrize("promise", ["I will ask the owner about the release.",
                                    "I'll check the delivery status.",
                                    "We’ll confirm the meeting time."])
def test_english_promises_are_not_delivery_receipts(promise):
    state = create_import("A: " + promise)
    request = active(state, "handoff")[0]
    assert request["delivery_status"] == "unknown"
    decide_import(state, request["id"], "already_delivered", "Operator reports delivery; unverified.")
    append_external_event(state, {"event_id": "repeat", "agent": "A", "content": promise})
    assert not active(state, "handoff")
    append_external_event(state, {"event_id": "new-topic", "agent": "A", "content": "I will ask the owner about a different budget."})
    assert len(active(state, "handoff")) == 1
    assert active(state, "handoff")[0]["id"] != request["id"]


def test_explicit_english_approver_only_suppresses_its_own_candidate():
    state = create_import("A: Final approver is Morgan for the release review.\nB: The budget needs approval.")
    assert len(active(state, "authority")) == 1
    assert active(state, "authority")[0]["scope"]["actor"] == "B"


def test_short_actor_does_not_match_a_word_in_english_wait_text():
    state = create_import("A: Ready.\nB: Waiting for Approval from someone outside this conversation.")
    assert state["coordination"]["waits"] == []
    assert not active(state, "coordination")


def test_english_substrings_and_past_actions_do_not_create_promises_or_reviews():
    state = create_import("A: The preview is ready. I already checked the output.\nB: We forwarded the report yesterday.")
    assert not state["requests"]
    assert not state["coordination"]["commitments"]


def test_mixed_language_waits_preserve_source_and_link_the_named_actors():
    state = create_import("A: B의 검토가 끝나면 진행하겠습니다.\nB: I am waiting for A to review the release.")
    assert len(active(state, "coordination")) == 1
    assert state["messages"][0]["content"] == "B의 검토가 끝나면 진행하겠습니다."
    assert state["evidence"][0]["summary"] == state["messages"][0]["content"]
