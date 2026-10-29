"""Evidence-linked coordination triage for imported conversations.

The rule extractor identifies review candidates, not hidden actions or intent.
A promise to ask someone never establishes that a request was delivered.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import re
from typing import Any
import unicodedata
from uuid import uuid4


PROMISE = re.compile(r"확인.{0,18}(볼|보겠|할게|하겠|드릴|되시|받는|후|대로)|여쭤.{0,12}(볼|보겠)|물어.{0,12}(볼|보겠)|전달.{0,12}(할게|하겠|드릴)")
WAIT = re.compile(r"기다|완료.{0,12}(후|되면)|검토.{0,12}(후|되면|끝나)|확인.{0,12}(대로|되면|되시는|받는)")
REVIEW = re.compile(r"검토|리뷰|승인|결정권|결재")
LABEL = re.compile(r"^\s*(?:\[[^\]]+\]\s*)?([^:\n：]{1,45})[:：]\s*(.*)$")
EXPLICIT_OWNER = re.compile(r"(?:최종\s*)?(?:결정권자|승인자|책임자)\s*(?:는|:|：|=)\s*\S+")


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().rstrip(".!?。！？…")


def _fingerprint(kind: str, values: list) -> str:
    encoded = json.dumps([kind, values], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()[:20]


def _obligation_scope(kind: str, actor: str, text: str) -> dict:
    # Scope depends only on the message, never on which actors appear later.
    # Full normalized text is deliberately conservative: different wording may
    # need review again, but unrelated topics cannot inherit an old decision.
    normalized_text = _normalized(text)
    target = re.search(r"([^\s,.:]+?)(?:에게|한테)", normalized_text)
    return {"id": _fingerprint(kind, [_normalized(actor), normalized_text]), "actor": actor,
            "normalized_text": normalized_text, "target": target.group(1) if target else None,
            "topic": normalized_text}


def _refresh_status(state: dict) -> None:
    active = [item for item in state["requests"] if item.get("active", True)]
    pending = [item for item in active if item["status"] == "pending"]
    handoffs = [item for item in active if item["kind"] == "handoff"]
    statuses = {item.get("delivery_status", "unknown") for item in handoffs}
    if statuses == {"human_reported_delivered"}:
        delivery_status = "human_reported_delivered"
    elif "human_reported_delivered" in statuses:
        delivery_status = "mixed"
    else:
        delivery_status = "unknown"
    state["coordination"]["delivery_status"] = delivery_status
    state["coordination"]["pending_handoff_count"] = sum(item["status"] == "pending" for item in handoffs)
    state["coordination"]["pending_request_count"] = len(pending)
    by_id = {item["id"]: item for item in handoffs}
    for commitment in state["coordination"]["commitments"]:
        request = by_id.get(commitment.get("request_id"))
        commitment["status"] = "human_reported_delivered" if request and request.get("delivery_status") == "human_reported_delivered" else "delivery_unknown"
    state["status"] = "waiting" if pending else "stopped"


def parse_transcript(text: str) -> list[dict]:
    messages: list[dict] = []
    for line in text.strip().splitlines():
        match = LABEL.match(line)
        if match:
            messages.append({"id": f"m{len(messages)+1}", "agent": match.group(1).strip(), "content": match.group(2).strip()})
        elif line.strip():
            if not messages:
                messages.append({"id": "m1", "agent": "발화자 미지정", "content": line.strip()})
            else:
                messages[-1]["content"] += "\n" + line.strip()
    return messages


def create_import(text: str, title: str = "가져온 협업 대화", source: str = "manual") -> dict:
    messages = parse_transcript(text)
    if not messages:
        raise ValueError("분석할 대화를 입력해 주세요.")
    state: dict[str, Any] = {
        "id": uuid4().hex, "scenario_id": "conversation-intake", "title": title,
        "description": "제공된 대화에 근거한 확인 요청·대기 관계 점검", "policy": "adaptive", "mode": "import",
        "source": source, "status": "stopped", "turn": len(messages), "max_turns": len(messages),
        "messages": [], "requests": [], "decisions": [], "claims": [], "evidence": [], "artifact": {},
        "metrics": {"input_tokens": 0, "output_tokens": 0, "measured_calls": 0, "unmetered_calls": 0,
                    "human_requests": 0, "progress_events": 0, "success": None},
        "detector": {"stalled_turns": 0, "reason": "대화의 명시적 확인·대기 표현을 점검합니다.", "conflicts": []},
        "task": {"id": "coordination", "description": "담당자와 다음 확인 행동을 명확히 한다.", "checklist": []},
        "coordination": {"summary": "", "issues": [], "commitments": [], "waits": [], "people": [],
                         "analyzer": "규칙 기반 후보 추출", "delivery_status": "unknown", "next_actions": []},
        "validation": {"success": None, "passed": 0, "total": 0, "checks": [],
                       "reason": "실제 외부 작업의 완료는 대화 가져오기만으로 판정하지 않습니다."},
    }
    for position, message in enumerate(messages, 1):
        message.update(turn=position, claims=[], evidence=[], input_tokens=None, output_tokens=None,
                       usage_source="unavailable", provenance="imported_transcript")
        state["messages"].append(message)
        state["evidence"].append({"id": message["id"], "summary": message["content"],
                                  "source": f"import://{source}/{message['id']}", "grade": "REFERENCED",
                                  "status": "active", "type": "Evidence"})
    _analyze(state)
    return state


def reanalyze_import(state: dict) -> dict:
    """Re-triage edited/deleted transcript messages while retaining decisions.

    Set a removed message's ``deleted`` flag or ``status='deleted'``. The audit
    message remains stored, but no current obligation is inferred from it.
    """
    state["turn"] = len(state["messages"])
    state["max_turns"] = state["turn"]
    _analyze(state)
    return state


def _analyze(state: dict) -> None:
    coordination = state["coordination"]
    messages = [item for item in state["messages"] if not item.get("deleted") and item.get("status") != "deleted"]
    actors = list(dict.fromkeys(message["agent"] for message in messages))
    old_requests = deepcopy(state["requests"])
    commitments, waits = [], []
    promise_groups, review_groups = {}, {}
    for message in messages:
        actor, text = message["agent"], message["content"]
        if PROMISE.search(text):
            scope = _obligation_scope("handoff-status", actor, text)
            group = promise_groups.setdefault(scope["id"], {"scope": scope, "message_ids": [], "scope_message_ids": [message["id"]]})
            group["message_ids"].append(message["id"])
            commitments.append({"id": f"commitment-{message['id']}", "actor": actor, "action": text,
                                "kind": "promise", "status": "delivery_unknown", "message_id": message["id"],
                                "target": scope["target"], "scope_id": scope["id"],
                                "request_id": f"request-handoff-status-{scope['id']}",
                                "label": "확인하겠다는 약속 · 전달 상태 미확인"})
        if REVIEW.search(text) and not EXPLICIT_OWNER.search(text):
            scope = _obligation_scope("decision-owner", actor, text)
            group = review_groups.setdefault(scope["id"], {"scope": scope, "message_ids": [], "scope_message_ids": [message["id"]]})
            group["message_ids"].append(message["id"])
        if WAIT.search(text):
            targets = [candidate for candidate in actors if candidate != actor and candidate in text]
            for target in targets:
                scope_id = _fingerprint("wait", [_normalized(actor), _normalized(target), _normalized(text)])
                existing = next((item for item in waits if item["scope_id"] == scope_id), None)
                if existing:
                    existing["evidence_ids"].append(message["id"])
                else:
                    waits.append({"from": actor, "to": target, "reason": text,
                                  "scope_id": scope_id, "scope_message_ids": [message["id"]],
                                  "evidence_ids": [message["id"]], "confirmed": False})
    coordination["commitments"], coordination["waits"] = commitments, waits
    coordination["actors"] = actors
    issues: list[dict] = []
    # Explicit, reciprocal waits provide evidence of a cycle candidate.
    for index, left in enumerate(waits):
        for right in waits[index + 1:]:
            if left["from"] != right["to"] or left["to"] != right["from"]:
                continue
            scope_id = _fingerprint("wait-cycle", sorted([left["scope_id"], right["scope_id"]]))
            issues.append({"id": "wait-cycle", "scope_id": scope_id,
                           "scope": {"id": scope_id, "actors": sorted([left["from"], right["from"]]), "wait_scope_ids": sorted([left["scope_id"], right["scope_id"]])},
                           "scope_message_ids": left["scope_message_ids"] + right["scope_message_ids"],
                           "kind": "coordination", "title": f"{left['from']} · {right['from']} 상호 대기 확인",
                           "summary": "이 두 발화에서 상호 대기 표현이 확인됩니다. 먼저 움직일 담당자를 정하고 실제 의존 관계를 확인해야 합니다.",
                           "message_ids": sorted(set(left["evidence_ids"] + right["evidence_ids"]))})
    for group in review_groups.values():
        issues.append({"id": "decision-owner", "scope_id": group["scope"]["id"], **group,
                       "kind": "authority", "title": f"{group['scope']['actor']}의 검토 결정권자 확인",
                       "summary": "이 검토 발화에는 최종 승인자가 명시되지 않았습니다. 다른 주제의 승인자나 이전 결정이 적용되는지는 별도 확인이 필요합니다."})
    for group in promise_groups.values():
        issues.append({"id": "handoff-status", "scope_id": group["scope"]["id"], **group,
                       "kind": "handoff", "title": f"{group['scope']['actor']}의 확인 요청 전달 상태",
                       "summary": "이 확인 약속의 실제 전달 영수증은 제공되지 않았습니다. 이미 요청했다면 응답을 기다리고, 아직이라면 요청 담당자를 정합니다."})
    coordination["issues"] = issues
    coordination["summary"] = (
        f"{len(actors)}개 발화 주체, 확인 약속 {len(commitments)}건, 대기 관계 {len(waits)}건을 추출했습니다. "
        "다른 채널에서 이루어진 요청·응답 여부는 알 수 없습니다."
    )
    updated = {}
    old_by_id = {item["id"]: item for item in old_requests}
    for issue in issues:
        if issue["id"] == "handoff-status":
            options = [
                {"id": "already_delivered", "label": "이미 요청함 · 응답 대기", "description": "전달 근거와 응답할 사람을 메모에 기록합니다. 중복 요청을 보류합니다."},
                {"id": "assign_sender", "label": "요청 담당자 지정", "description": "메모에 담당자와 확인할 질문을 적어 다음 행동으로 기록합니다."},
                {"id": "need_details", "label": "전달 여부 먼저 확인", "description": "실제 요청 여부를 확인할 담당자를 메모에 기록합니다."},
            ]
            question = "이 확인 요청은 사람에게 실제로 전달됐나요?"
        else:
            options = [
                {"id": "assign_owner", "label": "담당자 직접 지정", "description": "메모에 사람 또는 에이전트 이름과 권한 범위를 적습니다."},
                {"id": "ask_initiator", "label": "요청자에게 권한 확인", "description": "누가 최종 결정할 수 있는지 원래 요청자에게 확인할 행동을 기록합니다."},
                {"id": "not_blocked", "label": "정상적인 대기", "description": "이미 정해진 담당자·기한·대기 사유를 메모에 기록하고 이 후보를 해제합니다."},
            ]
            question = "누가 먼저 확인하고 다음 응답을 맡을까요?" if issue["id"] == "wait-cycle" else "이 검토의 최종 승인자는 누구인가요?"
        identifier = f"request-{issue['id']}-{issue['scope_id']}"
        request = {"id": identifier, "status": "pending", "active": True, "kind": issue["kind"],
                   "issue_type": issue["id"], "scope_id": issue["scope_id"], "scope": deepcopy(issue["scope"]),
                   "title": issue["title"], "summary": issue["summary"], "question": question,
                   "options": options, "evidence_ids": issue["message_ids"], "created_turn": state["turn"]}
        if issue["kind"] == "handoff":
            request["delivery_status"] = "unknown"
        old = old_by_id.get(identifier)
        if old is None:
            # Old persisted versions had one broad card per issue type. Its
            # answer may cover only the original evidence, never a new duty.
            legacy = old_by_id.get(f"request-{issue['id']}")
            if legacy and legacy["status"] == "resolved" and set(issue["scope_message_ids"]).issubset(legacy.get("evidence_ids", [])):
                old = legacy
                request["resolved_by_request_id"] = legacy["id"]
        if old:
            for key in ("status", "created_turn", "resolved_turn", "choice", "decision_id", "delivery_status", "resolved_by_request_id"):
                if key in old:
                    request[key] = deepcopy(old[key])
            if old["status"] == "resolved" and issue["kind"] == "handoff" and "delivery_status" not in old:
                old_choice = next((item["choice"] for item in reversed(state["decisions"]) if item["request_id"] == old["id"]), None)
                request["delivery_status"] = "human_reported_delivered" if old_choice == "already_delivered" else "unknown"
        updated[identifier] = request
    requests = []
    for old in old_requests:
        if old["id"] in updated:
            requests.append(updated.pop(old["id"]))
        else:
            old["active"] = False
            if old["status"] == "pending":
                old["status"] = "superseded"
            requests.append(old)
    requests.extend(updated.values())
    state["requests"] = requests
    _refresh_status(state)
    state["metrics"]["human_requests"] = len(requests)
    state["detector"].update(reason=coordination["summary"], conflicts=issues)


def decide_import(state: dict, request_id: str, choice: str, note: str) -> None:
    request = next((item for item in state["requests"] if item["id"] == request_id), None)
    if not request or request["status"] != "pending":
        raise ValueError("이미 처리했거나 유효하지 않은 결정 요청입니다.")
    if choice not in {option["id"] for option in request["options"]}:
        raise ValueError("제시된 선택지에서 선택해 주세요.")
    if not note.strip():
        raise ValueError("담당자, 근거 또는 다음 행동을 메모에 기록해 주세요.")
    request["status"] = "resolved"
    request["choice"] = choice
    request["resolved_turn"] = state["turn"]
    decision = {"id": f"decision-{len(state['decisions'])+1}", "request_id": request_id,
                "choice": choice, "note": note.strip(), "turn": state["turn"],
                "scope_id": request.get("scope_id"), "scope": deepcopy(request.get("scope", {})),
                "source": "human_input", "delivery_status": "not_sent"}
    request["decision_id"] = decision["id"]
    state["decisions"].append(decision)
    state["coordination"]["next_actions"].append({"id": decision["id"], "request_id": request_id,
                                                  "choice": choice, "description": note.strip(), "status": "recorded"})
    if request["kind"] == "handoff":
        request["delivery_status"] = "human_reported_delivered" if choice == "already_delivered" else "unknown"
    state["metrics"]["progress_events"] += 1
    _refresh_status(state)


def conversation_graph(state: dict) -> dict:
    nodes = [{"id": "task", "type": "Task", "label": state["title"]}]
    edges = []
    actors = state["coordination"].get("actors", [])
    actor_ids = {actor: f"actor-{i}" for i, actor in enumerate(actors)}
    for actor, identifier in actor_ids.items():
        nodes.append({"id": identifier, "type": "Agent", "label": actor})
        edges.append({"source": identifier, "target": "task", "label": "participatesIn"})
    for commitment in state["coordination"]["commitments"]:
        nodes.append({"id": commitment["id"], "type": "Commitment", "label": "확인 약속",
                      "status": commitment["status"], "detail": commitment["action"]})
        edges.append({"source": actor_ids[commitment["actor"]], "target": commitment["id"], "label": "promises"})
    for item in state["coordination"]["waits"]:
        edges.append({"source": actor_ids[item["from"]], "target": actor_ids[item["to"]], "label": "waitsFor"})
    for request in state["requests"]:
        nodes.append({"id": request["id"], "type": "HumanInputRequest", "label": request["title"], "status": request["status"]})
        edges.append({"source": "task", "target": request["id"], "label": "requiresDecision"})
    for decision in state["decisions"]:
        nodes.append({"id": decision["id"], "type": "Decision", "label": decision["note"]})
        edges.append({"source": decision["id"], "target": decision["request_id"], "label": "addresses"})
    return {"nodes": nodes, "edges": edges, "ontology": {"reasoning": "Explicit transcript relationships; missing delivery evidence is unknown, not false."}}


def append_external_event(state: dict, event: dict) -> dict:
    """Append a caller-supplied message and re-triage, preserving resolved decisions.

    Repeated event IDs are idempotent. Caller reports are not delivery receipts.
    """
    if any(message.get("external_id") == event["event_id"] for message in state["messages"]):
        return state
    index = len(state["messages"]) + 1
    message = {"id": f"m{index}", "external_id": event["event_id"], "agent": event["agent"],
               "content": event["content"], "turn": index, "claims": [], "evidence": [],
               "input_tokens": None, "output_tokens": None, "usage_source": "unavailable", "provenance": "external_agent_report"}
    state["messages"].append(message)
    state["evidence"].append({"id": message["id"], "summary": message["content"], "source": "event://" + event["event_id"],
                              "grade": "REFERENCED", "status": "active", "type": "Evidence"})
    state["turn"] = index
    state["max_turns"] = index
    _analyze(state)
    return state
