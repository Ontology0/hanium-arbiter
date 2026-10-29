---
name: arbiter-coordination
description: "Coordinate collaborating agents through a local Arbiter service: report conversations, inspect scoped authority and owner-approved priority, and follow recorded human decisions when delegation or authority is unclear."
metadata: {"openclaw":{"requires":{"bins":["python3"]}}}
---

# Arbiter coordination

Use this skill when coordinating multiple agents whose scope of authority, decision owner, or human dependency matters. The local Arbiter API must already be running. It records reports and local human input; it does not observe unreported conversations or send messages on your behalf.

Use Arbiter MCP tools when those tools are available. Otherwise run the bundled standard-library client with the existing execution tool:

```sh
python3 "{baseDir}/scripts/arbiter_client.py" --help
```

`ARBITER_API_URL` defaults to `http://127.0.0.1:8787`. Only a loopback origin is supported. If the execution environment is sandboxed or on a remote host, its loopback is different: report the connection issue instead of assuming access or changing security settings.

## Keep a shared conversation record

Register once and retain/share the returned `session_id`. Use `source=manual` for OpenClaw unless the actual conversation came from Slack or Pickle. If an existing Slack adapter already owns the thread's session, reuse that session rather than creating a second one.

```sh
python3 "{baseDir}/scripts/arbiter_client.py" register --title "Proposal review" --source manual --agent reviewer-a --initial-message "We are reviewing the proposal."
python3 "{baseDir}/scripts/arbiter_client.py" report --session-id SESSION_ID --event-id SOURCE_MESSAGE_ID --agent reviewer-b --content "I need to know who may approve this proposal."
```

Report actual coordination messages before handing off or promising to ask an owner. Use the source's stable event ID. Retries of the same message must reuse the same ID; new messages require new IDs. Register is not idempotent: do not blindly retry a failed registration. A message report or promise is not a delivery receipt.

## Resolve authority before relying on it

Read `get-authority`, then evaluate the exact agreed scope/action. The API evaluates **all recorded holders for that scope/action**. The optional participating-agent list only adds a requested-agent summary; it cannot exclude another owner's rights from the decision. If scope/action is ambiguous, ask for that concrete missing value rather than inventing a broad permission.

```sh
python3 "{baseDir}/scripts/arbiter_client.py" get-authority
python3 "{baseDir}/scripts/arbiter_client.py" evaluate --scope "review:proposal" --action approve --agents reviewer-a reviewer-b
```

Use the returned status:

- `authorized`: the `decision_owner` has priority for this exact scope/action. Follow that agent's scoped decision only within the permissions already available to you. This does not authorize new external actions by itself.
- `cross_owner_conflict`: the listed `required_owners` need to resolve the overlap. Agent confidence or seniority cannot establish whose owner's rights prevail. Cross-owner precedence requires all relevant owners' approval records.
- `authority_gap`, `authority_conflict`, `conditional`, or `unknown`: ask one concrete question about the missing grant, owner, condition, or precedence, then pause that dependency. Continue unrelated authorized work if available.

Show the pending Arbiter question and dashboard URL if one exists. If evaluation finds a conflict without a pending card, explain that finding once to the initiating human and direct them to the authority controls; evaluation itself does not create or deliver a human request. Do not fabricate a card, consent, or owner identity. Do not repeat “I will ask my owner” to another agent as a substitute for a human response. Do not busy-poll.

## Resume after a real human response

```sh
python3 "{baseDir}/scripts/arbiter_client.py" next-action --session-id SESSION_ID
python3 "{baseDir}/scripts/arbiter_client.py" decisions --session-id SESSION_ID
```

When the human says they responded, read decisions once and re-evaluate authority if it was changed. Keep applied decision IDs so retries do not execute the same instruction twice. A human decision note does not itself create a grant. Report the actual subsequent message using its new event ID.

MCP and this helper read the same next-action API. `follow_authority` identifies the current scoped decision owner; do not ask for that same approval again. `pending_decisions` contains remaining questions. `covered_pending_decisions` contains earlier authority questions answered by the current grants and precedence; their original records are retained, not fabricated as human answers. Unrelated dependencies remain pending. `refresh_coordination_context` means the conversation changed after extraction: confirm the current scope or request a fresh brief before relying on the old interpretation. A next-action read never calls a model. Authority changes alone are reevaluated without another model call.

The equivalent MCP tools are `register_conversation`, `record_message`, `get_authority`, `evaluate_authority`, `get_coordination_state`, `list_pending_decisions`, `get_human_decisions`, and `get_next_action`.

Neither interface provides human-decision writes, self-grants, revocations, or precedence writes. Do not call human-only HTTP endpoints on someone's behalf. Registry provenance is `local_operator_record`: remote owner identity and consent are not independently authenticated. Authority priority is not proof that a factual claim is true, a message was delivered, or an action completed.
