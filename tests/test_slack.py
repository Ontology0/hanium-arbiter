"""Socket Mode callback tests with synthetic events and no Slack credentials."""

from copy import deepcopy
import json
import logging
from pathlib import Path

import httpx
import pytest
from slack_sdk.socket_mode.request import SocketModeRequest

from arbiter.slack_bridge import (
    SecretRedactionFilter, SlackBridgeConfig, SlackEventReceiver, build_socket_client, main,
)


class FakeSocket:
    def __init__(self, order=None):
        self.responses = []
        self.order = order if order is not None else []

    def send_socket_mode_response(self, response):
        self.order.append("ack")
        self.responses.append(response)


def config(**overrides):
    return SlackBridgeConfig(**{"app_token": "xapp-test-only", "bot_token": "xoxb-test-only",
                                "allowed_channels": frozenset({"C123", "G456"}), **overrides})


def payload(**event_overrides):
    return {"type": "event_callback", "event_id": "Ev001", "team_id": "T123", "api_app_id": "A123",
            "event": {"type": "message", "channel": "C123", "user": "U111", "text": "검토 의견을 공유합니다.",
                      "ts": "1700000000.000001", "thread_ts": "1700000000.000000", **event_overrides}}


def envelope(data=None, **overrides):
    return SocketModeRequest(**{"type": "events_api", "envelope_id": "envelope-1", "payload": data or payload(), **overrides})


def test_persisted_api_response_precedes_socket_ack_and_payload_is_preserved():
    order, received = [], []
    def handler(request):
        order.append("api")
        received.append(request)
        return httpx.Response(200, json={"session_id": "s1", "duplicate": False})
    socket = FakeSocket(order)
    source = payload()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = SlackEventReceiver(config(), client).handle(socket, envelope(source))
    assert result["status"] == "forwarded"
    assert result["acknowledged"]
    assert order == ["api", "ack"]
    assert received[0].url == "http://127.0.0.1:8787/api/slack/events"
    assert json.loads(received[0].content) == source
    assert socket.responses[0].envelope_id == "envelope-1"


@pytest.mark.parametrize("subtype", [None, "bot_message"])
def test_bot_messages_are_included_even_without_user_field(subtype):
    received = []
    def handler(request):
        received.append(json.loads(request.content))
        return httpx.Response(200, json={"session_id": "s1"})
    source = payload(subtype=subtype, bot_id="B123", bot_profile={"name": "Pickle"})
    del source["event"]["user"]
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        SlackEventReceiver(config(), client).handle(FakeSocket(), envelope(source))
    assert received[0]["event"]["bot_id"] == "B123"
    assert "user" not in received[0]["event"]


@pytest.mark.parametrize("event_change,reason", [
    ({"channel": "COTHER"}, "channel_not_allowed"),
    ({"channel": "D111"}, "channel_not_allowed"),
    ({"subtype": "channel_join"}, "unsupported_message_subtype"),
    ({"subtype": "message_replied"}, "unsupported_message_subtype"),
    ({"type": "reaction_added"}, "not_message"),
])
def test_out_of_scope_events_are_acknowledged_without_api_or_slack_writes(event_change, reason):
    def handler(_):
        pytest.fail("Filtered event reached the local API")
    socket = FakeSocket()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = SlackEventReceiver(config(), client).handle(socket, envelope(payload(**event_change)))
    assert result == {"status": "ignored", "reason": reason}
    assert len(socket.responses) == 1


@pytest.mark.parametrize("event_change", [
    {"subtype": "message_changed", "hidden": True, "message": {"ts": "1700000000.000001", "text": "수정된 검토 의견", "user": "U111", "thread_ts": "1700000000.000000"}},
    {"subtype": "message_deleted", "hidden": True, "deleted_ts": "1700000000.000001", "previous_message": {"ts": "1700000000.000001", "text": "삭제 전 내용"}},
])
def test_edits_and_deletions_are_forwarded_as_events_not_new_message_text(event_change):
    received = []
    def handler(request):
        received.append(json.loads(request.content))
        return httpx.Response(200, json={"updated": True})
    source = payload(**event_change)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = SlackEventReceiver(config(), client).handle(FakeSocket(), envelope(source))
    assert result["acknowledged"]
    assert received == [source]


@pytest.mark.parametrize("status", [403, 422, 500, 503])
def test_api_rejection_is_not_acknowledged_or_mistaken_for_persistence(status):
    def handler(_):
        return httpx.Response(status, text="sensitive response details")
    socket = FakeSocket()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = SlackEventReceiver(config(), client).handle(socket, envelope())
    assert result["status"] == "retry"
    assert not result["acknowledged"]
    assert socket.responses == []
    assert "sensitive" not in repr(result)


def test_api_timeout_keeps_slack_event_retryable():
    def handler(request):
        raise httpx.ReadTimeout("xoxb-never-log-this", request=request)
    socket = FakeSocket()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = SlackEventReceiver(config(), client).handle(socket, envelope())
    assert result["reason"] == "api_unavailable"
    assert socket.responses == []


def test_event_identity_is_stable_across_receiver_restart_and_retry_envelopes():
    persisted, received = {}, []
    def handler(request):
        event = json.loads(request.content)
        received.append(event)
        duplicate = event["event_id"] in persisted
        persisted.setdefault(event["event_id"], event)
        return httpx.Response(200, json={"duplicate": duplicate, "session_id": "same-session"})
    source = payload()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first_socket, restarted_socket = FakeSocket(), FakeSocket()
        SlackEventReceiver(config(), client).handle(first_socket, envelope(source))
        SlackEventReceiver(config(), client).handle(restarted_socket, envelope(deepcopy(source), envelope_id="retry-envelope", retry_attempt=1))
    assert len(persisted) == 1
    assert received[0] == received[1]
    assert restarted_socket.responses[0].envelope_id == "retry-envelope"


def test_missing_event_identity_is_not_given_a_fabricated_random_id():
    source = payload()
    del source["event_id"]
    socket = FakeSocket()
    def handler(_):
        pytest.fail("Malformed event reached the local API")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = SlackEventReceiver(config(), client).handle(socket, envelope(source))
    assert result["reason"] == "missing_event_identity"
    assert len(socket.responses) == 1


def test_configuration_requires_environment_tokens_explicit_channels_and_loopback():
    values = {"SLACK_APP_TOKEN": "xapp-test-only", "SLACK_BOT_TOKEN": "xoxb-test-only", "SLACK_ALLOWED_CHANNELS": "C123, G456"}
    settings = SlackBridgeConfig.from_environ(values)
    assert settings.allowed_channels == frozenset({"C123", "G456"})
    assert "xapp-" not in repr(settings) and "xoxb-" not in repr(settings)
    for changes in ({"SLACK_APP_TOKEN": ""}, {"SLACK_BOT_TOKEN": ""}, {"SLACK_ALLOWED_CHANNELS": ""},
                    {"SLACK_ALLOWED_CHANNELS": "*"}, {"SLACK_ALLOWED_CHANNELS": "#general"},
                    {"ARBITER_API_URL": "https://remote.example"}):
        with pytest.raises(ValueError):
            SlackBridgeConfig.from_environ({**values, **changes})
    with pytest.raises(ValueError):
        config(api_url="https://remote.example")


def test_config_check_does_not_contact_slack_or_the_local_api(monkeypatch, capsys):
    for key, value in {"SLACK_APP_TOKEN": "xapp-test-only", "SLACK_BOT_TOKEN": "xoxb-test-only", "SLACK_ALLOWED_CHANNELS": "C123"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("arbiter.slack_bridge.SlackEventReceiver", lambda *_: pytest.fail("Configuration check created a network client"))
    root_logger = logging.getLogger()
    previous_handlers, previous_level = root_logger.handlers[:], root_logger.level
    try:
        main(["--check-config"])
    finally:
        root_logger.handlers = previous_handlers
        root_logger.setLevel(previous_level)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Configuration valid" in captured.err
    assert "xapp-" not in captured.err and "xoxb-" not in captured.err


def test_socket_client_registers_only_the_receiver_callback(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.socket_mode_request_listeners = []
    monkeypatch.setattr("arbiter.slack_bridge.SocketModeClient", Client)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as http:
        receiver = SlackEventReceiver(config(), http)
        socket = build_socket_client(config(), receiver)
    assert socket.socket_mode_request_listeners == [receiver.handle]
    assert socket.kwargs["app_token"] == "xapp-test-only"
    assert socket.kwargs["web_client"].token == "xoxb-test-only"


def test_log_filter_removes_credentials_and_websocket_ticket():
    record = logging.LogRecord("slack_sdk", logging.ERROR, __file__, 1,
                               "failed %s at wss://slack.example/socket?ticket=secret", ("xapp-test-only",), None)
    SecretRedactionFilter(("xapp-test-only", "xoxb-test-only")).filter(record)
    assert "xapp-test-only" not in record.getMessage()
    assert "ticket=secret" not in record.getMessage()


def test_app_manifest_is_channel_read_only_and_enables_socket_mode():
    manifest = json.loads((Path(__file__).resolve().parents[1] / "slack-app-manifest.json").read_text())
    assert set(manifest["oauth_config"]["scopes"]["bot"]) == {"channels:history", "groups:history"}
    assert set(manifest["settings"]["event_subscriptions"]["bot_events"]) == {"message.channels", "message.groups"}
    assert manifest["settings"]["socket_mode_enabled"]
    assert "chat:write" not in json.dumps(manifest)
