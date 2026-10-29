"""Export an auditable session without changing simulated values into measurements."""
from __future__ import annotations

import json
from typing import Any


def session_markdown(state: dict[str, Any]) -> str:
    mode = {"demo": "Controlled simulation — scripted agents", "codex": "Live model call — Codex CLI",
            "import": "Imported conversation — rule-based coordination review"}[state["mode"]]
    metrics = state.get("metrics", {})
    measured, unmetered = metrics.get("measured_calls", 0), metrics.get("unmetered_calls", 0)
    tokens = str(metrics.get("input_tokens", 0) + metrics.get("output_tokens", 0)) if measured else "Not measured"
    if measured and unmetered:
        tokens += " (only some calls measured)"
    lines = [f"# {state['title']} — Run results", "", f"Run type: {mode}", "",
             "| Item | Result |", "|---|---|",
             f"| Run ID | {state['id']} |", f"| Policy | {state['policy']} |",
             f"| Status | {state['status']} |", f"| Agent messages | {state['turn']} |",
             f"| Total input/output tokens | {tokens} |",
             f"| Human requests | {metrics.get('human_requests', len(state.get('requests', [])))} |",
             f"| Artifact validation success | {metrics.get('success') if metrics.get('success') is not None else 'Not evaluated'} |", "",
             "## Task and evaluation", "", state.get("task", {}).get("description", ""), "",
             "Artifacts are checked against the explicit checklist. A model's completion claim or a human choice alone does not verify facts.", "",
             "## Human decisions", ""]
    for decision in state.get("decisions", []):
        lines.append(f"- {decision.get('request_id')}: {decision.get('choice')} — {decision.get('note', '')}")
    if not state.get("decisions"):
        lines.append("No decisions recorded.")
    lines += ["", "## Conversation", ""]
    for message in state.get("messages", []):
        lines += [f"### {message.get('turn', '')} {message.get('agent', '')}", "", message.get("content", ""), ""]
    lines += ["## Final artifact", "", "```json", json.dumps(state.get("artifact", {}), ensure_ascii=False, indent=2), "```", "",
              "## Interpretation limits", "", "These are results from a single run. The task produces a structured contract artifact; it does not modify or execute code in an actual repository.",
              "Simulated message counts do not measure actual LLM tokens or the intervention burden in a user study.", ""]
    if state["mode"] == "import":
        lines += ["Imported conversations are checked for explicit expressions using rules. Actual request delivery and external task completion remain unverified.",
                  "Decisions are recorded locally. They are not delivered externally until a connected agent reads them through the decisions API.", ""]
    return "\n".join(lines)
