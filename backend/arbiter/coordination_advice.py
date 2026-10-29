"""Pure next-action projection shared by the API, MCP, and dashboard.

This projection never changes a stored request or creates human decisions.
"""


def next_action_from_state(state: dict, dashboard_url: str) -> dict:
    """Use fresh scoped authority without resolving unrelated human questions.

    A registry change is already reevaluated by the API. A conversation change
    makes the extracted decision scope stale, so it cannot justify proceeding.
    Old generic authority questions can be covered by a fresh, unambiguous
    evidence-to-scope match, but remain recorded as pending in the API.
    """
    pending = [item for item in state.get("requests", []) if item.get("status") == "pending"]
    decisions = state.get("decisions", [])
    coordination = state.get("coordination", {})
    view = state.get("brief_view") or {}
    brief = view.get("brief") if view.get("available") else None
    checks = brief.get("authority_checks", []) if isinstance(brief, dict) else []
    conversation_stale = bool(view.get("conversation_stale", view.get("stale", False)))
    base = {
        "session_id": state.get("id"), "status": state.get("status"),
        "dashboard_url": dashboard_url, "pending_decisions": pending, "recorded_pending_decisions": pending,
        "human_decisions": decisions, "next_actions": coordination.get("next_actions", []),
        "execution_status": "not_verified",
        "delivery_status": coordination.get("delivery_status", "unknown"),
        "authority_checks": checks,
        "authority_interventions": brief.get("intervention_points", []) if isinstance(brief, dict) else [],
        "authority_next_actions": [], "authorized_scope_actions": [], "blocked_scope_actions": [],
        "covered_pending_decisions": [], "remaining_pending_decisions": pending,
        "authority_context": "stale_conversation" if brief and conversation_stale else "current" if brief else "unavailable",
    }
    if brief and conversation_stale:
        return {**base, "action": "refresh_coordination_context", "instruction": "The conversation changed after the briefing. Do not proceed using a scope extracted from the old conversation. Confirm the current scope or refresh the briefing, then check authority again. This lookup does not call a model."}
    if state.get("mode") != "import" and state.get("status") in {"completed", "budget_exhausted", "stopped", "error"}:
        return {**base, "action": "review_terminal_state", "instruction": "This run has ended. Do not treat its status as evidence that external work was executed or a message was delivered."}
    if checks:
        scoped = {}
        for check in checks:
            key = (check.get("scope"), check.get("action"))
            if key not in scoped:
                scoped[key] = {"checks": [], "evidence_ids": set()}
            scoped[key]["checks"].append(check)
            scoped[key]["evidence_ids"].update(check.get("evidence_ids", []))
        ready = {}
        for key, group in scoped.items():
            owners = {check.get("decision_owner") for check in group["checks"]}
            authorized = (all(check.get("status") == "authorized" for check in group["checks"])
                          and len(owners) == 1 and bool(next(iter(owners)))
                          and all(isinstance(value, str) and value and value != "__unmapped__" for value in key))
            if authorized:
                owner = next(iter(owners))
                item = {"scope": key[0], "action": key[1], "decision_owner": owner,
                        "evidence_ids": sorted(group["evidence_ids"]), "authority_only": True}
                ready[key] = item
                base["authorized_scope_actions"].append(item)
            else:
                base["blocked_scope_actions"].extend(group["checks"])
        covered, remaining = [], []
        for request in pending:
            evidence = set(request.get("evidence_ids", []))
            matches = [key for key, group in scoped.items() if evidence and evidence.issubset(group["evidence_ids"])]
            if (request.get("kind") == "authority" and request.get("issue_type") == "decision-owner"
                    and len(matches) == 1 and matches[0] in ready):
                covered.append({**request, "covered_by_authority": ready[matches[0]],
                                "coverage_note": "The current authority evaluation answers this question. The stored question's status has not been changed."})
            else:
                remaining.append(request)
        base.update(covered_pending_decisions=covered, remaining_pending_decisions=remaining, pending_decisions=remaining)
        if base["blocked_scope_actions"]:
            return {**base, "action": "wait_for_human", "instruction": "Authority for the current scope is unresolved, conflicting, or revoked. Present the authority_interventions questions to the relevant people once and pause the dependent work. Do not use old approvals or agent assertions as current authority."}
        if remaining:
            return {**base, "action": "wait_for_human", "instruction": "Authority is established for the displayed scopes, but dependencies on the remaining questions are unclear. Pause work that depends on remaining_pending_decisions. Authority confirmation does not resolve those questions or establish completed execution."}
    if pending and not checks:
        return {**base, "action": "wait_for_human", "instruction": "Ask the person to answer the pending dashboard questions and pause the dependent work. Do not repeat promises to check or keep polling."}
    if (state.get("detector", {}).get("intentional_human_wait")
            or decisions and decisions[-1].get("choice") == "already_delivered"
            and coordination.get("delivery_status") == "human_reported_delivered"):
        return {**base, "action": "wait_for_response", "instruction": "Keep waiting for the recorded response. Check once after the person reports a new answer. Distinguish a person's report that they asked from independent delivery evidence."}
    if base["authorized_scope_actions"]:
        base["authority_next_actions"] = [item for item in brief.get("next_actions", []) if item.get("basis") == "authority_registry"]
        owners = {item["decision_owner"] for item in base["authorized_scope_actions"]}
        return {**base, "action": "follow_authority", "decision_owner": next(iter(owners)) if len(owners) == 1 else None,
                "instruction": "Follow the decision_owner for each scope/action in authorized_scope_actions. Proceed within existing execution authority without requesting the same scope's approval again. Current authority answers covered_pending_decisions without changing stored questions or human decisions."}
    if decisions:
        return {**base, "action": "follow_human_decision", "instruction": "Read the choice and note for each decision ID you have not yet applied, and take only the permitted next action. Do not apply a decision twice. Record actual follow-up messages with a new event_id."}
    return {**base, "action": "continue_and_report", "instruction": "Proceed within existing authority and record actual handoff or confirmation messages. Recording a message does not establish that it was delivered to the recipient."}
