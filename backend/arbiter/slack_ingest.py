"""Normalize allowlisted Slack events into durable, thread-scoped conversations."""
from __future__ import annotations

from hashlib import sha256
import os
import re

from .conversations import append_external_event, create_import, reanalyze_import
from .storage import now


def allowed_channels() -> list[str]:
    return list(dict.fromkeys(item.strip() for item in os.environ.get("SLACK_ALLOWED_CHANNELS", "").split(",") if item.strip()))


def ingest_slack(store, payload: dict) -> dict:
    channels = allowed_channels()
    if not channels:
        raise ValueError("SLACK_ALLOWED_CHANNELS에 수신할 채널 ID를 먼저 설정해 주세요.")
    if payload.get("type") != "event_callback":
        return {"accepted": False, "reason": "unsupported_envelope"}
    event = payload.get("event", {})
    if not isinstance(event, dict) or event.get("type") != "message":
        return {"accepted": False, "reason": "unsupported_event"}
    channel, team, event_id = event.get("channel", ""), payload.get("team_id", ""), payload.get("event_id", "")
    if channel not in channels:
        return {"accepted": False, "reason": "channel_not_allowed"}
    if not all(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value) for value in (channel, team, event_id)):
        raise ValueError("Slack 이벤트 식별자가 올바르지 않습니다.")
    subtype = event.get("subtype")
    if subtype not in (None, "bot_message", "thread_broadcast", "message_changed", "message_deleted"):
        return {"accepted": False, "reason": "unsupported_subtype"}
    deleted = subtype == "message_deleted"
    changed = subtype == "message_changed"
    message = event.get("message", {}) if changed else event.get("previous_message", {}) if deleted else event
    if not isinstance(message, dict):
        raise ValueError("Slack 메시지 형식이 올바르지 않습니다.")
    ts = event.get("deleted_ts") if deleted else message.get("ts")
    if not isinstance(ts, str) or not re.fullmatch(r"\d+\.\d+", ts):
        raise ValueError("Slack 메시지 시각이 없습니다.")
    thread = message.get("thread_ts") or ts
    states = [item for item in store.list() if item.get("slack", {}).get("team_id") == team
              and item["slack"].get("channel_id") == channel]
    # Edits/deletions may omit thread_ts. Resolve by the original message timestamp.
    existing = next((item for item in states if any(m.get("slack_ts") == ts for m in item["messages"])), None)
    sid = "slack-" + sha256(f"{team}:{channel}:{thread}".encode()).hexdigest()[:32]
    state = existing or store.get(sid)
    if state and event_id in state.get("slack", {}).get("event_ids", []):
        return {"accepted": True, "duplicate": True, "session_id": state["id"]}
    if deleted and not existing:
        return {"accepted": False, "reason": "unobserved_deleted_message"}
    text = message.get("text", "")
    if not deleted and (not isinstance(text, str) or not text.strip()):
        return {"accepted": False, "reason": "no_text"}
    if len(text) > 40000:
        raise ValueError("수신 가능한 메시지 길이를 초과했습니다.")
    actor = message.get("user") or message.get("bot_id") or "slack-unknown"
    if not isinstance(actor, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", actor):
        raise ValueError("발화자 식별자가 올바르지 않습니다.")
    if state is None:
        state = create_import(f"{actor}: 수신 메시지", f"Slack · {channel} · {thread}", "slack")
        state.update(id=sid, created_at=now(), busy=False, stop_requested=False, last_error=None)
        state["messages"][0].update(content=text, slack_ts=ts, external_id=event_id,
                                    provenance="slack_event", participant_type="Agent" if message.get("bot_id") else "Unknown")
        state["evidence"][0]["summary"] = text
        state["slack"] = {"team_id": team, "channel_id": channel, "thread_ts": thread, "event_ids": []}
        reanalyze_import(state)
    else:
        original = next((item for item in state["messages"] if item.get("slack_ts") == ts), None)
        if original:
            # A repeated ordinary delivery has no new semantic content.
            if changed or deleted:
                original.update(content="[Slack에서 삭제된 메시지]" if deleted else text, deleted=deleted,
                                edited=changed, last_slack_event_id=event_id)
                evidence = next((item for item in state["evidence"] if item["id"] == original["id"]), None)
                if evidence:
                    evidence.update(summary=original["content"], status="deleted" if deleted else "active")
                reanalyze_import(state)
        else:
            append_external_event(state, {"event_id": event_id, "agent": actor, "content": text})
            state["messages"][-1].update(slack_ts=ts, provenance="slack_event",
                                         participant_type="Agent" if message.get("bot_id") else "Unknown")
    state["slack"]["event_ids"].append(event_id)
    state["slack"]["last_received_at"] = now()
    store.save(state)
    return {"accepted": True, "duplicate": False, "session_id": state["id"], "status": state["status"]}
