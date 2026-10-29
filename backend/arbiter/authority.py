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
        "required_owners": [], "reason": "The authority records cannot be evaluated.", "grant_ids": [],
        "scope": scope, "action": action, "source": SOURCE,
        "precedence_applied": False, "priority_order": [], "conditional_agents": [],
        "owner_by_agent": {}, "authority_only": True,
        "registry_revision": None,
        "grant_revision": None,
    }
    if not _text(scope) or not _text(action) or not isinstance(registry, dict):
        result["reason"] = "An explicit scope, action, and human-maintained authority registry are required."
        return result
    if not isinstance(registry.get("grants", []), list) or not isinstance(registry.get("precedence", []), list):
        result["reason"] = "The authority registry has an invalid format."
        return result
    result["registry_revision"] = registry_revision(registry)
    result["grant_revision"] = grant_revision(registry, scope, action)
    if agents is not None and (not isinstance(agents, (list, tuple, set, frozenset)) or any(not _text(agent) for agent in agents)):
        result["reason"] = "The participating agent set is invalid."
        return result
    participating = set(agents) if agents is not None else None
    clock = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(clock, datetime) or clock.tzinfo is None or clock.utcoffset() is None:
        result["reason"] = "Checking grant expiration requires a current time with an explicit time zone."
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
        result["reason"] = "Priority cannot be established because this scope's grant records contain unclear owner, condition, or expiration information."
        return result
    if any(len(values) != 1 for values in owners_by_agent.values()):
        result["reason"] = "Valid grants for the same agent name different owners. Human clarification is required."
        return result
    if not valid_agents:
        if conditional:
            result.update(status="conditional", required_owners=sorted({grant["owner"] for grant in conditional}),
                          grant_ids=sorted({grant["id"] for grant in conditional}),
                          reason="Only conditional grants exist, and their conditions have not been verified. Authority is not automatically granted.")
        else:
            result.update(status="authority_gap", reason="No participating agent has a valid human-issued grant for this scope/action.")
        return result
    if len(valid_agents) == 1:
        result.update(status="authorized", decision_owner=valid_agents[0],
                      reason="Exactly one agent holds a valid, unconditional grant for this exact scope/action.")
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
                      reason="Human-recorded priority was applied among the valid grant holders for this scope/action."
                      + (" Approval from every relevant owner is recorded; remote identity verification has not been performed." if cross_owner else ""))
        return result
    if cross_owner:
        result.update(status="cross_owner_conflict",
                      reason="Grants from different owners overlap. A consistent priority order with recorded approval from every relevant owner is required.")
    else:
        result.update(status="authority_conflict",
                      reason="Multiple agents hold valid grants for this scope, and applicable priority is either missing or conflicting.")
    return result
