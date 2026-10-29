"""Read-only Slack Socket Mode receiver for the local coordination API.

The local API owns durable event IDs and thread/session mapping. Supported
messages are acknowledged only after that API accepts them. No Slack messages,
reactions, or other write operations are performed by this process.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import logging
import os
import re
import signal
import sys
from threading import Event
from typing import Mapping
from urllib.parse import urlsplit

import httpx
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web import WebClient


LOGGER = logging.getLogger(__name__)
DEFAULT_API_URL = "http://127.0.0.1:8787"
SUPPORTED_SUBTYPES = {None, "bot_message", "thread_broadcast", "message_changed", "message_deleted"}
_CHANNEL_ID = re.compile(r"^[CG][A-Z0-9]+$")


def local_api_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise ValueError("ARBITER_API_URL must be a loopback HTTP(S) origin")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("ARBITER_API_URL contains an invalid port") from exc
    return value.rstrip("/")


@dataclass(frozen=True)
class SlackBridgeConfig:
    app_token: str = field(repr=False)
    bot_token: str = field(repr=False)
    allowed_channels: frozenset[str]
    api_url: str = DEFAULT_API_URL

    def __post_init__(self) -> None:
        if not self.allowed_channels or any(not isinstance(value, str) or not _CHANNEL_ID.fullmatch(value) for value in self.allowed_channels):
            raise ValueError("Slack observation requires explicit channel IDs")
        object.__setattr__(self, "api_url", local_api_url(self.api_url))

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> "SlackBridgeConfig":
        env = os.environ if environ is None else environ
        app_token, bot_token = env.get("SLACK_APP_TOKEN", ""), env.get("SLACK_BOT_TOKEN", "")
        if not app_token.startswith("xapp-"):
            raise ValueError("Set SLACK_APP_TOKEN to an app-level token with connections:write")
        if not bot_token.startswith("xoxb-"):
            raise ValueError("Set SLACK_BOT_TOKEN to the installed app's bot token")
        channels = frozenset(value.strip() for value in env.get("SLACK_ALLOWED_CHANNELS", "").split(",") if value.strip())
        if not channels or any(not _CHANNEL_ID.fullmatch(value) for value in channels):
            raise ValueError("SLACK_ALLOWED_CHANNELS must contain explicit comma-separated channel IDs; wildcards and channel names are not allowed")
        return cls(app_token, bot_token, channels, local_api_url(env.get("ARBITER_API_URL", DEFAULT_API_URL)))


class SecretRedactionFilter(logging.Filter):
    """Prevent SDK exception/log output from exposing configured credentials."""

    def __init__(self, secrets: tuple[str, ...]):
        super().__init__()
        self.secrets = tuple(value for value in secrets if value)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self.secrets:
            message = message.replace(secret, "[REDACTED]")
        message = re.sub(r"x(?:app|ox[baprs])-[-A-Za-z0-9]+", "[REDACTED]", message)
        message = re.sub(r"wss://[^\s'\"]+", "[Slack WebSocket URL]", message)
        record.msg, record.args = message, ()
        # Tracebacks may contain third-party request representations. The bridge
        # reports exception types itself and does not need credential-bearing
        # traceback text in operational logs.
        if record.exc_info:
            record.msg += " (exception details omitted)"
            record.exc_info = None
            record.exc_text = None
        return True


class SlackEventReceiver:
    def __init__(self, config: SlackBridgeConfig, http_client: httpx.Client | None = None):
        self.config = config
        self.client = http_client or httpx.Client(
            timeout=httpx.Timeout(1.5, connect=0.3, write=0.3, pool=0.3),
            follow_redirects=False, trust_env=False,
        )
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _ack(self, client: SocketModeClient, request: SocketModeRequest) -> None:
        client.send_socket_mode_response(SocketModeResponse(envelope_id=request.envelope_id))

    def handle(self, client: SocketModeClient, request: SocketModeRequest) -> dict:
        """SDK callback: filter locally, persist through API, then ACK the envelope."""
        if request.type != "events_api":
            self._ack(client, request)
            return {"status": "ignored", "reason": "unsupported_envelope"}
        payload = request.payload
        event = payload.get("event") if isinstance(payload, dict) else None
        if not isinstance(event, dict) or event.get("type") != "message":
            self._ack(client, request)
            return {"status": "ignored", "reason": "not_message"}
        if event.get("channel") not in self.config.allowed_channels:
            self._ack(client, request)
            return {"status": "ignored", "reason": "channel_not_allowed"}
        if event.get("subtype") not in SUPPORTED_SUBTYPES:
            self._ack(client, request)
            return {"status": "ignored", "reason": "unsupported_message_subtype"}
        event_id = payload.get("event_id")
        if not isinstance(event_id, str) or not event_id or not payload.get("team_id"):
            self._ack(client, request)
            LOGGER.warning("Ignored malformed Slack event without a durable event/team identity")
            return {"status": "ignored", "reason": "missing_event_identity"}
        try:
            # Preserve the actual Events API envelope. In particular, do not
            # replace event_id on retry, drop bot_id, or flatten edits/deletions.
            response = self.client.post(self.config.api_url + "/api/slack/events", json=payload)
        except httpx.RequestError as exc:
            LOGGER.warning("Local event ingestion unavailable (%s); Slack envelope not acknowledged", type(exc).__name__)
            return {"status": "retry", "event_id": event_id, "reason": "api_unavailable", "acknowledged": False}
        if not 200 <= response.status_code < 300:
            LOGGER.warning("Local event ingestion returned HTTP %s; Slack envelope not acknowledged", response.status_code)
            return {"status": "retry", "event_id": event_id, "reason": "api_rejected", "http_status": response.status_code, "acknowledged": False}
        self._ack(client, request)
        return {"status": "forwarded", "event_id": event_id, "http_status": response.status_code, "acknowledged": True}


def build_socket_client(config: SlackBridgeConfig, receiver: SlackEventReceiver) -> SocketModeClient:
    client = SocketModeClient(app_token=config.app_token, web_client=WebClient(token=config.bot_token))
    client.socket_mode_request_listeners.append(receiver.handle)
    return client


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Read-only Slack Socket Mode observer")
    parser.add_argument("--check-config", action="store_true", help="Validate environment settings without contacting Slack")
    args = parser.parse_args(argv)
    try:
        config = SlackBridgeConfig.from_environ()
    except ValueError as exc:
        parser.error(str(exc))
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(SecretRedactionFilter((config.app_token, config.bot_token)))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger("slack_sdk").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.check_config:
        LOGGER.info("Configuration valid: %s allowed channels; local API %s. No Slack connection attempted.", len(config.allowed_channels), config.api_url)
        return
    receiver = SlackEventReceiver(config)
    client = None
    stopped = Event()
    try:
        health = receiver.client.get(config.api_url + "/api/health")
        if health.status_code != 200:
            raise RuntimeError("Local API health check failed")
        client = build_socket_client(config, receiver)
        signal.signal(signal.SIGINT, lambda *_: stopped.set())
        signal.signal(signal.SIGTERM, lambda *_: stopped.set())
        client.connect()
        LOGGER.info("Slack Socket Mode connected; observing %s allowlisted channels. No message sending enabled.", len(config.allowed_channels))
        stopped.wait()
    except Exception as exc:
        LOGGER.error("Slack bridge stopped (%s). Check the local API, app installation, tokens, and channel membership.", type(exc).__name__)
        raise SystemExit(1) from None
    finally:
        if client is not None:
            client.close()
        receiver.close()


if __name__ == "__main__":
    main()
