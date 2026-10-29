from copy import deepcopy
from datetime import datetime, timezone

import pytest

from arbiter.authority import evaluate_authority


NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def grant(agent="A", owner="owner-a", **changes):
    return {"id": f"grant-{agent}", "agent": agent, "owner": owner, "scope": "review:proposal", "action": "approve",
            "conditions": [], "expires_at": None, "revoked": False, "issuer": "local-human",
            "created_at": "2026-10-29T11:00:00Z", "source": "local_operator_record", **changes}


def precedence(agents, **changes):
    return {"scope": "review:proposal", "action": "approve", "agents": agents, "issuer": "local-human", **changes}


def evaluate(grants, orders=None, **changes):
    return evaluate_authority({"grants": grants, "precedence": orders or []}, "review:proposal", "approve", now=NOW, **changes)


def test_one_valid_human_grant_identifies_the_scope_decision_owner():
    result = evaluate([grant()])
    assert result["status"] == "authorized"
    assert result["authorized_agents"] == ["A"]
    assert result["decision_owner"] == "A"
    assert result["owner_by_agent"] == {"A": "owner-a"}
    assert result["grant_ids"] == ["grant-A"]
    assert result["source"] == "local_operator_record"
    assert result["authority_only"]


def test_agent_claims_and_grants_for_other_scopes_or_actions_do_not_authorize():
    result = evaluate([grant(issuer="agent-A"), grant("B", scope="*"), grant("C", action="read"), grant("D", scope="review:another")])
    assert result["status"] == "authority_gap"
    assert result["authorized_agents"] == []
    assert result["decision_owner"] is None


@pytest.mark.parametrize("change", [{"revoked": True}, {"expires_at": "2026-10-29T11:59:59Z"}, {"expires_at": "2026-10-29T12:00:00Z"}, {"expires_at": "2026-10-29T21:00:00+09:00"}])
def test_revoked_and_expired_grants_are_excluded(change):
    assert evaluate([grant(**change)])["status"] == "authority_gap"


def test_expiry_with_timezone_is_compared_in_utc():
    result = evaluate([grant(expires_at="2026-10-29T21:00:01+09:00")])
    assert result["status"] == "authorized"


@pytest.mark.parametrize("expiry", ["2026-10-29T12:00:01", "tomorrow", "", 100, "2026-99-99T00:00:00Z"])
def test_invalid_or_naive_expiry_fails_closed(expiry):
    result = evaluate([grant(expires_at=expiry)])
    assert result["status"] == "unknown"
    assert result["decision_owner"] is None


def test_conditions_are_not_auto_verified_by_an_agent_boolean():
    result = evaluate([grant(conditions=["소유자가 예산을 확인한 경우"], conditions_verified=True)])
    assert result["status"] == "conditional"
    assert result["authorized_agents"] == []
    assert result["conditional_agents"] == ["A"]
    assert result["decision_owner"] is None
    assert result["required_owners"] == ["owner-a"]


def test_unverified_conditional_holder_cannot_outrank_a_valid_holder():
    result = evaluate([grant("A", conditions=["추가 동의 필요"]), grant("B")], [precedence(["A", "B"])])
    assert result["status"] == "authorized"
    assert result["decision_owner"] == "B"
    assert result["conditional_agents"] == ["A"]


def test_two_holders_without_precedence_are_a_scope_conflict():
    result = evaluate([grant("A"), grant("B")])
    assert result["status"] == "authority_conflict"
    assert result["authorized_agents"] == ["A", "B"]
    assert result["decision_owner"] is None


def test_same_owner_human_precedence_selects_one_agent_only_for_exact_scope():
    result = evaluate([grant("A"), grant("B")], [precedence(["B", "A"])])
    assert result["status"] == "authorized"
    assert result["decision_owner"] == "B"
    assert result["priority_order"] == ["B", "A"]
    assert evaluate([grant("A"), grant("B")], [precedence(["B", "A"], scope="*")])["status"] == "authority_conflict"


def test_precedence_cannot_manufacture_a_grant_for_its_highest_ranked_agent():
    result = evaluate([grant("A", revoked=True), grant("B"), grant("C")], [precedence(["unregistered", "A", "C", "B"])])
    assert result["decision_owner"] == "C"
    assert result["authorized_agents"] == ["B", "C"]
    assert result["priority_order"] == ["C", "B"]


def test_unranked_holder_is_not_silently_below_ranked_holders():
    result = evaluate([grant("A"), grant("B"), grant("C")], [precedence(["A", "B"])])
    assert result["status"] == "authority_conflict"


def test_different_owners_require_joint_approval_of_the_specific_precedence():
    grants = [grant("A", "owner-a"), grant("B", "owner-b")]
    for orders in ([], [precedence(["A", "B"])], [precedence(["A", "B"], approved_by=["owner-a"])],
                   [precedence(["A", "B"], approved_by=["owner-a", "owner-a"]) ]):
        result = evaluate(grants, orders)
        assert result["status"] == "cross_owner_conflict"
        assert result["required_owners"] == ["owner-a", "owner-b"]
        assert result["decision_owner"] is None
    approved = evaluate(grants, [precedence(["B", "A"], approved_by=["owner-a", "owner-b"])])
    assert approved["status"] == "authorized"
    assert approved["decision_owner"] == "B"
    assert approved["source"] == "local_operator_record"
    assert "원격 본인 인증" in approved["reason"]


def test_agent_authored_order_cannot_resolve_a_conflict_even_with_claimed_approvals():
    result = evaluate([grant("A", "owner-a"), grant("B", "owner-b")], [precedence(["A", "B"], issuer="agent", approved_by=["owner-a", "owner-b"])])
    assert result["status"] == "cross_owner_conflict"


def test_conflicting_human_orders_do_not_choose_by_record_order():
    result = evaluate([grant("A"), grant("B")], [precedence(["A", "B"]), precedence(["B", "A"])])
    assert result["status"] == "authority_conflict"


def test_participant_filter_is_exact_and_empty_filter_is_not_all_agents():
    result = evaluate([grant("A", "owner-a"), grant("B", "owner-b")], agents=["A"])
    assert result["decision_owner"] == "A"
    assert result["required_owners"] == ["owner-a"]
    assert evaluate([grant()], agents=[])["status"] == "authority_gap"


def test_owner_is_required_and_conflicting_owner_identity_is_not_invented():
    assert evaluate([grant(owner="")])["status"] == "unknown"
    result = evaluate([grant("A", "owner-a"), grant("A", "owner-b", id="second-grant")])
    assert result["status"] == "unknown"
    assert result["decision_owner"] is None


def test_duplicate_grant_rows_do_not_create_extra_holders_but_conflicting_ids_are_unknown():
    original = grant()
    assert evaluate([original, deepcopy(original)])["status"] == "authorized"
    assert evaluate([original, grant("B", id=original["id"])])["status"] == "unknown"


def test_unknown_input_is_not_treated_as_permission_and_registry_is_unchanged():
    registry = {"grants": [grant("A"), grant("B")], "precedence": [precedence(["B", "A"])]}
    before = deepcopy(registry)
    assert evaluate_authority(registry, "review:proposal", "approve", now=NOW)["decision_owner"] == "B"
    assert registry == before
    assert evaluate_authority(registry, "", "approve", now=NOW)["status"] == "unknown"
    assert evaluate_authority(registry, "review:proposal", "approve", agents="A", now=NOW)["status"] == "unknown"
    assert evaluate_authority(registry, "review:proposal", "approve", now=datetime(2026, 10, 29))["status"] == "unknown"
