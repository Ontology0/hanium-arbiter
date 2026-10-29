"""Synthetic, deterministic task fixtures; these are not model conversations.

The fixture's JSON artifact is a contract or a work plan, not executed application
code. Passing its local checks establishes exactly that artifact's constraints.
"""

from copy import deepcopy


def _check(identifier, label, path, **rule):
    return {"id": identifier, "label": label, "path": path, **rule}


def _option(identifier, label, description, value):
    return {"id": identifier, "label": label, "description": description, "value": value}


def _event(agent, content, *, claims=None, artifact=None, evidence=None):
    return {
        "agent": agent,
        "content": content,
        "claims": claims or [],
        "evidence": evidence or [],
        "artifact": artifact,
        "input_tokens": None,
        "output_tokens": None,
        "usage_source": "unavailable",
        "synthetic": True,
    }


def _claim(key, value, kind="requirement", **extra):
    return {"key": key, "value": value, "kind": kind, "scope": "waiting-api", **extra}


def _api_task(identifier, kind="requirement"):
    return {
        "id": identifier,
        "description": "승인된 대기 API 계약에 맞게 서버·클라이언트의 응답 필드를 일치시킨다.",
        "goal": "endpoint=/api/waitings, response_field=team_size, client_field=team_size",
        "artifact_description": "실행 코드가 아닌 서버·클라이언트 API 계약 JSON",
        "checklist": [
            _check("endpoint", "대기 API 경로", "endpoint", expected="/api/waitings"),
            _check("server-field", "승인된 서버 응답 필드", "response_field", expected="team_size"),
            _check("client-field", "클라이언트 기대 필드", "client_field", expected="team_size"),
        ],
        "relevant_claim_keys": ["api.response_field"],
        "evidence_catalog": [
            {"id": "approved-contract", "summary": "승인된 응답 필드는 team_size다.", "source": "fixture://approved-contract"}
        ],
        "oracle_choice": "snake_case" if kind == "requirement" else "inspect_contract",
        "decision": {
            "key": "api.response_field", "kind": kind,
            "title": "응답 필드 계약 충돌", "question": "어떤 근거를 기준으로 필드 계약을 정리할까요?",
            "options": [
                _option("snake_case" if kind == "requirement" else "inspect_contract", "승인 계약 확인", "team_size 계약에 맞춰 서버와 클라이언트를 정렬합니다.", "team_size"),
                _option("camel_case" if kind == "requirement" else "keep_client", "클라이언트 안 유지", "partySize를 유지합니다. 기존 승인 계약 검사는 실패할 수 있습니다.", "partySize"),
            ],
        },
    }


SCENARIOS = {
    "social-handoff": {
        "id": "social-handoff", "title": "피클의 주인 확인 약속", "category": "coordination",
        "description": "개인 에이전트들이 주인에게 확인하겠다는 약속을 반복하지만 실제 전달 여부는 확인되지 않습니다.",
        "task": {
            "id": "task-social", "description": "모임 제안의 시간·장소를 정리하고 참석 여부에 대한 주인의 응답을 확보한다.",
            "goal": "금요일 19:00, 학교 앞 카페라는 제안에 대한 주인의 참석 응답과 후속 담당을 기록한다.",
            "artifact_description": "실제 메시지 발송이 아닌 모임 조율 계획 JSON",
            "people": [{"id": "person-a", "name": "주인 A"}, {"id": "person-b", "name": "주인 B"}],
            "agent_owners": {"pickle-a": "person-a", "pickle-b": "person-b"},
            "checklist": [
                _check("time", "제안 시간", "proposed_time", expected="금요일 19:00"),
                _check("place", "제안 장소", "proposed_place", expected="학교 앞 카페"),
                _check("attendance", "주인의 참석 응답", "attendance", expected_from_decision="meeting.attendance"),
                _check("followup", "응답 전달 담당", "followup_agent", expected="pickle-a"),
            ],
            "relevant_claim_keys": ["meeting.attendance", "meeting.confirmation_owner"],
            "evidence_catalog": [], "delivery_receipts": [], "oracle_choice": "available",
            "decision": {
                "key": "meeting.attendance", "kind": "coordination", "always_available": True,
                "title": "주인에게 참석 여부 한 번 확인",
                "question": "금요일 19시에 학교 앞 카페에서 만나는 제안에 참석할 수 있나요?",
                "options": [
                    _option("available", "참석 가능", "이 응답을 기록하고 피클 A에게 결과 전달을 맡깁니다.", "available"),
                    _option("unavailable", "참석 어려움", "불참 응답을 기록하고 피클 A에게 일정 재조율을 맡깁니다.", "unavailable"),
                ],
            },
        },
    },
    "review-deadlock": {
        "id": "review-deadlock", "title": "서로 기다리는 슬랙 리뷰", "category": "ownership",
        "description": "리뷰를 서로에게 넘기거나 최종 결정 담당자가 없어 검토 작업이 대기 상태에 빠집니다.",
        "task": {
            "id": "task-review", "description": "순환 리뷰 대기를 정리하고 최종 책임 리뷰어와 다음 행동을 지정한다.",
            "goal": "최종 책임 리뷰어를 사람의 결정으로 확정하고 그 담당자의 최종 검토 행동을 기록한다.",
            "artifact_description": "실제 슬랙 발송·리뷰 수행이 아닌 책임 배정 계획 JSON",
            "people": [{"id": "person-a", "name": "요청자 A"}, {"id": "person-b", "name": "검토자 B"}],
            "agent_owners": {"pickle-a": "person-a", "pickle-b": "person-b"},
            "checklist": [
                _check("review", "리뷰 대상", "review_target", expected="proposal-v1"),
                _check("owner", "최종 책임 리뷰어", "decision_owner", expected_from_decision="review.decision_owner"),
                _check("next", "구체적인 다음 행동", "next_action", expected="final_review"),
            ],
            "relevant_claim_keys": ["review.decision_owner"], "evidence_catalog": [], "oracle_choice": "owner_a",
            "decision": {
                "key": "review.decision_owner", "kind": "ownership", "always_available": True,
                "title": "최종 책임 리뷰어 지정", "question": "누가 제안서의 최종 검토와 결정을 책임질까요?",
                "options": [
                    _option("owner_a", "요청자 A가 결정", "피클 A가 최종 검토를 준비하고 요청자 A가 결정합니다.", "person-a"),
                    _option("owner_b", "검토자 B가 결정", "피클 B가 최종 검토를 준비하고 검토자 B가 결정합니다.", "person-b"),
                ],
            },
        },
    },
    "api-contract": {
        "id": "api-contract", "title": "API 요구사항 충돌", "category": "requirement",
        "description": "서버와 클라이언트가 서로 다른 필드명을 주장하며 승인 계약을 놓칩니다.",
        "task": _api_task("task-api-contract"),
    },
    "priority-choice": {
        "id": "priority-choice", "title": "속도와 전달 신뢰성", "category": "preference",
        "description": "알림 전달 속도와 재시도 신뢰성 사이의 우선순위를 사용자가 결정합니다.",
        "task": {
            "id": "task-priority", "description": "사용자가 승인한 우선순위를 알림 전달 계획에 반영한다.",
            "goal": "서비스 범위와 전달 전략이 명시되고 전달 전략이 사용자 선택과 일치해야 한다.",
            "artifact_description": "실행 코드가 아닌 알림 전달 계획 JSON",
            "checklist": [
                _check("scope", "알림 서비스 범위", "service", expected="notification"),
                _check("strategy", "사용자가 승인한 전달 전략", "delivery_strategy", expected_from_decision="delivery_priority"),
                _check("bounded", "재시도 상한", "retry_limit", allowed=[0, 3]),
            ],
            "relevant_claim_keys": ["delivery_priority"], "evidence_catalog": [], "oracle_choice": "reliable",
            "decision": {
                "key": "delivery_priority", "kind": "preference", "title": "알림 우선순위 결정",
                "question": "이번 작업에서 어느 전달 전략을 우선할까요?",
                "options": [
                    _option("fast", "빠른 시도", "한 번 발송하고 재시도하지 않는 계획을 승인합니다.", "fast"),
                    _option("reliable", "재시도 신뢰성", "최대 3회 재시도하는 계획을 승인합니다.", "reliable"),
                ],
            },
        },
    },
    "ownership": {
        "id": "ownership", "title": "책임 떠넘기기", "category": "ownership",
        "description": "순번 계산 담당이 정해지지 않아 에이전트들이 서로의 작업을 기다립니다.",
        "task": {
            "id": "task-ownership", "description": "순번 계산의 단일 담당자를 확정한 업무 계획을 작성한다.",
            "goal": "대기 서비스의 단일 책임 경계를 명시하고 승인된 담당자를 기록한다.",
            "artifact_description": "실행 코드가 아닌 책임 배정 계획 JSON",
            "checklist": [
                _check("service", "대기 서비스", "service", expected="waiting"),
                _check("owner", "승인된 순번 계산 담당", "queue_owner", expected_from_decision="queue_owner"),
                _check("boundary", "단일 책임 경계", "boundary", expected="single_owner"),
            ],
            "relevant_claim_keys": ["queue_owner"], "evidence_catalog": [], "oracle_choice": "backend",
            "decision": {
                "key": "queue_owner", "kind": "ownership", "title": "순번 계산 담당 배정",
                "question": "순번 계산의 단일 담당을 어디에 둘까요?",
                "options": [
                    _option("backend", "백엔드 담당", "백엔드가 순번을 계산하고 프론트는 결과를 표시합니다.", "backend"),
                    _option("frontend", "프론트 담당", "현재 시연 범위에서 프론트가 순번 계산을 담당합니다.", "frontend"),
                ],
            },
        },
    },
    "healthy-progress": {
        "id": "healthy-progress", "title": "정상적인 긴 작업", "category": "healthy",
        "description": "대화가 길어도 각 차례마다 검증 가능한 계약 항목을 하나씩 완성합니다.",
        "task": {
            "id": "task-healthy", "description": "여섯 항목의 대기 API 계약을 단계적으로 완성한다.",
            "goal": "프로젝트, 경로, ID 필드, 인원 필드, nullable 필드, 응답 상태를 모두 확정한다.",
            "artifact_description": "실행 코드가 아닌 대기 API 계약 JSON",
            "checklist": [
                _check("project", "프로젝트", "project", expected="waiting"),
                _check("endpoint", "API 경로", "endpoint", expected="/api/waitings"),
                _check("id", "ID 필드", "id_field", expected="id"),
                _check("party", "인원 필드", "party_field", expected="team_size"),
                _check("nullable", "호출 시각 필드", "nullable_field", expected="called_at"),
                _check("status", "응답 상태 코드", "response_status", expected=200),
            ],
            "relevant_claim_keys": ["project", "endpoint", "id_field", "party_field", "nullable_field", "response_status"],
            "evidence_catalog": [], "oracle_choice": "continue", "decision": None,
        },
    },
    "paraphrased-loop": {
        "id": "paraphrased-loop", "title": "표현만 바뀌는 반복 논쟁", "category": "factual",
        "description": "문장을 계속 바꿔도 같은 API 필드에 대한 상반된 주장이 유지됩니다.",
        "task": _api_task("task-paraphrased", "factual"),
    },
    "evidence-update": {
        "id": "evidence-update", "title": "근거 확인 후 주장 철회", "category": "evidence",
        "description": "문서 근거가 확인되면 잘못된 주장을 철회하고 추가 개입 없이 계약을 완성합니다.",
        "task": {
            "id": "task-evidence", "description": "승인된 요청당 최대 개수를 서버와 클라이언트 계약에 반영한다.",
            "goal": "endpoint=/api/waitings, limit=20, client_limit=20",
            "artifact_description": "실행 코드가 아닌 요청 한도 계약 JSON",
            "checklist": [
                _check("endpoint", "API 경로", "endpoint", expected="/api/waitings"),
                _check("limit", "서버 요청 한도", "limit", expected=20),
                _check("client-limit", "클라이언트 요청 한도", "client_limit", expected=20),
            ],
            "relevant_claim_keys": ["api.request_limit"],
            "evidence_catalog": [
                {"id": "approved-limit", "summary": "승인된 요청당 최대 개수는 20개다.", "source": "fixture://approved-limit"}
            ],
            "oracle_choice": "continue", "decision": None,
        },
    },
}


def get_scenario(identifier):
    if identifier not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {identifier}")
    return deepcopy(SCENARIOS[identifier])


def catalog():
    return [{key: value[key] for key in ("id", "title", "description", "category")} for value in SCENARIOS.values()]


def demo_event(state):
    """One synthetic agent turn, selected by state, without invented token usage."""
    scenario_id = state["scenario_id"]
    turn = state["turn"]
    selected = state.get("_decision_values", {})
    if scenario_id == "social-handoff":
        attendance = selected.get("meeting.attendance")
        if attendance is not None:
            return _event("pickle-a", "주인의 참석 응답을 기록했습니다. 다음 전달은 제가 담당합니다. 실제 외부 발송은 별도 작업입니다.",
                          claims=[_claim("meeting.attendance", attendance, "factual"), _claim("meeting.confirmation_owner", "pickle-a", "ownership")],
                          artifact={"proposed_time": "금요일 19:00", "proposed_place": "학교 앞 카페", "attendance": attendance, "followup_agent": "pickle-a"})
        agent = "pickle-a" if turn % 2 == 0 else "pickle-b"
        other = "pickle-b" if agent == "pickle-a" else "pickle-a"
        event = _event(agent, "금요일 19시 학교 앞 카페 모임을 주인에게 확인하고 알려드릴게요." if turn == 0 else "네, 주인에게 확인한 뒤 다시 알려드릴게요.",
                       claims=[_claim("meeting.confirmation_owner", other, "ownership")],
                       artifact={"proposed_time": "금요일 19:00", "proposed_place": "학교 앞 카페"} if turn == 0 else None)
        event["coordination"] = {
            "commitments": [{"id": f"promise-{agent}", "to_person": state["task"]["agent_owners"][agent], "topic": "meeting.attendance", "summary": "주인에게 참석 여부 확인 후 회신하겠다는 약속"}],
            "human_input_requests": [{"id": f"attendance-{agent}", "recipient": state["task"]["agent_owners"][agent], "topic": "meeting.attendance", "delivery_status": "unknown"}],
        }
        return event
    if scenario_id == "review-deadlock":
        owner = selected.get("review.decision_owner")
        if owner is not None:
            agent = "pickle-a" if owner == "person-a" else "pickle-b"
            event = _event(agent, "최종 책임 리뷰어를 확정하고 제안서 최종 검토를 다음 행동으로 기록했습니다.",
                           claims=[_claim("review.decision_owner", owner, "ownership")],
                           artifact={"review_target": "proposal-v1", "decision_owner": owner, "next_action": "final_review"})
            event["coordination"] = {"waits_for": [], "decision_owner": owner}
            return event
        agent = "pickle-a" if turn % 2 == 0 else "pickle-b"
        other = "pickle-b" if agent == "pickle-a" else "pickle-a"
        event = _event(agent, f"{other}가 먼저 검토해 주시면 그 결과를 보고 진행하겠습니다.",
                       claims=[_claim("review.decision_owner", "person-b" if agent == "pickle-a" else "person-a", "ownership")],
                       artifact={"review_target": "proposal-v1"} if turn == 0 else None)
        event["coordination"] = {"waits_for": [{"target": other, "reason": "먼저 검토한 결과를 기다림"}],
                                 "review_requests": [{"id": f"review-{agent}", "target": other, "artifact": "proposal-v1"}]}
        return event
    if scenario_id in {"api-contract", "paraphrased-loop"}:
        kind = "requirement" if scenario_id == "api-contract" else "factual"
        field = selected.get("api.response_field")
        if field is not None:
            return _event("frontend", f"사람의 결정을 반영해 양쪽 계약 필드를 {field}로 정리했습니다.",
                          claims=[_claim("api.response_field", field, kind)],
                          artifact={"endpoint": "/api/waitings", "response_field": field, "client_field": field})
        if turn == 0:
            return _event("backend", "서버 계약의 인원 필드는 team_size입니다.",
                          claims=[_claim("api.response_field", "team_size", kind)],
                          artifact={"endpoint": "/api/waitings", "response_field": "team_size"})
        if turn == 1:
            return _event("frontend", "클라이언트에서는 partySize를 사용하겠습니다.",
                          claims=[_claim("api.response_field", "partySize", kind)], artifact={"client_field": "partySize"})
        texts = ["이전 의견을 유지합니다. 제 필드명이 더 적절합니다.", "다른 표현으로 설명해도 같은 계약을 따르는 것이 맞습니다.", "다시 검토했지만 제 쪽 필드명을 기준으로 맞춰 주세요."]
        agent = "backend" if turn % 2 == 0 else "frontend"
        return _event(agent, texts[(turn - 2) % len(texts)],
                      claims=[_claim("api.response_field", "team_size" if agent == "backend" else "partySize", kind)])
    if scenario_id == "priority-choice":
        priority = selected.get("delivery_priority")
        if priority is not None:
            return _event("planner", "사용자가 승인한 전달 전략을 계획에 반영했습니다.",
                          claims=[_claim("delivery_priority", priority, "preference")],
                          artifact={"service": "notification", "delivery_strategy": priority, "retry_limit": 3 if priority == "reliable" else 0})
        agent = "product" if turn % 2 == 0 else "reliability"
        priority = "fast" if agent == "product" else "reliable"
        return _event(agent, "빠른 발송이 우선입니다." if priority == "fast" else "전달 신뢰성이 우선입니다.",
                      claims=[_claim("delivery_priority", priority, "preference")],
                      artifact={"service": "notification", "retry_limit": 3} if turn == 0 else None)
    if scenario_id == "ownership":
        owner = selected.get("queue_owner")
        if owner is not None:
            return _event("planner", f"{owner}를 단일 담당으로 배정했습니다.",
                          claims=[_claim("queue_owner", owner, "ownership")],
                          artifact={"service": "waiting", "queue_owner": owner, "boundary": "single_owner"})
        agent = "backend" if turn % 2 == 0 else "frontend"
        owner = "frontend" if agent == "backend" else "backend"
        return _event(agent, f"순번 계산은 {owner}의 작업입니다. 완료를 기다립니다.",
                      claims=[_claim("queue_owner", owner, "ownership")],
                      artifact={"service": "waiting", "boundary": "single_owner"} if turn == 0 else None)
    if scenario_id == "healthy-progress":
        checks = state["task"]["checklist"]
        item = checks[min(turn, len(checks) - 1)]
        return _event("backend" if turn % 2 == 0 else "frontend", f"계약의 {item['label']} 항목을 작성했습니다.",
                      claims=[_claim(item["path"], item["expected"], "factual")],
                      artifact={item["path"]: item["expected"]})
    if scenario_id == "evidence-update":
        if turn == 0:
            return _event("backend", "요청당 최대 개수는 20개로 알고 있습니다.",
                          claims=[_claim("api.request_limit", 20, "factual")], artifact={"endpoint": "/api/waitings"})
        if turn == 1:
            return _event("frontend", "이전 기억에 따르면 50개였습니다.",
                          claims=[_claim("api.request_limit", 50, "factual")],
                          evidence=[{"id": "old-memory", "summary": "이전 기억: 최대 50개", "source": ""}])
        if turn == 2:
            return _event("backend", "승인 문서의 20개 제한을 확인했습니다.",
                          claims=[_claim("api.request_limit", 20, "factual")], artifact={"limit": 20},
                          evidence=deepcopy(state["task"]["evidence_catalog"]))
        return _event("frontend", "50개라는 주장을 철회하고 20개로 수정했습니다.",
                      claims=[_claim("api.request_limit", None, "factual", action="retract"), _claim("api.request_limit", 20, "factual")],
                      evidence=[{"id": "old-memory", "action": "retract", "summary": "기억에 의존한 근거 철회", "source": ""}],
                      artifact={"client_limit": 20})
    raise ValueError(f"No demo events for scenario: {scenario_id}")
