"""Official MCP SDK bridge to the authoritative local Arbiter HTTP API.

Nothing observes conversations automatically. Agents explicitly report events;
human decisions are read here and can only be written through the human UI/API.
The bridge never opens the database and never sends Slack or other messages.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from .coordination_advice import next_action_from_state
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations


DEFAULT_API_URL = "http://127.0.0.1:8787"
DEFAULT_MCP_PORT = 8788
_SECRET_KEYS = {"api_key", "apikey", "authorization", "password", "secret", "access_token", "refresh_token", "credentials"}
_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,200}$")

AGENT_INSTRUCTIONS = """Arbiter is a coordination observer, not a messaging service.
Register a conversation once, retain its session ID, and share that ID with other
participating agents. Before handing off a task or saying you will ask an owner,
record the actual message with a stable unique event_id. Retry the same message
with the same event_id; use a new ID only for a new message. Evaluate the exact
scope/action and all participating agents before relying on authority. A scoped
decision_owner has priority only within existing execution permissions. For an
authority gap, conflict, cross-owner conflict, conditional or unknown authority,
ask the relevant human once and wait; do not self-grant rights or invent consent.
Registry approvals are local operator records, not verified external identities.
Then get_next_action.
If a human decision is pending, show the dashboard location and pause that
dependency instead of repeating promises or polling in a loop. After the human
says they responded, get_human_decisions or get_next_action once. Apply only new
decision IDs and only actions within your existing permissions. A recorded
decision or a promise is not proof of delivery or execution. Never create or
invent a human decision. This connection does not automatically observe Slack,
other channels, or messages that were not explicitly reported.
"""


def _sanitize(value: Any) -> Any:
    """Drop private implementation fields and credential-shaped keys recursively."""
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()
                if not key.startswith("_") and key.lower() not in _SECRET_KEYS}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _text(value: str, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ToolError(f"{name} must be nonempty text of at most {maximum} characters")
    return value


def _session_path(session_id: str) -> str:
    if not _SESSION_ID.fullmatch(session_id):
        raise ToolError("session_id must be the ID returned by register_conversation")
    return "/api/sessions/" + session_id


def _local_api_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise ValueError("ARBITER_API_URL must be a loopback HTTP(S) origin, for example http://127.0.0.1:8787")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("ARBITER_API_URL has an invalid port") from exc
    return value.rstrip("/")


class ArbiterAPI:
    """Small HTTP client with no retry of session-creating requests."""

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None):
        self.base_url = _local_api_url(base_url)
        self.client = client

    async def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        try:
            if self.client is None:
                async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False) as client:
                    response = await client.request(method, self.base_url + path, json=payload)
            else:
                response = await self.client.request(method, self.base_url + path, json=payload)
        except httpx.TimeoutException as exc:
            raise ToolError("Arbiter API timed out. For record_message, retry with the same event_id. Do not blindly retry registration; it may have created a session.") from exc
        except httpx.RequestError as exc:
            raise ToolError(f"Cannot reach the local Arbiter API at {self.base_url}. Start the dashboard API first.") from exc
        if not 200 <= response.status_code < 300:
            meanings = {404: "Session not found; check the saved session_id.",
                        409: "The API rejected a conflicting or stale operation.",
                        422: "The API rejected invalid input; check the tool arguments."}
            detail = meanings.get(response.status_code, "The local API could not complete this request.")
            raise ToolError(f"Arbiter API HTTP {response.status_code}: {detail}")
        try:
            result = response.json()
        except ValueError as exc:
            raise ToolError("Arbiter API returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise ToolError("Arbiter API returned an unexpected response shape")
        return _sanitize(result)


def create_server(api_url: str | None = None, *, client: httpx.AsyncClient | None = None,
                  port: int = DEFAULT_MCP_PORT) -> FastMCP:
    api = ArbiterAPI(api_url or os.environ.get("ARBITER_API_URL", DEFAULT_API_URL), client)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("MCP port must be between 1 and 65535")
    server = FastMCP("Hanium Arbiter", instructions=AGENT_INSTRUCTIONS,
                     host="127.0.0.1", port=port, streamable_http_path="/mcp",
                     json_response=True, stateless_http=True, log_level="WARNING")
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    append = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    create = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

    @server.tool(annotations=read)
    async def get_authority() -> dict[str, Any]:
        """Read the human-maintained scoped grants and precedence registry. Agent
        assertions are not grants. Owner approvals are local operator records,
        not independently verified external identities. Cannot modify authority.
        """
        return await api.request("GET", "/api/authority")

    @server.tool(annotations=read)
    async def evaluate_authority(scope: str, action: str, agents: list[str] | None = None) -> dict[str, Any]:
        """Read who may decide this exact scope/action across all valid holders.
        Optional agents select a requested-agent summary only: they never hide
        other holders, owner conflicts, or the global scoped decision owner.
        A decision_owner has scoped priority, not general superiority. Unknown,
        conditional, missing, or conflicting rights require human clarification.
        This POST evaluates existing records only; it grants no rights, records
        no human approval, and proves neither facts nor execution.
        """
        _text(scope, "scope", 200)
        _text(action, "action", 100)
        if agents is not None:
            if len(agents) > 100:
                raise ToolError("agents must contain at most 100 participating agent IDs")
            for agent in agents:
                _text(agent, "agent", 100)
        payload: dict[str, Any] = {"scope": scope, "action": action}
        if agents is not None:
            payload["agents"] = agents
        return await api.request("POST", "/api/authority/evaluate", payload)

    @server.tool(annotations=create)
    async def register_conversation(title: str, source: Literal["pickle", "slack", "manual"],
                                    initial_message: str, agent: str) -> dict[str, Any]:
        """Create one coordination session from the first reported message. Call once,
        save the returned id, and share it with participating agents. This does not
        connect to or send a message to the named source channel. Registration is
        not idempotent; a repeated call creates a separate session.
        """
        _text(title, "title", 150)
        _text(agent, "agent", 45)
        _text(initial_message, "initial_message", 10000)
        if any(character in agent for character in ("\n", "\r", ":", "：")):
            raise ToolError("agent must be a single speaker label without colons")
        # Prefix each supplied line so quoted labels in content cannot invent
        # another speaker in the API's line-based transcript format.
        transcript = "\n".join(f"{agent}: {line}" for line in initial_message.splitlines() if line.strip())
        if len(transcript) > 40000:
            raise ToolError("The formatted initial message exceeds the transcript limit")
        result = await api.request("POST", "/api/intake", {"title": title, "source": source, "transcript": transcript})
        return {**result, "session_id": result.get("id"), "dashboard_url": api.base_url + "/",
                "observation_mode": "explicit_tool_calls_only"}

    @server.tool(annotations=append)
    async def record_message(session_id: str, event_id: str, agent: str, content: str) -> dict[str, Any]:
        """Append a reported message to an existing session. Use the same stable
        event_id when retrying that message: the authoritative API deduplicates it.
        A report is not a delivery receipt. Does not create human decisions or send
        messages to Slack, owners, or other agents.
        """
        path = _session_path(session_id)
        _text(event_id, "event_id", 200)
        _text(agent, "agent", 100)
        _text(content, "content", 10000)
        return await api.request("POST", path + "/events", {"event_id": event_id, "agent": agent, "content": content})

    @server.tool(annotations=read)
    async def get_coordination_state(session_id: str) -> dict[str, Any]:
        """Read the authoritative session, reported claims, pending questions, and
        human decisions. Fields describe recorded information, not unseen actions.
        """
        return await api.request("GET", _session_path(session_id))

    @server.tool(annotations=read)
    async def list_pending_decisions(session_id: str) -> dict[str, Any]:
        """Read questions that need an actual human answer in the dashboard. Do not
        answer these on the human's behalf or poll repeatedly while they are away.
        Old questions already covered by current scoped authority are listed
        separately; their stored records are preserved without asking them again.
        """
        advice = await api.request("GET", _session_path(session_id) + "/next-action")
        return {"session_id": session_id, "status": advice.get("status"),
                "pending_decisions": advice.get("remaining_pending_decisions", advice.get("pending_decisions", [])),
                "recorded_pending_decisions": advice.get("recorded_pending_decisions", advice.get("pending_decisions", [])),
                "covered_pending_decisions": advice.get("covered_pending_decisions", []),
                "authority_interventions": advice.get("authority_interventions", []),
                "authority_context": advice.get("authority_context", "unavailable"),
                "dashboard_url": advice.get("dashboard_url", api.base_url + "/workspace")}

    @server.tool(annotations=read)
    async def get_human_decisions(session_id: str) -> dict[str, Any]:
        """Read recorded human choices and next-action notes after the human replies.
        Track decision IDs locally so a decision is not applied twice. Recorded
        choices are not proof that the resulting actions were delivered or done.
        """
        return await api.request("GET", _session_path(session_id) + "/decisions")

    @server.tool(annotations=read)
    async def get_next_action(session_id: str) -> dict[str, Any]:
        """Read one current API snapshot and return whether to wait for a human,
        follow a recorded decision, or continue reporting. This advice never
        fabricates a receipt, execution result, or a human answer.
        """
        return await api.request("GET", _session_path(session_id) + "/next-action")

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Local Arbiter MCP bridge")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--port", type=int, default=DEFAULT_MCP_PORT, help="Streamable HTTP port on 127.0.0.1")
    parser.add_argument("--api-url", default=os.environ.get("ARBITER_API_URL", DEFAULT_API_URL))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    try:
        server = create_server(args.api_url, port=args.port)
    except ValueError as exc:
        parser.error(str(exc))
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
