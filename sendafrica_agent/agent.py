from __future__ import annotations

import logging
import re
from typing import Any

from .config import Settings
from .ngamia import NgamiaClient
from .sendafrica import SendAfricaClient
from .store import Store

logger = logging.getLogger("sendafrica_agent")

_PHONE_RE = re.compile(r"^\+?[0-9]{10,15}$")


class Agent:
    """The SMS auto-reply pipeline: inbound SMS -> turn history -> Ngamia -> SMS reply."""

    def __init__(self, settings: Settings, sendafrica: SendAfricaClient, ngamia: NgamiaClient, store: Store):
        self.settings = settings
        self.sendafrica = sendafrica
        self.ngamia = ngamia
        self.store = store

    async def handle_inbound_sms(
        self,
        from_phone: str,
        text: str,
        message_id: str = "",
    ) -> dict[str, Any]:
        phone = from_phone.strip()
        body = text.strip()

        if not phone or not body:
            logger.info("inbound sms skipped: missing phone or body")
            return {"action": "skipped", "reason": "empty phone or body"}

        cfg = await self.store.get_config(phone)
        mode = (cfg or {}).get("mode") or self.settings.agent_default_mode
        enabled = (cfg or {}).get("enabled", True)

        if mode not in ("auto", "draft") or not enabled:
            return {"action": "off", "mode": mode, "phone": phone}

        await self.store.append_turn(phone, "user", body, message_id)

        persona = (cfg or {}).get("persona") or self.settings.agent_default_persona
        history = await self.store.get_thread(phone, limit=20)

        llm_messages = [{"role": "system", "content": persona}]
        llm_messages += [{"role": t.role, "content": t.content} for t in history]

        if llm_messages[-1]["role"] != "user":
            llm_messages.append({"role": "user", "content": body})

        logger.info("generating SMS reply via Ngamia for %s", phone)
        reply = await self.ngamia.complete(llm_messages, max_tokens=250)

        out = {
            "phone": phone,
            "action": "draft" if mode == "draft" else "auto",
            "reply": reply,
        }

        if mode == "draft":
            await self.store.append_turn(phone, "assistant", reply, message_id)
            return out

        # Mode == "auto": Send actual outbound SMS reply
        idempotency_key = f"agent-inbound-{message_id}" if message_id else None
        send_res = await self.sendafrica.send_sms(
            to=phone,
            message=reply,
            idempotency_key=idempotency_key,
        )
        out["sent"] = send_res
        await self.store.append_turn(phone, "assistant", reply, message_id)
        return out
