from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import aiosqlite


@dataclass
class StoredMessage:
    id: int
    session_id: str
    role: str
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_id: str | None = None
    created_at: str = ""


class Store:
    """SQLite storage for Dashboard AI Agent chat sessions and message logs."""

    def __init__(self, path: str):
        self.path = path

    async def connect(self) -> None:
        self.db = await aiosqlite.connect(self.path)
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA busy_timeout=5000")
        await self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_sessions (
                id          TEXT PRIMARY KEY,
                account_id  TEXT NOT NULL,
                user_id     TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL DEFAULT '',
                tool_calls  TEXT NOT NULL DEFAULT '[]',
                tool_id     TEXT,
                created_at  TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES agent_sessions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_agent_messages_session
                ON agent_messages (session_id, id);
            """
        )
        await self.db.commit()

    async def close(self) -> None:
        await self.db.close()

    # --- Sessions -------------------------------------------------------------

    async def get_or_create_session(self, session_id: str, account_id: str, user_id: str) -> str:
        now = datetime.now(timezone.utc).isoformat()
        cur = await self.db.execute("SELECT id FROM agent_sessions WHERE id = ?", (session_id,))
        row = await cur.fetchone()
        await cur.close()

        if not row:
            await self.db.execute(
                "INSERT INTO agent_sessions (id, account_id, user_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, account_id, user_id, now, now),
            )
            await self.db.commit()
        return session_id

    # --- Messages -------------------------------------------------------------

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str = "",
        tool_calls: list[dict[str, Any]] | None = None,
        tool_id: str | None = None,
    ) -> StoredMessage:
        now = datetime.now(timezone.utc).isoformat()
        tool_calls_json = json.dumps(tool_calls or [])

        cur = await self.db.execute(
            "INSERT INTO agent_messages (session_id, role, content, tool_calls, tool_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, role, content, tool_calls_json, tool_id, now),
        )
        msg_id = cur.lastrowid
        await cur.close()
        await self.db.execute(
            "UPDATE agent_sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        await self.db.commit()

        return StoredMessage(
            id=msg_id,
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls or [],
            tool_id=tool_id,
            created_at=now,
        )

    async def get_session_messages(self, session_id: str, limit: int = 50) -> list[StoredMessage]:
        cur = await self.db.execute(
            "SELECT id, session_id, role, content, tool_calls, tool_id, created_at "
            "FROM agent_messages WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        )
        rows = await cur.fetchall()
        await cur.close()

        messages = []
        for row in rows:
            try:
                tc = json.loads(row["tool_calls"]) if row["tool_calls"] else []
            except Exception:
                tc = []
            messages.append(
                StoredMessage(
                    id=row["id"],
                    session_id=row["session_id"],
                    role=row["role"],
                    content=row["content"],
                    tool_calls=tc,
                    tool_id=row["tool_id"],
                    created_at=row["created_at"],
                )
            )
        return messages
