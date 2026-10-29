from copy import deepcopy

from arbiter.conversations import append_external_event, conversation_graph, create_import, decide_import, reanalyze_import


def append(state, agent, content, event_id):
    return append_external_event(state, {"event_id": event_id, "agent": agent, "content": content})


def pending(state, kind="handoff"):
    return [item for item in state["requests"] if item["status"] == "pending" and item["kind"] == kind]


def delivered(state, request):
    decide_import(state, request["id"], "already_delivered", "주인에게 전달했다는 사람의 보고. 독립된 영수증은 없음.")


def test_new_actor_cannot_inherit_an_old_delivery_decision():
    state = create_import("A: B에게 모임 시간을 확인하고 알려드릴게요.")
    original = pending(state)[0]
    delivered(state, original)
    old_decisions = deepcopy(state["decisions"])
    append(state, "C", "D에게 참석 여부를 확인하고 알려드릴게요.", "new-actor")
    assert original["id"] != pending(state)[0]["id"]
    assert pending(state)[0]["scope"]["actor"] == "C"
    assert pending(state)[0]["delivery_status"] == "unknown"
    original = next(item for item in state["requests"] if item["id"] == original["id"])
    assert original["status"] == "resolved"
    assert original["delivery_status"] == "human_reported_delivered"
    assert state["coordination"]["delivery_status"] == "mixed"
    assert state["coordination"]["pending_handoff_count"] == 1
    assert state["status"] == "waiting"
    assert state["decisions"] == old_decisions


def test_same_actor_new_topic_needs_a_new_decision():
    state = create_import("A: B에게 모임 시간을 확인하고 알려드릴게요.")
    first = pending(state)[0]
    delivered(state, first)
    append(state, "A", "B에게 모임 장소를 확인하고 알려드릴게요.", "new-topic")
    assert len(pending(state)) == 1
    assert pending(state)[0]["scope"]["actor"] == "A"
    assert "장소" in pending(state)[0]["scope"]["topic"]
    assert pending(state)[0]["id"] != first["id"]


def test_same_actor_new_recipient_needs_a_new_decision():
    state = create_import("A: B에게 모임 시간을 확인하고 알려드릴게요.")
    delivered(state, pending(state)[0])
    append(state, "A", "C에게 모임 시간을 확인하고 알려드릴게요.", "new-recipient")
    assert len(pending(state)) == 1
    assert pending(state)[0]["scope"]["target"] == "C"


def test_exact_obligation_repeated_with_new_event_id_preserves_decision():
    text = "B에게 모임 시간을 확인하고 알려드릴게요."
    state = create_import("A: " + text)
    original = pending(state)[0]
    delivered(state, original)
    append(state, "A", text, "repeat-report")
    assert pending(state) == []
    assert len(state["requests"]) == 1
    assert state["requests"][0]["id"] == original["id"]
    assert state["requests"][0]["evidence_ids"] == ["m1", "m2"]
    assert len(state["decisions"]) == 1
    assert state["coordination"]["delivery_status"] == "human_reported_delivered"
    assert state["status"] == "stopped"


def test_cosmetic_whitespace_and_trailing_punctuation_do_not_create_new_duty():
    state = create_import("A: B에게 모임 시간을 확인하고 알려드릴게요.")
    delivered(state, pending(state)[0])
    append(state, "A", "B에게   모임 시간을 확인하고 알려드릴게요!", "formatted-repeat")
    assert pending(state) == []
    assert len(state["requests"]) == 1


def test_new_actor_becoming_known_does_not_change_an_existing_scope_id():
    state = create_import("A: B에게 모임 시간을 확인하고 알려드릴게요.")
    original_id = pending(state)[0]["id"]
    delivered(state, pending(state)[0])
    append(state, "B", "연락을 받았습니다.", "b-joins")
    assert state["requests"][0]["id"] == original_id
    assert state["requests"][0]["status"] == "resolved"
    assert pending(state) == []


def test_per_request_delivery_rolls_up_to_mixed_then_delivered():
    state = create_import("A: 주인에게 시간을 확인하고 알려드릴게요.\nB: 주인에게 장소를 확인하고 알려드릴게요.")
    assert len(pending(state)) == 2
    assert state["coordination"]["delivery_status"] == "unknown"
    delivered(state, pending(state)[0])
    assert state["coordination"]["delivery_status"] == "mixed"
    assert len(pending(state)) == 1
    delivered(state, pending(state)[0])
    assert state["coordination"]["delivery_status"] == "human_reported_delivered"
    assert all(item["status"] == "human_reported_delivered" for item in state["coordination"]["commitments"])
    assert all(item["delivery_status"] == "not_sent" for item in state["decisions"])


def test_assigning_sender_does_not_establish_delivery():
    state = create_import("A: 주인에게 확인하고 알려드릴게요.")
    request = pending(state)[0]
    decide_import(state, request["id"], "assign_sender", "A가 참석 여부 질문을 준비한다.")
    assert state["requests"][0]["delivery_status"] == "unknown"
    assert state["coordination"]["delivery_status"] == "unknown"
    assert state["decisions"][0]["scope_id"] == request["scope_id"]


def test_new_review_topic_cannot_inherit_prior_owner_choice():
    state = create_import("A: 제안서 검토를 부탁드립니다.")
    request = pending(state, "authority")[0]
    decide_import(state, request["id"], "assign_owner", "제안서의 최종 승인자는 A")
    append(state, "A", "예산서 검토를 부탁드립니다.", "budget-review")
    assert len(pending(state, "authority")) == 1
    assert pending(state, "authority")[0]["id"] != request["id"]
    assert len(state["decisions"]) == 1


def test_an_explicit_owner_for_one_message_does_not_suppress_another_topic():
    state = create_import("A: 제안서 최종 승인자는 A입니다.\nC: 예산서 검토를 부탁드립니다.")
    requests = pending(state, "authority")
    assert len(requests) == 1
    assert requests[0]["scope"]["actor"] == "C"


def test_new_wait_cycle_cannot_inherit_a_different_pair_decision():
    state = create_import("A: B의 검토가 끝나면 진행하겠습니다.\nB: A의 검토가 끝나면 진행하겠습니다.")
    original = pending(state, "coordination")[0]
    decide_import(state, original["id"], "assign_owner", "A가 먼저 제안서를 검토한다.")
    append(state, "C", "D의 검토가 끝나면 진행하겠습니다.", "c-waits")
    append(state, "D", "C의 검토가 끝나면 진행하겠습니다.", "d-waits")
    assert len(pending(state, "coordination")) == 1
    assert pending(state, "coordination")[0]["scope"]["actors"] == ["C", "D"]
    old = next(item for item in state["requests"] if item["id"] == original["id"])
    assert old["status"] == "resolved"


def test_event_id_retry_is_idempotent_and_turn_ceiling_tracks_imported_messages():
    state = create_import("A: 준비하겠습니다.")
    append(state, "B", "주인에게 확인하고 알려드릴게요.", "same-event")
    snapshot = deepcopy(state)
    append(state, "B", "주인에게 확인하고 알려드릴게요.", "same-event")
    assert state == snapshot
    assert state["turn"] == state["max_turns"] == len(state["messages"]) == 2


def test_legacy_group_decision_is_limited_to_its_original_evidence():
    state = create_import("A: B에게 모임 시간을 확인하고 알려드릴게요.")
    delivered(state, pending(state)[0])
    legacy = state["requests"][0]
    legacy["id"] = "request-handoff-status"
    for key in ("scope_id", "scope", "choice", "delivery_status"):
        legacy.pop(key, None)
    state["decisions"][0]["request_id"] = legacy["id"]
    append(state, "C", "D에게 장소를 확인하고 알려드릴게요.", "new-duty")
    assert len(pending(state)) == 1
    assert pending(state)[0]["scope"]["actor"] == "C"
    assert any(item["id"] == "request-handoff-status" and item["status"] == "resolved" for item in state["requests"])
    current_old = next(item for item in state["requests"] if item.get("scope", {}).get("actor") == "A")
    assert current_old["status"] == "resolved"
    assert current_old["delivery_status"] == "human_reported_delivered"
    assert current_old["resolved_by_request_id"] == "request-handoff-status"
    graph = conversation_graph(state)
    node_ids = {item["id"] for item in graph["nodes"]}
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in graph["edges"])


def test_edit_creates_new_obligation_and_preserves_previous_resolution_history():
    state = create_import("A: B에게 시간을 확인하고 알려드릴게요.")
    old_request = pending(state)[0]
    delivered(state, old_request)
    state["messages"][0]["content"] = "B에게 장소를 확인하고 알려드릴게요."
    reanalyze_import(state)
    assert len(pending(state)) == 1
    assert pending(state)[0]["id"] != old_request["id"]
    old = next(item for item in state["requests"] if item["id"] == old_request["id"])
    assert old["status"] == "resolved" and not old["active"]
    assert len(state["decisions"]) == 1
    assert state["coordination"]["delivery_status"] == "unknown"


def test_deleted_message_retires_pending_question_without_dropping_history():
    state = create_import("A: B에게 확인하고 알려드릴게요.")
    old_id = pending(state)[0]["id"]
    state["messages"][0]["deleted"] = True
    reanalyze_import(state)
    assert pending(state) == []
    assert state["requests"][0]["id"] == old_id
    assert state["requests"][0]["status"] == "superseded"
    assert state["status"] == "stopped"
    assert state["coordination"]["commitments"] == []
