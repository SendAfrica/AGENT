from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import aiosqlite


@dataclass
class ConversationTurn:
    role: str  # user | assistant
    content: str
    message_id: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Store:
    """SQLite-backed conversation memory store for SMS threads by phone number."""

    def __init__(self, path: str):
        self.path = path

    async def connect(self) -> None:
        self.db = await aiosqlite.connect(self.path)
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA busy_timeout=5000")
        await self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS sms_conversations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                phone       TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                message_id  TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sms_conversations_phone
                ON sms_conversations (phone, created_at);

            CREATE TABLE IF NOT EXISTS agent_configs (
                phone       TEXT PRIMARY KEY,
                mode        TEXT NOT NULL DEFAULT 'off',
                persona     TEXT,
                enabled     BOOLEAN NOT NULL DEFAULT 1,
                updated_at  TEXT NOT NULL
            );
            """
        )
        await self.db.commit()

    async def close(self) -> None:
        await self.db.close()

    # --- SMS Conversations ---------------------------------------------------

    async def append_turn(self, phone: str, role: str, content: str, message_id: str) -> None:
        cur = await self.db.execute(
            "INSERT INTO sms_conversations (phone, role, content, message_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                phone.strip().lower(),
                role,
                content,
                message_id,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await cur.close()
        await self.db.commit()

    async def get_thread(self, phone: str, limit: int = 20) -> list[ConversationTurn]:
        cur = await self.db.execute(
            "SELECT role, content, message_id, created_at FROM sms_conversations "
            "WHERE phone = ? ORDER BY id DESC LIMIT ?",
            (phone.strip().lower(), limit),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [
            ConversationTurn(
                role=row["role"],
                content=row["content"],
                message_id=row["message_id"],
                created_at=row["created_at"],
            )
            for row in reversed(rows)
        ]

    # --- Config Management ----------------------------------------------------

    async def set_config(self, phone: str, mode: str, persona: str | None = None, enabled: bool = True) -> None:
        await self.db.execute(
            "INSERT INTO agent_configs (phone, mode, persona, enabled, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(phone) DO UPDATE SET "
            "mode=excluded.mode, persona=excluded.persona, enabled=excluded.enabled, updated_at=excluded.updated_at",
            (
                phone.strip().lower(),
                mode,
                persona,
                1 if enabled else 0,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await self.db.commit()

    async def get_config(self, phone: str) -> dict[str, Any] | None:
        cur = await self.db.execute(
            "SELECT phone, mode, persona, enabled FROM agent_configs WHERE phone = ?",
            (phone.strip().lower(),),
        )
        row = await cur.fetchone()
        await cur.close()
        if not row:
            return None
        return {
            "phone": row["phone"],
            "mode": row["mode"],
            "persona": row["persona"],
            "enabled": bool(row["enabled"]),
        }

    async def list_configs(self) -> list[dict[str, Any]]:
        cur = await self.db.execute("SELECT phone, mode, persona, enabled FROM agent_configs")
        rows = await cur.fetchall()
        await cur.close()
        return [
            {
                "phone": row["phone"],
                "mode": row["mode"],
                "persona": row["persona"],
                "enabled": bool(row["enabled"]),
            }
            for row in rows
        ]
