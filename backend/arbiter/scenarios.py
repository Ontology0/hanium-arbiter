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
        "description": "Align the server and client response fields with the approved waiting API contract.",
        "goal": "endpoint=/api/waitings, response_field=team_size, client_field=team_size",
        "artifact_description": "Server/client API contract JSON, not executable code",
        "checklist": [
            _check("endpoint", "Waiting API path", "endpoint", expected="/api/waitings"),
            _check("server-field", "Approved server response field", "response_field", expected="team_size"),
            _check("client-field", "Expected client field", "client_field", expected="team_size"),
        ],
        "relevant_claim_keys": ["api.response_field"],
        "evidence_catalog": [
            {"id": "approved-contract", "summary": "The approved response field is team_size.", "source": "fixture://approved-contract"}
        ],
        "oracle_choice": "snake_case" if kind == "requirement" else "inspect_contract",
        "decision": {
            "key": "api.response_field", "kind": kind,
            "title": "Response field contract conflict", "question": "Which evidence should determine the field contract?",
            "options": [
                _option("snake_case" if kind == "requirement" else "inspect_contract", "Use the approved contract", "Align the server and client with the team_size contract.", "team_size"),
                _option("camel_case" if kind == "requirement" else "keep_client", "Keep the client proposal", "Keep partySize. This may fail the existing approved contract checks.", "partySize"),
            ],
        },
    }


SCENARIOS = {
    "social-handoff": {
        "id": "social-handoff", "title": "Promises to check with an owner", "category": "coordination",
        "description": "Personal agents repeat promises to ask their owners, but actual delivery remains unknown.",
        "task": {
            "id": "task-social", "description": "Record the proposed meeting time and place, and obtain the owner's attendance response.",
            "goal": "Record the owner's response to meeting on Friday at 19:00 at the cafe near campus, and assign a follow-up agent.",
            "artifact_description": "Meeting coordination plan JSON, not an actual message delivery",
            "people": [{"id": "person-a", "name": "Owner A"}, {"id": "person-b", "name": "Owner B"}],
            "agent_owners": {"pickle-a": "person-a", "pickle-b": "person-b"},
            "checklist": [
                _check("time", "Proposed time", "proposed_time", expected="Friday 19:00"),
                _check("place", "Proposed place", "proposed_place", expected="Campus cafe"),
                _check("attendance", "Owner's attendance response", "attendance", expected_from_decision="meeting.attendance"),
                _check("followup", "Response delivery agent", "followup_agent", expected="pickle-a"),
            ],
            "relevant_claim_keys": ["meeting.attendance", "meeting.confirmation_owner"],
            "evidence_catalog": [], "delivery_receipts": [], "oracle_choice": "available",
            "decision": {
                "key": "meeting.attendance", "kind": "coordination", "always_available": True,
                "title": "Ask the owner about attendance once",
                "question": "Can you attend a meeting on Friday at 19:00 at the cafe near campus?",
                "options": [
                    _option("available", "Available", "Record this response and assign Pickle A to relay it.", "available"),
                    _option("unavailable", "Unavailable", "Record the declined invitation and assign Pickle A to reschedule.", "unavailable"),
                ],
            },
        },
    },
    "review-deadlock": {
        "id": "review-deadlock", "title": "Mutual review waits in Slack", "category": "ownership",
        "description": "Review work stalls when agents defer to each other or lack a final decision owner.",
        "task": {
            "id": "task-review", "description": "Resolve circular review waits and assign a final accountable reviewer and next action.",
            "goal": "Record a human-selected accountable reviewer and that person's final review action.",
            "artifact_description": "Responsibility assignment plan JSON, not an actual Slack message or completed review",
            "people": [{"id": "person-a", "name": "Requester A"}, {"id": "person-b", "name": "Reviewer B"}],
            "agent_owners": {"pickle-a": "person-a", "pickle-b": "person-b"},
            "checklist": [
                _check("review", "Review target", "review_target", expected="proposal-v1"),
                _check("owner", "Final accountable reviewer", "decision_owner", expected_from_decision="review.decision_owner"),
                _check("next", "Concrete next action", "next_action", expected="final_review"),
            ],
            "relevant_claim_keys": ["review.decision_owner"], "evidence_catalog": [], "oracle_choice": "owner_a",
            "decision": {
                "key": "review.decision_owner", "kind": "ownership", "always_available": True,
                "title": "Assign the final accountable reviewer", "question": "Who should own the proposal's final review and decision?",
                "options": [
                    _option("owner_a", "Requester A decides", "Pickle A prepares the final review and Requester A decides.", "person-a"),
                    _option("owner_b", "Reviewer B decides", "Pickle B prepares the final review and Reviewer B decides.", "person-b"),
                ],
            },
        },
    },
    "api-contract": {
        "id": "api-contract", "title": "Conflicting API requirements", "category": "requirement",
        "description": "The server and client advocate different field names and overlook the approved contract.",
        "task": _api_task("task-api-contract"),
    },
    "priority-choice": {
        "id": "priority-choice", "title": "Speed versus delivery reliability", "category": "preference",
        "description": "The user chooses between notification speed and reliability through retries.",
        "task": {
            "id": "task-priority", "description": "Apply the user's approved priority to the notification delivery plan.",
            "goal": "Specify the service scope and delivery strategy, matching the strategy to the user's choice.",
            "artifact_description": "Notification delivery plan JSON, not executable code",
            "checklist": [
                _check("scope", "Notification service scope", "service", expected="notification"),
                _check("strategy", "User-approved delivery strategy", "delivery_strategy", expected_from_decision="delivery_priority"),
                _check("bounded", "Retry limit", "retry_limit", allowed=[0, 3]),
            ],
            "relevant_claim_keys": ["delivery_priority"], "evidence_catalog": [], "oracle_choice": "reliable",
            "decision": {
                "key": "delivery_priority", "kind": "preference", "title": "Choose a notification priority",
                "question": "Which delivery strategy should this task prioritize?",
                "options": [
                    _option("fast", "Fast attempt", "Approve a single delivery attempt with no retries.", "fast"),
                    _option("reliable", "Reliability through retries", "Approve a plan with up to three retries.", "reliable"),
                ],
            },
        },
    },
    "ownership": {
        "id": "ownership", "title": "Passing responsibility around", "category": "ownership",
        "description": "Agents wait for each other because no one owns queue-position calculation.",
        "task": {
            "id": "task-ownership", "description": "Create a work plan with one accountable owner for queue-position calculation.",
            "goal": "Specify a single responsibility boundary for the waiting service and record the approved owner.",
            "artifact_description": "Responsibility assignment plan JSON, not executable code",
            "checklist": [
                _check("service", "Waiting service", "service", expected="waiting"),
                _check("owner", "Approved queue-position owner", "queue_owner", expected_from_decision="queue_owner"),
                _check("boundary", "Single responsibility boundary", "boundary", expected="single_owner"),
            ],
            "relevant_claim_keys": ["queue_owner"], "evidence_catalog": [], "oracle_choice": "backend",
            "decision": {
                "key": "queue_owner", "kind": "ownership", "title": "Assign queue-position responsibility",
                "question": "Which side should own queue-position calculation?",
                "options": [
                    _option("backend", "Backend owns it", "The backend calculates positions and the frontend displays the results.", "backend"),
                    _option("frontend", "Frontend owns it", "The frontend calculates positions within this demo's scope.", "frontend"),
                ],
            },
        },
    },
    "healthy-progress": {
        "id": "healthy-progress", "title": "Healthy progress over many turns", "category": "healthy",
        "description": "A long conversation completes one verifiable contract item on each turn.",
        "task": {
            "id": "task-healthy", "description": "Complete a six-item waiting API contract step by step.",
            "goal": "Define the project, path, ID field, party-size field, nullable field, and response status.",
            "artifact_description": "Waiting API contract JSON, not executable code",
            "checklist": [
                _check("project", "Project", "project", expected="waiting"),
                _check("endpoint", "API path", "endpoint", expected="/api/waitings"),
                _check("id", "ID field", "id_field", expected="id"),
                _check("party", "Party-size field", "party_field", expected="team_size"),
                _check("nullable", "Call-time field", "nullable_field", expected="called_at"),
                _check("status", "Response status code", "response_status", expected=200),
            ],
            "relevant_claim_keys": ["project", "endpoint", "id_field", "party_field", "nullable_field", "response_status"],
            "evidence_catalog": [], "oracle_choice": "continue", "decision": None,
        },
    },
    "paraphrased-loop": {
        "id": "paraphrased-loop", "title": "The same disagreement in new words", "category": "factual",
        "description": "Conflicting claims about the same API field persist despite repeated paraphrasing.",
        "task": _api_task("task-paraphrased", "factual"),
    },
    "evidence-update": {
        "id": "evidence-update", "title": "Retracting a claim after checking evidence", "category": "evidence",
        "description": "Documentary evidence leads to a claim retraction and contract completion without additional intervention.",
        "task": {
            "id": "task-evidence", "description": "Apply the approved per-request item limit to the server and client contracts.",
            "goal": "endpoint=/api/waitings, limit=20, client_limit=20",
            "artifact_description": "Request-limit contract JSON, not executable code",
            "checklist": [
                _check("endpoint", "API path", "endpoint", expected="/api/waitings"),
                _check("limit", "Server request limit", "limit", expected=20),
                _check("client-limit", "Client request limit", "client_limit", expected=20),
            ],
            "relevant_claim_keys": ["api.request_limit"],
            "evidence_catalog": [
                {"id": "approved-limit", "summary": "The approved maximum is 20 items per request.", "source": "fixture://approved-limit"}
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
            return _event("pickle-a", "I recorded the owner's attendance response and will handle the follow-up. Actual external delivery is a separate task.",
                          claims=[_claim("meeting.attendance", attendance, "factual"), _claim("meeting.confirmation_owner", "pickle-a", "ownership")],
                          artifact={"proposed_time": "Friday 19:00", "proposed_place": "Campus cafe", "attendance": attendance, "followup_agent": "pickle-a"})
        agent = "pickle-a" if turn % 2 == 0 else "pickle-b"
        other = "pickle-b" if agent == "pickle-a" else "pickle-a"
        event = _event(agent, "I will ask my owner about meeting on Friday at 19:00 at the cafe near campus and let you know." if turn == 0 else "Yes, I will check with my owner and get back to you.",
                       claims=[_claim("meeting.confirmation_owner", other, "ownership")],
                       artifact={"proposed_time": "Friday 19:00", "proposed_place": "Campus cafe"} if turn == 0 else None)
        event["coordination"] = {
            "commitments": [{"id": f"promise-{agent}", "to_person": state["task"]["agent_owners"][agent], "topic": "meeting.attendance", "summary": "A promise to ask the owner about attendance and reply"}],
            "human_input_requests": [{"id": f"attendance-{agent}", "recipient": state["task"]["agent_owners"][agent], "topic": "meeting.attendance", "delivery_status": "unknown"}],
        }
        return event
    if scenario_id == "review-deadlock":
        owner = selected.get("review.decision_owner")
        if owner is not None:
            agent = "pickle-a" if owner == "person-a" else "pickle-b"
            event = _event(agent, "I recorded the final accountable reviewer and listed the proposal's final review as the next action.",
                           claims=[_claim("review.decision_owner", owner, "ownership")],
                           artifact={"review_target": "proposal-v1", "decision_owner": owner, "next_action": "final_review"})
            event["coordination"] = {"waits_for": [], "decision_owner": owner}
            return event
        agent = "pickle-a" if turn % 2 == 0 else "pickle-b"
        other = "pickle-b" if agent == "pickle-a" else "pickle-a"
        event = _event(agent, f"I will proceed after {other} reviews it first and shares the result.",
                       claims=[_claim("review.decision_owner", "person-b" if agent == "pickle-a" else "person-a", "ownership")],
                       artifact={"review_target": "proposal-v1"} if turn == 0 else None)
        event["coordination"] = {"waits_for": [{"target": other, "reason": "Waiting for the initial review result"}],
                                 "review_requests": [{"id": f"review-{agent}", "target": other, "artifact": "proposal-v1"}]}
        return event
    if scenario_id in {"api-contract", "paraphrased-loop"}:
        kind = "requirement" if scenario_id == "api-contract" else "factual"
        field = selected.get("api.response_field")
        if field is not None:
            return _event("frontend", f"Following the human decision, I aligned both contract fields to {field}.",
                          claims=[_claim("api.response_field", field, kind)],
                          artifact={"endpoint": "/api/waitings", "response_field": field, "client_field": field})
        if turn == 0:
            return _event("backend", "The server contract uses team_size for the party-size field.",
                          claims=[_claim("api.response_field", "team_size", kind)],
                          artifact={"endpoint": "/api/waitings", "response_field": "team_size"})
        if turn == 1:
            return _event("frontend", "The client will use partySize.",
                          claims=[_claim("api.response_field", "partySize", kind)], artifact={"client_field": "partySize"})
        texts = ["I stand by my earlier view. My field name is more appropriate.", "Even expressed differently, the same contract should apply.", "I reviewed it again; please align with my field name."]
        agent = "backend" if turn % 2 == 0 else "frontend"
        return _event(agent, texts[(turn - 2) % len(texts)],
                      claims=[_claim("api.response_field", "team_size" if agent == "backend" else "partySize", kind)])
    if scenario_id == "priority-choice":
        priority = selected.get("delivery_priority")
        if priority is not None:
            return _event("planner", "I incorporated the user's approved delivery strategy into the plan.",
                          claims=[_claim("delivery_priority", priority, "preference")],
                          artifact={"service": "notification", "delivery_strategy": priority, "retry_limit": 3 if priority == "reliable" else 0})
        agent = "product" if turn % 2 == 0 else "reliability"
        priority = "fast" if agent == "product" else "reliable"
        return _event(agent, "Fast delivery comes first." if priority == "fast" else "Delivery reliability comes first.",
                      claims=[_claim("delivery_priority", priority, "preference")],
                      artifact={"service": "notification", "retry_limit": 3} if turn == 0 else None)
    if scenario_id == "ownership":
        owner = selected.get("queue_owner")
        if owner is not None:
            return _event("planner", f"I assigned {owner} as the sole owner.",
                          claims=[_claim("queue_owner", owner, "ownership")],
                          artifact={"service": "waiting", "queue_owner": owner, "boundary": "single_owner"})
        agent = "backend" if turn % 2 == 0 else "frontend"
        owner = "frontend" if agent == "backend" else "backend"
        return _event(agent, f"Queue-position calculation belongs to {owner}. I am waiting for it to finish.",
                      claims=[_claim("queue_owner", owner, "ownership")],
                      artifact={"service": "waiting", "boundary": "single_owner"} if turn == 0 else None)
    if scenario_id == "healthy-progress":
        checks = state["task"]["checklist"]
        item = checks[min(turn, len(checks) - 1)]
        return _event("backend" if turn % 2 == 0 else "frontend", f"I completed the contract's {item['label']} item.",
                      claims=[_claim(item["path"], item["expected"], "factual")],
                      artifact={item["path"]: item["expected"]})
    if scenario_id == "evidence-update":
        if turn == 0:
            return _event("backend", "I understand the maximum to be 20 items per request.",
                          claims=[_claim("api.request_limit", 20, "factual")], artifact={"endpoint": "/api/waitings"})
        if turn == 1:
            return _event("frontend", "From memory, the limit was 50 items.",
                          claims=[_claim("api.request_limit", 50, "factual")],
                          evidence=[{"id": "old-memory", "summary": "Prior memory: a maximum of 50 items", "source": ""}])
        if turn == 2:
            return _event("backend", "I checked the approved document's limit of 20 items.",
                          claims=[_claim("api.request_limit", 20, "factual")], artifact={"limit": 20},
                          evidence=deepcopy(state["task"]["evidence_catalog"]))
        return _event("frontend", "I retracted the claim of 50 items and corrected it to 20.",
                      claims=[_claim("api.request_limit", None, "factual", action="retract"), _claim("api.request_limit", 20, "factual")],
                      evidence=[{"id": "old-memory", "action": "retract", "summary": "Retracted memory-based evidence", "source": ""}],
                      artifact={"client_limit": 20})
    raise ValueError(f"No demo events for scenario: {scenario_id}")
