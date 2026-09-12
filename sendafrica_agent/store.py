from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import aiosqlite


class StoreError(Exception):
    """Raised when a session cannot be safely used by the requested identity."""


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
    """SQLite storage for dashboard sessions with bounded, account-scoped history."""

    def __init__(self, path: str):
        self.path = path
        self.db: aiosqlite.Connection | None = None
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._session_locks_lock = asyncio.Lock()

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        async with self._session_locks_lock:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = asyncio.Lock()
            return self._session_locks[session_id]

    async def connect(self) -> None:
        self.db = await aiosqlite.connect(self.path)
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA synchronous=NORMAL")
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

            CREATE INDEX IF NOT EXISTS idx_agent_messages_session_desc
                ON agent_messages (session_id, id DESC);
            CREATE INDEX IF NOT EXISTS idx_agent_sessions_account_updated
                ON agent_sessions (account_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS agent_phone_configs (
                phone       TEXT PRIMARY KEY,
                enabled     INTEGER NOT NULL DEFAULT 1,
                mode        TEXT NOT NULL DEFAULT 'off',
                persona     TEXT,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_turns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                phone       TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                message_id  TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_agent_turns_phone_desc
                ON agent_turns (phone, id DESC);
            """
        )
        await self.db.commit()

    async def close(self) -> None:
        if self.db is not None:
            await self.db.close()
            self.db = None

    def _require_db(self) -> aiosqlite.Connection:
        if self.db is None:
            raise StoreError("store is not connected")
        return self.db

    # --- Sessions -------------------------------------------------------------

    async def get_or_create_session(self, session_id: str, account_id: str, user_id: str) -> str:
        if not session_id or not account_id or not user_id:
            raise StoreError("session, account, and user identity are required")

        db = self._require_db()
        now = datetime.now(UTC).isoformat()
        session_lock = await self._get_session_lock(session_id)
        async with session_lock:
            await db.execute(
                "INSERT OR IGNORE INTO agent_sessions "
                "(id, account_id, user_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, account_id, user_id, now, now),
            )
            cur = await db.execute(
                "SELECT account_id, user_id FROM agent_sessions WHERE id = ?", (session_id,)
            )
            row = await cur.fetchone()
            await cur.close()
            if row is None:
                raise StoreError("unable to create session")
            if row["account_id"] != account_id or row["user_id"] != user_id:
                raise StoreError("session belongs to a different identity")
            await db.commit()
        return session_id

    # --- Inbound SMS configuration and history -------------------------------

    async def get_config(self, phone: str) -> dict[str, Any] | None:
        db = self._require_db()
        cur = await db.execute(
            "SELECT enabled, mode, persona FROM agent_phone_configs WHERE phone = ?", (phone,)
        )
        row = await cur.fetchone()
        await cur.close()
        if row is None:
            return None
        return {"enabled": bool(row["enabled"]), "mode": row["mode"], "persona": row["persona"]}

    async def append_turn(self, phone: str, role: str, content: str, message_id: str = "") -> None:
        db = self._require_db()
        now = datetime.now(UTC).isoformat()
        session_lock = await self._get_session_lock(phone)
        async with session_lock:
            await db.execute(
                "INSERT INTO agent_turns (phone, role, content, message_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (phone, role, content, message_id, now),
            )
            await db.commit()

    async def get_thread(self, phone: str, limit: int = 20) -> list[StoredMessage]:
        db = self._require_db()
        bounded_limit = max(1, min(limit, 100))
        cur = await db.execute(
            "SELECT id, phone, role, content, message_id, created_at "
            "FROM agent_turns WHERE phone = ? ORDER BY id DESC LIMIT ?",
            (phone, bounded_limit),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [
            StoredMessage(
                id=row["id"],
                session_id=row["phone"],
                role=row["role"],
                content=row["content"],
                tool_id=row["message_id"] or None,
                created_at=row["created_at"],
            )
            for row in reversed(rows)
        ]

    # --- Messages -------------------------------------------------------------

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str = "",
        tool_calls: list[dict[str, Any]] | None = None,
        tool_id: str | None = None,
    ) -> StoredMessage:
        db = self._require_db()
        now = datetime.now(UTC).isoformat()
        tool_calls_json = json.dumps(tool_calls or [], separators=(",", ":"))

        session_lock = await self._get_session_lock(session_id)
        async with session_lock:
            cur = await db.execute(
                "INSERT INTO agent_messages (session_id, role, content, tool_calls, tool_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, role, content, tool_calls_json, tool_id, now),
            )
            msg_id = cur.lastrowid
            await cur.close()
            await db.execute(
                "UPDATE agent_sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            await db.commit()

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
        db = self._require_db()
        bounded_limit = max(1, min(limit, 100))
        cur = await db.execute(
            "SELECT id, session_id, role, content, tool_calls, tool_id, created_at "
            "FROM agent_messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, bounded_limit),
        )
        rows = await cur.fetchall()
        await cur.close()

        messages: list[StoredMessage] = []
        for row in reversed(rows):
            try:
                tool_calls = json.loads(row["tool_calls"]) if row["tool_calls"] else []
            except (TypeError, ValueError):
                tool_calls = []
            messages.append(
                StoredMessage(
                    id=row["id"],
                    session_id=row["session_id"],
                    role=row["role"],
                    content=row["content"],
                    tool_calls=tool_calls,
                    tool_id=row["tool_id"],
                    created_at=row["created_at"],
                )
            )
        return messages

    async def get_session_messages_for_identity(self, session_id: str, account_id: str, user_id: str, limit: int = 100) -> list[StoredMessage]:
        db = self._require_db()
        cur = await db.execute("SELECT account_id, user_id FROM agent_sessions WHERE id = ?", (session_id,))
        owner = await cur.fetchone(); await cur.close()
        if owner is None or owner["account_id"] != account_id or owner["user_id"] != user_id:
            raise StoreError("session does not belong to this identity")
        return await self.get_session_messages(session_id, limit)

    async def list_sessions_for_identity(self, account_id: str, user_id: str, limit: int = 30) -> list[dict[str, Any]]:
        db = self._require_db()
        bounded_limit = max(1, min(limit, 100))
        cur = await db.execute("SELECT id, created_at, updated_at FROM agent_sessions WHERE account_id = ? AND user_id = ? ORDER BY updated_at DESC LIMIT ?", (account_id, user_id, bounded_limit))
        rows = await cur.fetchall(); await cur.close()
        result = []
        for row in rows:
            msg_cur = await db.execute("SELECT content FROM agent_messages WHERE session_id = ? AND role = 'user' ORDER BY id ASC LIMIT 1", (row["id"],))
            first = await msg_cur.fetchone(); await msg_cur.close()
            result.append({"session_id": row["id"], "title": (first["content"][:60] if first and first["content"] else "New conversation"), "created_at": row["created_at"], "updated_at": row["updated_at"]})
        return result
