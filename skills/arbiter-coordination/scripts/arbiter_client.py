#!/usr/bin/env python3
"""Standard-library client for Arbiter's read/report agent capabilities.

No dependency on the server package. This CLI never creates human decisions,
authority grants, revocations, or precedence records. It talks to loopback only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


DEFAULT_API_URL = "http://127.0.0.1:8787"
SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,200}$")
SECRET_KEYS = {"api_key", "apikey", "authorization", "password", "secret", "access_token", "refresh_token", "credentials"}


class ClientError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                 and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
                 and parsed.path in {"", "/"})
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ClientError("ARBITER_API_URL must be a loopback HTTP(S) origin, such as http://127.0.0.1:8787")
    return value.rstrip("/")


def clean(value):
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()
                if not key.startswith("_") and key.lower() not in SECRET_KEYS}
    if isinstance(value, list):
        return [clean(item) for item in value]
    return value


def text(value: str, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ClientError(f"{name} must be nonempty text of at most {maximum} characters")
    return value


def session_path(session_id: str) -> str:
    if not SESSION_ID.fullmatch(session_id):
        raise ClientError("session_id must be the ID returned by register")
    return "/api/sessions/" + session_id


class Client:
    def __init__(self, base_url: str):
        self.base_url = local_origin(base_url)
        # Ignore ambient proxies and refuse redirects, including to remote hosts.
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = Request(self.base_url + path, data=raw, method=method,
                          headers={"Accept": "application/json", "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=15) as response:
                if not 200 <= response.status < 300:
                    raise ClientError(f"Arbiter API HTTP {response.status}; no external execution is implied")
                result = json.loads(response.read())
        except HTTPError as exc:
            raise ClientError(f"Arbiter API HTTP {exc.code}; check the session and arguments") from None
        except (URLError, TimeoutError, OSError):
            raise ClientError("Cannot reach the local Arbiter API. Do not repeat register blindly; retry report only with the same event_id.") from None
        except (ValueError, UnicodeError):
            raise ClientError("Arbiter API returned invalid JSON") from None
        if not isinstance(result, dict):
            raise ClientError("Arbiter API returned an unexpected response shape")
        return clean(result)




def run(args: argparse.Namespace, client: Client) -> dict:
    command = args.command
    if command == "get-authority":
        return client.request("GET", "/api/authority")
    if command == "evaluate":
        payload = {"scope": text(args.scope, "scope", 200), "action": text(args.action, "action", 100)}
        if args.agents is not None:
            if len(args.agents) > 100:
                raise ClientError("agents must contain at most 100 participating IDs")
            payload["agents"] = [text(agent, "agent", 100) for agent in args.agents]
        return client.request("POST", "/api/authority/evaluate", payload)
    if command == "register":
        agent = text(args.agent, "agent", 45)
        if any(character in agent for character in ("\n", "\r", ":", "：")):
            raise ClientError("agent must be a single speaker label without colons")
        content = text(args.initial_message, "initial_message", 10000)
        transcript = "\n".join(f"{agent}: {line}" for line in content.splitlines() if line.strip())
        text(transcript, "formatted transcript", 40000)
        result = client.request("POST", "/api/intake", {
            "title": text(args.title, "title", 150), "source": args.source, "transcript": transcript,
        })
        return {**result, "session_id": result.get("id"), "dashboard_url": client.base_url + "/",
                "observation_mode": "explicit_tool_calls_only"}
    path = session_path(args.session_id)
    if command == "report":
        return client.request("POST", path + "/events", {
            "event_id": text(args.event_id, "event_id", 200), "agent": text(args.agent, "agent", 100),
            "content": text(args.content, "content", 10000),
        })
    if command == "state":
        return client.request("GET", path)
    if command == "decisions":
        return client.request("GET", path + "/decisions")
    if command == "next-action":
        return client.request("GET", path + "/next-action")
    raise ClientError("Unsupported capability")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--api-url", default=os.environ.get("ARBITER_API_URL", DEFAULT_API_URL))
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("get-authority", help="Read the human-maintained authority registry")
    evaluate = commands.add_parser("evaluate", help="Evaluate existing scoped authority; does not grant rights")
    evaluate.add_argument("--scope", required=True)
    evaluate.add_argument("--action", required=True)
    evaluate.add_argument("--agents", nargs="+", help="Every participating agent ID; omit to examine all holders")
    register = commands.add_parser("register", help="Create a session once; retain the returned session_id")
    register.add_argument("--title", required=True)
    register.add_argument("--source", choices=("manual", "slack", "pickle"), default="manual")
    register.add_argument("--agent", required=True)
    register.add_argument("--initial-message", required=True)
    for name in ("report", "state", "decisions", "next-action"):
        command = commands.add_parser(name)
        command.add_argument("--session-id", required=True)
        if name == "report":
            command.add_argument("--event-id", required=True)
            command.add_argument("--agent", required=True)
            command.add_argument("--content", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = run(args, Client(args.api_url))
    except ClientError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
