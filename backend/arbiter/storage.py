"""Small durable session store; connections are local to each operation."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, updated_at TEXT NOT NULL, state TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS configuration (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def save(self, state: dict[str, Any]) -> None:
        state["updated_at"] = now()
        with self.connect() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, state=excluded.state",
                (state["id"], state["updated_at"], json.dumps(state, ensure_ascii=False)),
            )

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT state FROM sessions WHERE id=?", (session_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT state FROM sessions ORDER BY updated_at DESC").fetchall()
        return [json.loads(row[0]) for row in rows]

    def get_authority(self) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT value FROM configuration WHERE key='authority'").fetchone()
        return json.loads(row[0]) if row else {"grants": [], "precedence": []}

    def save_authority(self, registry: dict) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO configuration VALUES ('authority', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (json.dumps(registry, ensure_ascii=False),))

    def recover(self) -> None:
        for state in self.list():
            if state.get("brief_status") == "generating":
                state.update(brief_status="error", brief_generation_id=None,
                             brief_error="Briefing generation was interrupted by a server restart. Please generate it again.")
                self.save(state)
            if state.get("busy"):
                state.update(busy=False, status="stopped", stop_requested=False,
                             last_error="The run was interrupted by a server restart. You can resume from the saved state.")
                self.save(state)
