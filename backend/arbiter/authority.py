"""Pure evaluation of scoped authority recorded by a local human operator.

The caller must load this registry from the human-only storage/API boundary.
An ``issuer`` string is a provenance marker, not a cryptographic signature.
Agent statements, confidence, verbosity, and message order never grant rights.
``approved_by`` records local operator assertions of owner approval; this module
does not authenticate remote owners or verify external consent.

Example: two agents owned by ``owner-a`` may both hold ``scope='review:proposal'``
and ``action='approve'``. Without a matching human precedence record their
decision owner is unresolved. A matching order ``['reviewer', 'assistant']``
selects ``reviewer`` only while both grants remain valid. This ordering has no
effect on another scope/action. Different owners additionally require every
relevant owner in that precedence record's ``approved_by`` list.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any


SOURCE = "local_operator_record"


def registry_revision(registry: dict) -> str:
    """Version the stored records, excluding response-only metadata."""
    records = {key: registry.get(key, []) for key in ("grants", "precedence")}
    return sha256(json.dumps(records, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def grant_revision(registry: dict, scope: str, action: str) -> str:
    """Bind an approval to the exact scoped grants the operator reviewed."""
    records = [grant for grant in registry.get("grants", []) if isinstance(grant, dict)
               and grant.get("scope") == scope and grant.get("action") == action]
    return sha256(json.dumps(records, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Authority timestamps must be ISO-8601 strings with an explicit timezone")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Authority timestamps require an explicit timezone")
    return parsed.astimezone(timezone.utc)


def evaluate_authority(registry: dict, scope: str, action: str, agents: list[str] | None = None,
                       *, now: datetime | None = None) -> dict:
    """Evaluate exact scope/action for the participating agents, without mutations.

    Empty ``agents`` means no participating agents; ``None`` examines all holders.
    Expiry is exclusive: a grant expiring at ``now`` is already expired. Conditions
    are unverified text and cannot be bypassed with an agent-supplied boolean.
    Malformed relevant human records fail closed with ``unknown``.
    """
    result = {
        "status": "unknown", "authorized_agents": [], "decision_owner": None,
        "required_owners": [], "reason": "권한 기록을 판정할 수 없습니다.", "grant_ids": [],
        "scope": scope, "action": action, "source": SOURCE,
        "precedence_applied": False, "priority_order": [], "conditional_agents": [],
        "owner_by_agent": {}, "authority_only": True,
        "registry_revision": None,
        "grant_revision": None,
    }
    if not _text(scope) or not _text(action) or not isinstance(registry, dict):
        result["reason"] = "명시적인 scope와 action 및 사람의 권한 레지스트리가 필요합니다."
        return result
    if not isinstance(registry.get("grants", []), list) or not isinstance(registry.get("precedence", []), list):
        result["reason"] = "권한 레지스트리 형식이 올바르지 않습니다."
        return result
    result["registry_revision"] = registry_revision(registry)
    result["grant_revision"] = grant_revision(registry, scope, action)
    if agents is not None and (not isinstance(agents, (list, tuple, set, frozenset)) or any(not _text(agent) for agent in agents)):
        result["reason"] = "참여 에이전트 집합이 올바르지 않습니다."
        return result
    participating = set(agents) if agents is not None else None
    clock = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(clock, datetime) or clock.tzinfo is None or clock.utcoffset() is None:
        result["reason"] = "권한 만료 확인에는 시간대가 명시된 현재 시각이 필요합니다."
        return result
    clock = clock.astimezone(timezone.utc)
    unconditional, conditional, invalid = [], [], []
    observed_ids: dict[str, dict] = {}
    for grant in registry.get("grants", []):
        if not isinstance(grant, dict) or grant.get("issuer") != "local-human":
            continue
        if grant.get("scope") != scope or grant.get("action") != action:
            continue
        if participating is not None and grant.get("agent") not in participating:
            continue
        if grant.get("revoked") is True:
            continue
        try:
            if not all(_text(grant.get(key)) for key in ("id", "agent", "owner")):
                raise ValueError("Missing human-owned grant identity")
            if type(grant.get("revoked", False)) is not bool:
                raise ValueError("Invalid revocation flag")
            expiry = grant.get("expires_at")
            if expiry is not None and _utc(expiry) <= clock:
                continue
            conditions = grant.get("conditions", [])
            if not isinstance(conditions, list) or any(not _text(condition) for condition in conditions):
                raise ValueError("Conditions must be explicit nonempty strings")
            previous = observed_ids.get(grant["id"])
            if previous is not None and previous != grant:
                raise ValueError("Conflicting records use the same grant ID")
            if previous is not None:
                continue
            observed_ids[grant["id"]] = grant
            (conditional if conditions else unconditional).append(grant)
        except (TypeError, ValueError, OverflowError):
            invalid.append(grant.get("id"))
    valid_agents = sorted({grant["agent"] for grant in unconditional})
    result["authorized_agents"] = valid_agents
    result["conditional_agents"] = sorted({grant["agent"] for grant in conditional} - set(valid_agents))
    result["grant_ids"] = sorted({grant["id"] for grant in unconditional})
    owners_by_agent: dict[str, set[str]] = {}
    for grant in unconditional:
        owners_by_agent.setdefault(grant["agent"], set()).add(grant["owner"])
    result["owner_by_agent"] = {agent: next(iter(owners)) for agent, owners in owners_by_agent.items() if len(owners) == 1}
    owners = sorted({grant["owner"] for grant in unconditional})
    result["required_owners"] = owners
    if invalid:
        result["invalid_grant_ids"] = invalid
        result["reason"] = "해당 범위의 사람 권한 기록에 소유자·조건·만료 등 불명확한 정보가 있어 우선권을 확정하지 않습니다."
        return result
    if any(len(values) != 1 for values in owners_by_agent.values()):
        result["reason"] = "같은 에이전트의 유효 권한에 서로 다른 소유자가 기록되어 사람의 확인이 필요합니다."
        return result
    if not valid_agents:
        if conditional:
            result.update(status="conditional", required_owners=sorted({grant["owner"] for grant in conditional}),
                          grant_ids=sorted({grant["id"] for grant in conditional}),
                          reason="조건부 권한만 존재하며 조건 충족을 검증하지 않았습니다. 자동으로 권한을 인정하지 않습니다.")
        else:
            result.update(status="authority_gap", reason="이 scope/action에서 참여 에이전트에게 부여된 유효한 사람 권한이 없습니다.")
        return result
    if len(valid_agents) == 1:
        result.update(status="authorized", decision_owner=valid_agents[0],
                      reason="정확히 일치하는 scope/action에서 조건 없는 유효 권한 보유자가 한 명입니다.")
        return result

    cross_owner = len(owners) > 1
    applicable_orders = []
    for precedence in registry.get("precedence", []):
        if (not isinstance(precedence, dict) or precedence.get("issuer") != "local-human"
                or precedence.get("scope") != scope or precedence.get("action") != action):
            continue
        if ("grant_revision" in precedence
                and precedence["grant_revision"] != grant_revision(registry, scope, action)):
            continue
        order = precedence.get("agents")
        if not isinstance(order, list) or any(not _text(agent) for agent in order) or len(set(order)) != len(order):
            continue
        # Unranked holders are not implicitly below ranked ones. Invalid,
        # expired, revoked, and nonparticipating agents cannot outrank anyone.
        filtered = [agent for agent in order if agent in valid_agents]
        if set(filtered) != set(valid_agents):
            continue
        if cross_owner:
            approvals = precedence.get("approved_by", [])
            if not isinstance(approvals, list) or any(not _text(owner) for owner in approvals) or not set(owners).issubset(approvals):
                continue
        applicable_orders.append(filtered)
    winners = {order[0] for order in applicable_orders}
    if len(winners) == 1:
        winner = next(iter(winners))
        result.update(status="authorized", decision_owner=winner, precedence_applied=True,
                      priority_order=next(order for order in applicable_orders if order[0] == winner),
                      reason="이 scope/action의 유효 권한 보유자 사이에 사람이 기록한 우선권을 적용했습니다."
                      + (" 관련 소유자 전원의 승인 기록이 있으며 원격 본인 인증을 수행한 것은 아닙니다." if cross_owner else ""))
        return result
    if cross_owner:
        result.update(status="cross_owner_conflict",
                      reason="서로 다른 소유자의 권한이 겹칩니다. 관련 소유자 모두의 승인 기록이 있는 일관된 우선권이 필요합니다.")
    else:
        result.update(status="authority_conflict",
                      reason="같은 범위의 유효 권한 보유자가 여러 명이고 적용 가능한 우선권이 없거나 서로 충돌합니다.")
    return result
