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
        return {**base, "action": "refresh_coordination_context", "instruction": "브리핑 이후 대화가 바뀌었습니다. 이전 대화에서 추출한 범위로 진행하지 마세요. 최신 대화의 대상 범위를 확인하거나 브리핑을 갱신한 뒤 권한을 다시 조회하세요. 이 조회는 모델을 호출하지 않습니다."}
    if state.get("mode") != "import" and state.get("status") in {"completed", "budget_exhausted", "stopped", "error"}:
        return {**base, "action": "review_terminal_state", "instruction": "현재 실행은 종료 상태입니다. 이 상태를 외부 작업 실행이나 전달 완료의 증거로 사용하지 마세요."}
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
                                "coverage_note": "현재 권한 판정으로 답할 수 있는 질문입니다. 저장된 질문의 상태를 변경한 것은 아닙니다."})
            else:
                remaining.append(request)
        base.update(covered_pending_decisions=covered, remaining_pending_decisions=remaining, pending_decisions=remaining)
        if base["blocked_scope_actions"]:
            return {**base, "action": "wait_for_human", "instruction": "현재 범위에 미확정·충돌·철회된 권한이 있습니다. authority_interventions의 질문을 관련 사람에게 한 번 안내하고 해당 의존 작업을 대기하세요. 이전 승인이나 에이전트의 주장을 현재 권한으로 사용하지 마세요."}
        if remaining:
            return {**base, "action": "wait_for_human", "instruction": "표시된 범위의 권한은 확인됐지만 남은 질문과의 의존 관계를 확정할 수 없습니다. remaining_pending_decisions에 해당하는 의존 작업을 보류하세요. 권한 확인을 질문 해소나 실행 완료로 간주하지 마세요."}
    if pending and not checks:
        return {**base, "action": "wait_for_human", "instruction": "사람이 대시보드에서 보류 중인 질문에 응답하도록 안내하고 해당 의존 작업을 대기하세요. 확인 약속을 반복하거나 계속 조회하지 마세요."}
    if (state.get("detector", {}).get("intentional_human_wait")
            or decisions and decisions[-1].get("choice") == "already_delivered"
            and coordination.get("delivery_status") == "human_reported_delivered"):
        return {**base, "action": "wait_for_response", "instruction": "기록된 응답 대기를 유지하세요. 사람이 새 응답을 알려주면 한 번 다시 조회하세요. 이미 요청했다는 사람의 보고와 독립된 전달 증거는 구분하세요."}
    if base["authorized_scope_actions"]:
        base["authority_next_actions"] = [item for item in brief.get("next_actions", []) if item.get("basis") == "authority_registry"]
        owners = {item["decision_owner"] for item in base["authorized_scope_actions"]}
        return {**base, "action": "follow_authority", "decision_owner": next(iter(owners)) if len(owners) == 1 else None,
                "instruction": "authorized_scope_actions에 명시된 각 scope/action의 decision_owner가 결정하도록 따르세요. 기존 실행 권한 안에서 진행하며 같은 범위의 승인을 다시 요청하지 마세요. covered_pending_decisions는 현재 권한으로 답할 수 있지만 저장된 질문·사람 결정의 상태를 변경하지 않습니다."}
    if decisions:
        return {**base, "action": "follow_human_decision", "instruction": "아직 적용하지 않은 결정 ID의 선택과 메모를 읽고 허용된 다음 행동만 수행하세요. 이미 적용한 결정을 중복 실행하지 말고, 실제 후속 메시지는 새로운 event_id로 기록하세요."}
    return {**base, "action": "continue_and_report", "instruction": "기존 권한 범위에서 작업을 진행하고 실제 인계·확인 메시지를 기록하세요. 메시지 기록 자체가 상대방에게 전달했다는 뜻은 아닙니다."}
