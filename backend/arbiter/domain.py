"""Pure-dictionary HITL state machine and an explicit, lightweight ontology.

This module uses typed entities and deterministic relationships, not an OWL
reasoner. Only the local artifact validator can create VERIFIED evidence. An
agent's assertions, references and claims of successful execution are untrusted.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Literal, TypedDict
from uuid import uuid4

from .scenarios import catalog, demo_event, get_scenario


ConflictKind = Literal["factual", "requirement", "preference", "ownership"]
EvidenceGrade = Literal["CLAIMED", "REFERENCED", "VERIFIED"]


class Agent(TypedDict):
    id: str
    type: Literal["Agent"]
    label: str


class Person(TypedDict):
    id: str
    type: Literal["Person"]
    name: str


class Commitment(TypedDict):
    id: str
    type: Literal["Commitment"]
    agent: str
    to_person: str
    topic: str
    status: Literal["promised"]


class HumanInputRequest(TypedDict):
    id: str
    type: Literal["HumanInputRequest"]
    recipient: str
    topic: str
    delivery_status: Literal["unknown", "delivered"]
    status: Literal["pending", "answered"]


class ReviewRequest(TypedDict):
    id: str
    type: Literal["ReviewRequest"]
    target: str
    artifact: str


class DecisionOwner(TypedDict):
    id: str
    type: Literal["DecisionOwner"]
    person_id: str


class Task(TypedDict):
    id: str
    type: Literal["Task"]
    description: str
    checklist: list[dict[str, Any]]


class Claim(TypedDict):
    id: str
    type: Literal["Claim"]
    agent: str
    key: str
    value: Any
    kind: ConflictKind
    scope: str
    status: Literal["active", "superseded", "retracted"]


class Evidence(TypedDict):
    id: str
    type: Literal["Evidence"]
    summary: str
    source: str
    grade: EvidenceGrade
    status: Literal["active", "retracted"]


class Decision(TypedDict):
    id: str
    type: Literal["Decision"]
    request_id: str
    choice: str
    note: str
    turn: int


class Artifact(TypedDict):
    id: str
    type: Literal["Artifact"]
    data: dict[str, Any]


ONTOLOGY = {
    "name": "HITL lightweight task ontology",
    "version": "1.0",
    "reasoning": "Deterministic scoped claim comparison and local JSON artifact validation; no OWL inference.",
    "classes": ["Person", "Agent", "Task", "Claim", "Evidence", "Decision", "Artifact", "Commitment", "HumanInputRequest", "ReviewRequest", "DecisionOwner"],
    "relations": {
        "worksOn": {"domain": "Agent", "range": "Task"},
        "asserts": {"domain": "Agent", "range": "Claim"},
        "about": {"domain": "Claim", "range": "Task"},
        "supportedBy": {"domain": "Claim", "range": "Evidence"},
        "conflictsWith": {"domain": "Claim", "range": "Claim"},
        "supersedes": {"domain": "Claim", "range": "Claim"},
        "addresses": {"domain": "Decision", "range": "Task"},
        "resolves": {"domain": "Decision", "range": "Claim"},
        "contributesTo": {"domain": "Agent", "range": "Artifact"},
        "forTask": {"domain": "Artifact", "range": "Task"},
        "verifies": {"domain": "Evidence", "range": "Artifact"},
        "represents": {"domain": "Agent", "range": "Person"},
        "promises": {"domain": "Agent", "range": "Commitment"},
        "promisedTo": {"domain": "Commitment", "range": "Person"},
        "requestsInput": {"domain": "Agent", "range": "HumanInputRequest"},
        "addressedTo": {"domain": "HumanInputRequest", "range": "Person"},
        "requestsReview": {"domain": "Agent", "range": "ReviewRequest"},
        "reviewAssignedTo": {"domain": "ReviewRequest", "range": "Agent"},
        "waits_for": {"domain": "Agent", "range": "Agent"},
        "fillsRole": {"domain": "Person", "range": "DecisionOwner"},
        "accountableFor": {"domain": "DecisionOwner", "range": "Task"},
    },
}

_KINDS = {"factual", "requirement", "preference", "ownership"}
_POLICIES = {"capped", "periodic", "adaptive"}
_MISSING = object()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _same(left: Any, right: Any) -> bool:
    return _canonical(left) == _canonical(right)


def _path(data: dict, path: str) -> Any:
    value = data
    for segment in path.split("."):
        if not isinstance(value, dict) or segment not in value:
            return _MISSING
        value = value[segment]
    return value


def _merge(target: dict, incoming: dict) -> None:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = deepcopy(value)


def scenario_catalog() -> list[dict]:
    return catalog()


def create_state(scenario_id: str, policy: str = "adaptive", mode: str = "demo", max_turns: int = 18,
                 periodic_every: int = 4, stall_window: int = 3) -> dict:
    if policy not in _POLICIES:
        raise ValueError(f"Unknown policy: {policy}")
    for name, value in (("max_turns", max_turns), ("periodic_every", periodic_every), ("stall_window", stall_window)):
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    scenario = get_scenario(scenario_id)
    task = scenario["task"]
    task["type"] = "Task"
    task.setdefault("scope", "waiting-api")
    return {
        "id": str(uuid4()), "scenario_id": scenario_id, "title": scenario["title"],
        "description": scenario["description"], "category": scenario["category"],
        "policy": policy, "mode": mode, "status": "running", "turn": 0,
        "max_turns": max_turns, "periodic_every": periodic_every, "stall_window": stall_window,
        "messages": [], "requests": [], "decisions": [], "claims": [], "evidence": [], "artifact": {},
        "metrics": {
            "input_tokens": 0, "output_tokens": 0, "measured_calls": 0, "unmetered_calls": 0,
            "human_requests": 0, "progress_events": 0, "success": False,
        },
        "detector": {"stalled_turns": 0, "reason": "아직 에이전트 작업이 없습니다.", "conflicts": []},
        "task": task,
        "_decision_values": {},
        "_progress": {"seen_passed_checks": [], "seen_references": [], "epoch": 0},
        "_last_request": None,
        "_artifact_revision": 0,
        "coordination": {"commitments": [], "human_input_requests": [], "review_requests": [], "waits_for": [], "decision_owner": None},
    }


def next_demo_event(state: dict) -> dict:
    if state["status"] != "running":
        raise ValueError("Only a running state can produce the next demo event")
    if state["turn"] >= state["max_turns"]:
        raise ValueError("The cumulative turn budget is exhausted")
    return demo_event(state)


def evaluate_state(state: dict) -> dict:
    """Validate actual JSON artifact fields; agent completion claims have no effect."""
    checks = []
    artifact = state.get("artifact", {})
    decisions = state.get("_decision_values", {})
    for rule in state["task"]["checklist"]:
        actual = _path(artifact, rule["path"])
        missing = actual is _MISSING
        expected = _MISSING
        rule_name = "expected"
        if "expected_from_decision" in rule:
            expected = decisions.get(rule["expected_from_decision"], _MISSING)
            passed = not missing and expected is not _MISSING and _same(actual, expected)
            rule_name = "approved_decision"
        elif "equals_path" in rule:
            expected = _path(artifact, rule["equals_path"])
            passed = not missing and expected is not _MISSING and _same(actual, expected)
            rule_name = "equals_path"
        elif "allowed" in rule:
            expected = rule["allowed"]
            passed = not missing and any(_same(actual, item) for item in expected)
            rule_name = "allowed"
        else:
            expected = rule.get("expected", _MISSING)
            passed = not missing and expected is not _MISSING and _same(actual, expected)
        checks.append({
            "id": rule["id"], "label": rule["label"], "path": rule["path"], "rule": rule_name,
            "passed": bool(passed), "actual": None if missing else deepcopy(actual),
            "expected": None if expected is _MISSING else deepcopy(expected),
            "missing": missing, "requires_decision": "expected_from_decision" in rule and expected is _MISSING,
        })
    passed = sum(item["passed"] for item in checks)
    return {
        "success": bool(checks) and passed == len(checks), "passed": passed, "total": len(checks),
        "checks": checks, "turn": state["turn"], "status": state["status"],
        "scope": "Local JSON contract/work-plan constraints only; no execution or general code correctness claim.",
        "metrics": deepcopy(state.get("metrics", {})),
    }


def _normalize_event(event: dict) -> dict:
    if not isinstance(event, dict):
        raise ValueError("An event must be a JSON object")
    result = deepcopy(event)
    if not isinstance(result.get("agent"), str) or not result["agent"].strip():
        raise ValueError("An event needs a nonempty agent")
    if not isinstance(result.get("content", ""), str):
        raise ValueError("Event content must be text")
    result.setdefault("content", "")
    for field in ("claims", "evidence"):
        if result.get(field) is None:
            result[field] = []
        result.setdefault(field, [])
        if not isinstance(result[field], list):
            raise ValueError(f"{field} must be a list")
    if result.get("artifact") is not None and not isinstance(result["artifact"], dict):
        raise ValueError("Event artifact must be an object or null")
    for claim in result["claims"]:
        if not isinstance(claim, dict) or not isinstance(claim.get("key"), str) or not claim["key"]:
            raise ValueError("Each claim needs a nonempty key")
        if claim.get("kind", "factual") not in _KINDS:
            raise ValueError("Unknown claim kind")
        if claim.get("action", "assert") not in {"assert", "retract"}:
            raise ValueError("Unknown claim action")
        if claim.get("action", "assert") == "assert" and "value" not in claim:
            raise ValueError("An asserted claim needs a value")
        if "scope" in claim and not isinstance(claim["scope"], str):
            raise ValueError("Claim scope must be text")
        if "evidence_ids" in claim and (not isinstance(claim["evidence_ids"], list) or any(not isinstance(i, str) for i in claim["evidence_ids"])):
            raise ValueError("Claim evidence_ids must be a list of strings")
    for evidence in result["evidence"]:
        if not isinstance(evidence, dict):
            raise ValueError("Each evidence item must be an object")
        if "id" in evidence and not isinstance(evidence["id"], str):
            raise ValueError("Evidence id must be text")
        if not isinstance(evidence.get("summary", ""), str) or not isinstance(evidence.get("source", ""), str):
            raise ValueError("Evidence summary and source must be text")
        if evidence.get("action", "assert") not in {"assert", "retract"}:
            raise ValueError("Unknown evidence action")
    for field in ("input_tokens", "output_tokens"):
        value = result.get(field)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("Token counts must be nonnegative integers or null")
    if result.get("usage_source", "unavailable") not in {"measured", "unavailable"}:
        raise ValueError("Unknown usage_source")
    coordination = result.get("coordination", {})
    if not isinstance(coordination, dict):
        raise ValueError("coordination must be an object")
    for field in ("commitments", "human_input_requests", "review_requests", "waits_for"):
        if field in coordination and (not isinstance(coordination[field], list) or any(not isinstance(item, dict) for item in coordination[field])):
            raise ValueError(f"coordination.{field} must be a list of objects")
    for field, required in (("commitments", ("id", "to_person", "topic")), ("human_input_requests", ("id", "recipient", "topic")), ("review_requests", ("id", "target", "artifact")), ("waits_for", ("target",))):
        for item in coordination.get(field, []):
            if any(not isinstance(item.get(key), str) or not item[key] for key in required):
                raise ValueError(f"coordination.{field} needs nonempty text fields: {required}")
    try:
        _canonical(result)
    except (TypeError, ValueError) as exc:
        raise ValueError("Events must contain finite JSON values") from exc
    return result


def _ingest_evidence(state: dict, event: dict) -> tuple[list[str], list[str]]:
    evidence_ids, new_references = [], []
    registry = {item["id"]: item for item in state["task"].get("evidence_catalog", [])}
    for incoming in event["evidence"]:
        external_id = incoming.get("id") or sha256(_canonical(incoming).encode()).hexdigest()[:16]
        existing = next((item for item in reversed(state["evidence"]) if item.get("external_id") == external_id and item.get("agent") == event["agent"] and item.get("origin") == "agent"), None)
        if incoming.get("action") == "retract":
            if existing:
                existing["status"] = "retracted"
                existing["retracted_turn"] = state["turn"]
            continue
        summary, source = incoming.get("summary", ""), incoming.get("source", "")
        if existing and existing["status"] == "active" and existing["summary"] == summary and existing["source"] == source:
            evidence_ids.append(existing["id"])
            continue
        if existing:
            existing["status"] = "retracted"
            existing["retracted_turn"] = state["turn"]
        known = registry.get(external_id)
        relevant = bool(known and known["summary"] == summary and known["source"] == source)
        item = {
            "id": f"evidence-{len(state['evidence']) + 1}", "type": "Evidence", "external_id": external_id,
            "agent": event["agent"], "summary": summary, "source": source,
            "grade": "REFERENCED" if source else "CLAIMED", "status": "active", "origin": "agent",
            "turn": state["turn"], "relevant": relevant,
        }
        state["evidence"].append(item)
        evidence_ids.append(item["id"])
        if relevant and external_id not in state["_progress"]["seen_references"]:
            state["_progress"]["seen_references"].append(external_id)
            new_references.append(external_id)
    return evidence_ids, new_references


def _ingest_claims(state: dict, event: dict, evidence_ids: list[str]) -> list[str]:
    result = []
    for incoming in event["claims"]:
        scope = incoming.get("scope", state["task"]["scope"])
        previous = [claim for claim in state["claims"] if claim["agent"] == event["agent"] and claim["key"] == incoming["key"] and claim["scope"] == scope and claim["status"] == "active"]
        if incoming.get("action") == "retract":
            for claim in previous:
                claim["status"] = "retracted"
                claim["retracted_turn"] = state["turn"]
            continue
        if previous and _same(previous[-1]["value"], incoming["value"]) and previous[-1]["kind"] == incoming.get("kind", "factual"):
            previous[-1]["last_seen_turn"] = state["turn"]
            previous[-1]["evidence_ids"] = list(dict.fromkeys(previous[-1].get("evidence_ids", []) + evidence_ids))
            result.append(previous[-1]["id"])
            continue
        for claim in previous:
            claim["status"] = "superseded"
            claim["superseded_turn"] = state["turn"]
        declared_evidence = incoming.get("evidence_ids", [])
        linked = list(evidence_ids)
        for item in state["evidence"]:
            if item["status"] == "active" and (item["id"] in declared_evidence or item.get("external_id") in declared_evidence):
                linked.append(item["id"])
        claim = {
            "id": f"claim-{len(state['claims']) + 1}", "type": "Claim", "agent": event["agent"],
            "key": incoming["key"], "value": deepcopy(incoming["value"]), "kind": incoming.get("kind", "factual"),
            "scope": scope, "status": "active", "turn": state["turn"], "last_seen_turn": state["turn"],
            "evidence_ids": list(dict.fromkeys(linked)), "supersedes": [item["id"] for item in previous],
            "relevant": incoming["key"] in state["task"].get("relevant_claim_keys", []),
        }
        state["claims"].append(claim)
        result.append(claim["id"])
    return result


def _detect_conflicts(state: dict) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for claim in state["claims"]:
        if claim["status"] == "active":
            groups.setdefault((claim["scope"], claim["key"]), []).append(claim)
    conflicts = []
    for (scope, key), claims in sorted(groups.items()):
        values = {_canonical(claim["value"]) for claim in claims}
        if len(values) < 2 or len({claim["agent"] for claim in claims}) < 2:
            continue
        signature = _canonical([scope, key, sorted(values)])
        kinds = sorted({claim["kind"] for claim in claims})
        resolved = key in state.get("_decision_values", {}) and scope == state["task"]["scope"]
        conflicts.append({
            "id": "conflict-" + sha256(signature.encode()).hexdigest()[:12], "key": key, "scope": scope,
            "kind": kinds[0] if len(kinds) == 1 else "requirement" if "requirement" in kinds else kinds[0],
            "kinds": kinds, "claim_ids": [claim["id"] for claim in claims],
            "agents": sorted({claim["agent"] for claim in claims}),
            "values": [json.loads(value) for value in sorted(values)],
            "status": "decision_recorded" if resolved else "open",
            "summary": f"{scope}의 {key}에 대해 {len(values)}개 값이 충돌합니다.",
            "relevant": any(claim["relevant"] for claim in claims),
        })
    return conflicts


def _record_validation(state: dict, validation: dict) -> None:
    state["_artifact_revision"] += 1
    artifact_hash = sha256(_canonical(state["artifact"]).encode()).hexdigest()
    state["evidence"].append({
        "id": f"evidence-{len(state['evidence']) + 1}", "type": "Evidence", "origin": "local_validator",
        "summary": f"로컬 계약 검사 {validation['passed']}/{validation['total']} 통과",
        "source": "local://artifact-validator", "grade": "VERIFIED", "status": "active", "relevant": True,
        "turn": state["turn"], "artifact_hash": artifact_hash, "artifact_revision": state["_artifact_revision"],
        "checks": deepcopy(validation["checks"]),
        "artifact_snapshot": deepcopy(state["artifact"]),
        "scope": "JSON artifact constraints; not application execution",
    })


def _ingest_coordination(state: dict, event: dict) -> None:
    incoming = event.get("coordination", {})
    current = state["coordination"]
    agent = event["agent"]
    for commitment in incoming.get("commitments", []):
        existing = next((item for item in current["commitments"] if item["id"] == commitment["id"] and item["agent"] == agent), None)
        if existing:
            existing["last_seen_turn"] = state["turn"]
            continue
        current["commitments"].append({
            "id": commitment["id"], "type": "Commitment", "agent": agent,
            "to_person": commitment["to_person"], "topic": commitment["topic"],
            "summary": commitment.get("summary", "확인 후 회신하겠다는 약속"),
            "status": "promised", "created_turn": state["turn"], "last_seen_turn": state["turn"],
        })
    for request in incoming.get("human_input_requests", []):
        existing = next((item for item in current["human_input_requests"] if item["id"] == request["id"] and item["agent"] == agent), None)
        # The agent cannot verify its own delivery claim. Only a separately
        # registered receipt can establish delivery; a transcript quote cannot.
        receipt = next((item for item in state["task"].get("delivery_receipts", [])
                        if item.get("id") == request.get("delivery_receipt_id")
                        and item.get("request_id") == request["id"]
                        and item.get("recipient") == request["recipient"]
                        and item.get("topic") == request["topic"]), None)
        item = {
            "id": request["id"], "type": "HumanInputRequest", "agent": agent,
            "recipient": request["recipient"], "topic": request["topic"],
            "delivery_status": "delivered" if receipt else "unknown",
            "reported_delivery_status": request.get("delivery_status", "unknown"),
            "delivery_receipt_id": receipt["id"] if receipt else None,
            "status": "answered" if request["topic"] in state["_decision_values"] else "pending",
            "created_turn": existing["created_turn"] if existing else state["turn"],
        }
        if existing:
            if existing["delivery_status"] == "delivered" and not receipt:
                item["delivery_status"] = "delivered"
                item["delivery_receipt_id"] = existing["delivery_receipt_id"]
            existing.update(item)
        else:
            current["human_input_requests"].append(item)
    for request in incoming.get("review_requests", []):
        existing = next((item for item in current["review_requests"] if item["id"] == request["id"] and item["agent"] == agent), None)
        if not existing:
            current["review_requests"].append({**deepcopy(request), "type": "ReviewRequest", "agent": agent, "status": "pending", "created_turn": state["turn"]})
    if "waits_for" in incoming:
        current["waits_for"] = [item for item in current["waits_for"] if item["source"] != agent]
        current["waits_for"].extend({"source": agent, "target": item["target"], "reason": item.get("reason", "리뷰 대기")} for item in incoming["waits_for"])
    owner = state["_decision_values"].get("review.decision_owner")
    if owner is not None:
        current["decision_owner"] = owner
        current["waits_for"] = []
        for request in current["review_requests"]:
            request["status"] = "owner_assigned"


def _update_coordination_detector(state: dict) -> None:
    current = state["coordination"]
    pending = [item for item in current["human_input_requests"] if item["status"] == "pending"]
    delivered = [item for item in pending if item["delivery_status"] == "delivered"]
    unknown = [item for item in pending if item["delivery_status"] == "unknown"]
    adjacency: dict[str, list[str]] = {}
    for item in current["waits_for"]:
        adjacency.setdefault(item["source"], []).append(item["target"])
    cycles = []
    visited, active = set(), []
    def visit(node):
        if node in active:
            cycle = active[active.index(node):] + [node]
            if cycle not in cycles:
                cycles.append(cycle)
            return
        if node in visited:
            return
        active.append(node)
        for target in adjacency.get(node, []):
            visit(target)
        active.pop()
        visited.add(node)
    for node in adjacency:
        visit(node)
    intentional_wait = bool(delivered) and not unknown and not cycles
    state["detector"]["intentional_human_wait"] = intentional_wait
    state["detector"]["delivery_unknown"] = bool(unknown)
    state["detector"]["wait_cycles"] = cycles
    state["detector"]["missing_decision_owner"] = bool(current["review_requests"] and not current["decision_owner"])
    if intentional_wait:
        state["detector"]["reason"] = "독립된 전달 기록을 확인했습니다. 사람의 응답을 기다리는 상태이며 대화 반복으로 단정하지 않습니다."
    elif unknown:
        state["detector"]["reason"] += " 주인에게 확인하겠다는 약속은 있으나 요청 전달 여부는 확인되지 않았습니다."
    elif cycles:
        state["detector"]["reason"] += " 리뷰 대기가 순환하며 최종 결정 담당이 필요합니다."


def _request_intervention(state: dict, trigger: str) -> None:
    if state["status"] != "running" or any(item["status"] == "pending" for item in state["requests"]):
        return
    conflicts = state["detector"]["conflicts"]
    decision = state["task"].get("decision")
    specific = decision and (decision.get("always_available") or any(item["key"] == decision["key"] and item["scope"] == state["task"]["scope"] for item in conflicts))
    signature = _canonical([trigger, [(item["scope"], item["key"], item["values"]) for item in conflicts]])
    marker = {"signature": signature, "epoch": state["_progress"]["epoch"]}
    if state.get("_last_request") == marker:
        return
    if specific:
        options = deepcopy(decision["options"])
        title, question, kind = decision["title"], decision["question"], decision["kind"]
        decision_key = decision["key"]
    else:
        options = [
            {"id": "continue", "label": "작업 계속", "description": "현재 목표를 유지하고 다음 검증 가능한 산출물을 요청합니다."},
            {"id": "stop", "label": "작업 종료", "description": "현재 실행을 종료합니다. 완료로 처리하지 않습니다."},
        ]
        title = "정기 진행 확인" if trigger == "periodic" else "작업 정체 확인"
        question, kind, decision_key = "현재 작업을 계속할까요?", "checkpoint" if trigger == "periodic" else "stagnation", None
    request = {
        "id": f"request-{len(state['requests']) + 1}", "status": "pending", "kind": kind,
        "title": title, "summary": state["detector"]["reason"], "question": question, "options": options,
        "evidence_ids": [item["id"] for item in state["evidence"] if item["status"] == "active" and item.get("relevant")][-8:],
        "created_turn": state["turn"], "trigger": trigger, "decision_key": decision_key,
        "conflict_ids": [item["id"] for item in conflicts],
        "claim_ids": [identifier for item in conflicts for identifier in item["claim_ids"]],
    }
    state["requests"].append(request)
    state["metrics"]["human_requests"] += 1
    state["status"] = "waiting"
    state["_last_request"] = marker


def ingest_event(state: dict, event: dict) -> dict:
    if state["status"] != "running":
        raise ValueError("Events can only be ingested while running")
    if state["turn"] >= state["max_turns"]:
        raise ValueError("The cumulative turn budget is exhausted")
    event = _normalize_event(event)  # Validate before changing the state.
    before_artifact = _canonical(state["artifact"])
    state["turn"] += 1
    evidence_ids, new_references = _ingest_evidence(state, event)
    claim_ids = _ingest_claims(state, event, evidence_ids)
    _ingest_coordination(state, event)
    if event.get("artifact") is not None:
        _merge(state["artifact"], event["artifact"])
    measured = event.get("usage_source") == "measured" and all(type(event.get(key)) is int for key in ("input_tokens", "output_tokens"))
    if measured:
        state["metrics"]["measured_calls"] += 1
        state["metrics"]["input_tokens"] += event["input_tokens"]
        state["metrics"]["output_tokens"] += event["output_tokens"]
    else:
        state["metrics"]["unmetered_calls"] += 1
    validation = evaluate_state(state)
    if before_artifact != _canonical(state["artifact"]):
        _record_validation(state, validation)
    newly_passed = [item["id"] for item in validation["checks"] if item["passed"] and item["id"] not in state["_progress"]["seen_passed_checks"]]
    state["_progress"]["seen_passed_checks"].extend(newly_passed)
    progress = bool(newly_passed or new_references)
    if progress:
        state["metrics"]["progress_events"] += 1
        state["_progress"]["epoch"] += 1
        state["detector"]["stalled_turns"] = 0
        state["detector"]["reason"] = f"새 검사항목 {len(newly_passed)}개·관련 근거 {len(new_references)}개로 진전했습니다."
    else:
        state["detector"]["stalled_turns"] += 1
        state["detector"]["reason"] = f"검증 가능한 새 진전 없이 {state['detector']['stalled_turns']}차례가 이어졌습니다."
    state["detector"]["conflicts"] = _detect_conflicts(state)
    _update_coordination_detector(state)
    state["detector"]["last_progress"] = {"check_ids": newly_passed, "reference_ids": new_references}
    state["metrics"]["success"] = validation["success"]
    state["messages"].append({
        **event, "id": f"message-{len(state['messages']) + 1}", "turn": state["turn"],
        "claim_ids": claim_ids, "evidence_ids": evidence_ids, "progress": progress,
        "input_tokens": event.get("input_tokens") if measured else None,
        "output_tokens": event.get("output_tokens") if measured else None,
        "usage_source": "measured" if measured else "unavailable",
        "validation": {"passed": validation["passed"], "total": validation["total"]},
    })
    if validation["success"]:
        state["status"] = "completed"
        state["detector"]["reason"] = "모든 로컬 계약 검사가 통과했습니다."
    elif state["turn"] >= state["max_turns"]:
        state["status"] = "budget_exhausted"
        state["detector"]["reason"] = "누적 대화 상한에 도달했습니다. 완료되지 않은 상태로 종료합니다."
    elif state["policy"] == "periodic" and state["turn"] % state["periodic_every"] == 0:
        _request_intervention(state, "periodic")
    elif state["policy"] == "adaptive" and not state["detector"].get("intentional_human_wait") and state["detector"]["stalled_turns"] >= state["stall_window"]:
        _request_intervention(state, "adaptive")
    return state


def apply_decision(state: dict, request_id: str, choice: str, note: str = "") -> dict:
    if not isinstance(note, str):
        raise ValueError("Decision note must be text")
    request = next((item for item in state["requests"] if item["id"] == request_id), None)
    if state["status"] != "waiting" or request is None or request["status"] != "pending":
        raise ValueError("The decision request is stale, missing, or already resolved")
    option = next((item for item in request["options"] if item["id"] == choice), None)
    if option is None:
        raise ValueError("Choice is not one of this request's options")
    request["status"] = "resolved"
    request["resolved_turn"] = state["turn"]
    request["choice"] = choice
    decision = {
        "id": f"decision-{len(state['decisions']) + 1}", "type": "Decision", "request_id": request_id,
        "choice": choice, "note": note, "turn": state["turn"], "decision_key": request.get("decision_key"),
        "claim_ids": list(request.get("claim_ids", [])),
    }
    if request.get("decision_key") is not None:
        decision["value"] = deepcopy(option["value"])
        state["_decision_values"][request["decision_key"]] = deepcopy(option["value"])
        for human_request in state["coordination"]["human_input_requests"]:
            if human_request["topic"] == request["decision_key"]:
                human_request["status"] = "answered"
                human_request["answered_via"] = "human_decision"
        if request["decision_key"] == "review.decision_owner":
            state["coordination"]["decision_owner"] = deepcopy(option["value"])
            state["coordination"]["waits_for"] = []
            for review in state["coordination"]["review_requests"]:
                review["status"] = "owner_assigned"
    state["decisions"].append(decision)
    state["_progress"]["epoch"] += 1
    state["metrics"]["progress_events"] += 1
    state["detector"]["stalled_turns"] = 0
    state["detector"]["reason"] = "사람의 결정을 기록했습니다. 다음 산출물을 다시 검사합니다."
    state["detector"]["conflicts"] = _detect_conflicts(state)
    _update_coordination_detector(state)
    validation = evaluate_state(state)
    state["metrics"]["success"] = validation["success"]
    if choice == "stop" and not request.get("decision_key"):
        state["status"] = "stopped"
    elif validation["success"]:
        _record_validation(state, validation)
        state["status"] = "completed"
    elif state["turn"] >= state["max_turns"]:
        state["status"] = "budget_exhausted"
    else:
        state["status"] = "running"
    return state


def ontology_graph(state: dict) -> dict:
    """A typed graph of stored facts, preserving superseded claims and provenance."""
    nodes, edges = [], []
    task_id = "task:" + state["task"]["id"]
    artifact_id = "artifact:" + state["id"]
    nodes.append({"id": task_id, "type": "Task", "label": state["title"], "description": state["task"]["description"]})
    coordination = state.get("coordination", {})
    owners = state["task"].get("agent_owners", {})
    people = {item["id"]: item.get("name", item["id"]) for item in state["task"].get("people", [])}
    for person in owners.values():
        people.setdefault(person, person)
    for item in coordination.get("human_input_requests", []):
        people.setdefault(item["recipient"], item["recipient"])
    for item in coordination.get("commitments", []):
        people.setdefault(item["to_person"], item["to_person"])
    for identifier, name in people.items():
        nodes.append({"id": "person:" + identifier, "type": "Person", "label": name})
    agent_ids = {message["agent"] for message in state["messages"]} | set(owners)
    agent_ids.update(item["target"] for item in coordination.get("waits_for", []))
    agent_ids.update(item["target"] for item in coordination.get("review_requests", []))
    agents = sorted(agent_ids)
    for agent in agents:
        identifier = "agent:" + agent
        nodes.append({"id": identifier, "type": "Agent", "label": agent})
        edges.append({"source": identifier, "target": task_id, "type": "worksOn", "label": "담당 작업"})
        if agent in owners:
            edges.append({"source": identifier, "target": "person:" + owners[agent], "type": "represents", "label": "개인 에이전트"})
    evidence_ids = {item["id"] for item in state["evidence"]}
    for claim in state["claims"]:
        identifier = "claim:" + claim["id"]
        nodes.append({**deepcopy(claim), "id": identifier, "label": f"{claim['key']} = {_canonical(claim['value'])}"})
        edges.append({"source": "agent:" + claim["agent"], "target": identifier, "type": "asserts", "label": "주장"})
        edges.append({"source": identifier, "target": task_id, "type": "about", "label": "작업 범위"})
        for reference in claim.get("evidence_ids", []):
            if reference in evidence_ids:
                edges.append({"source": identifier, "target": "evidence:" + reference, "type": "supportedBy", "label": "근거 연결"})
        for previous in claim.get("supersedes", []):
            edges.append({"source": identifier, "target": "claim:" + previous, "type": "supersedes", "label": "이전 주장 갱신"})
    for conflict in state["detector"]["conflicts"]:
        candidates = [claim for claim in state["claims"] if claim["id"] in conflict["claim_ids"]]
        for index, left in enumerate(candidates):
            for right in candidates[index + 1:]:
                if left["agent"] != right["agent"] and not _same(left["value"], right["value"]):
                    edges.append({"source": "claim:" + left["id"], "target": "claim:" + right["id"], "type": "conflictsWith", "label": conflict["kind"], "status": conflict["status"]})
    for item in state["evidence"]:
        identifier = "evidence:" + item["id"]
        nodes.append({**deepcopy(item), "id": identifier, "label": item["summary"]})
        if item["origin"] == "local_validator" and state["artifact"]:
            revision_id = artifact_id + f":revision-{item['artifact_revision']}"
            nodes.append({"id": revision_id, "type": "Artifact", "label": f"검사 당시 산출물 r{item['artifact_revision']}", "data": deepcopy(item.get("artifact_snapshot", {})), "revision": item["artifact_revision"]})
            edges.append({"source": identifier, "target": revision_id, "type": "verifies", "label": "해당 시점 산출물 검사"})
            edges.append({"source": revision_id, "target": task_id, "type": "forTask", "label": "검사 대상"})
    for decision in state["decisions"]:
        identifier = "decision:" + decision["id"]
        nodes.append({**deepcopy(decision), "id": identifier, "label": decision["choice"]})
        edges.append({"source": identifier, "target": task_id, "type": "addresses", "label": "사람 결정"})
        addressed_claims = {claim["id"] for claim in state["claims"] if claim["key"] == decision.get("decision_key")}
        for claim_id in decision.get("claim_ids", []):
            if claim_id in addressed_claims:
                edges.append({"source": identifier, "target": "claim:" + claim_id, "type": "resolves", "label": "쟁점 결정"})
    if state["artifact"]:
        nodes.append({"id": artifact_id, "type": "Artifact", "label": "현재 계약·작업 계획", "data": deepcopy(state["artifact"]), "revision": state["_artifact_revision"]})
        edges.append({"source": artifact_id, "target": task_id, "type": "forTask", "label": "검사 대상"})
        contributing = {message["agent"] for message in state["messages"] if message.get("artifact")}
        for agent in sorted(contributing):
            edges.append({"source": "agent:" + agent, "target": artifact_id, "type": "contributesTo", "label": "산출물 기여"})
    for item in coordination.get("commitments", []):
        identifier = "commitment:" + item["agent"] + ":" + item["id"]
        nodes.append({**deepcopy(item), "id": identifier, "label": item["summary"]})
        edges.append({"source": "agent:" + item["agent"], "target": identifier, "type": "promises", "label": "확인 약속"})
        edges.append({"source": identifier, "target": "person:" + item["to_person"], "type": "promisedTo", "label": "확인 대상"})
    for item in coordination.get("human_input_requests", []):
        identifier = "human-input:" + item["agent"] + ":" + item["id"]
        nodes.append({**deepcopy(item), "id": identifier, "label": f"{item['topic']} · 전달 {'확인' if item['delivery_status'] == 'delivered' else '여부 미확인'}"})
        edges.append({"source": "agent:" + item["agent"], "target": identifier, "type": "requestsInput", "label": "사람 입력 필요"})
        edges.append({"source": identifier, "target": "person:" + item["recipient"], "type": "addressedTo", "label": "응답 주체"})
    for item in coordination.get("review_requests", []):
        identifier = "review:" + item["agent"] + ":" + item["id"]
        nodes.append({**deepcopy(item), "id": identifier, "label": f"{item['artifact']} 검토 요청"})
        edges.append({"source": "agent:" + item["agent"], "target": identifier, "type": "requestsReview", "label": "검토 요청"})
        edges.append({"source": identifier, "target": "agent:" + item["target"], "type": "reviewAssignedTo", "label": "검토 대기 대상"})
    for item in coordination.get("waits_for", []):
        edges.append({"source": "agent:" + item["source"], "target": "agent:" + item["target"], "type": "waits_for", "label": item["reason"]})
    owner = coordination.get("decision_owner")
    if owner:
        identifier = "decision-owner:" + state["task"]["id"]
        nodes.append({"id": identifier, "type": "DecisionOwner", "label": "최종 책임 리뷰어"})
        if owner not in people:
            nodes.append({"id": "person:" + owner, "type": "Person", "label": owner})
        edges.append({"source": "person:" + owner, "target": identifier, "type": "fillsRole", "label": "승인된 책임자"})
        edges.append({"source": identifier, "target": task_id, "type": "accountableFor", "label": "최종 결정 책임"})
    return {"nodes": nodes, "edges": edges, "ontology": deepcopy(ONTOLOGY)}
