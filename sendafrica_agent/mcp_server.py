from __future__ import annotations

import warnings
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .agent import Agent
from .capabilities import get_capabilities
from .chat import ChatRunner
from .config import Settings
from .docs import get_doc_topic, search_docs
from .mailafrica import MailAfricaClient
from .ngamia import NgamiaClient
from .policy import confirmation_decision, confirmation_payload
from .sendafrica import SendAfricaClient
from .store import Store

warnings.filterwarnings(
    "ignore",
    message="Field 'lifespan' has an incomplete definition",
    category=Warning,
)

MODES = ("auto", "draft", "off")


class Runtime:
    """Shared component container for MCP server and Webhook HTTP app across SMS & Email."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.sendafrica = SendAfricaClient(settings.sendafrica_api_base, settings.sendafrica_api_key)
        self.mailafrica = MailAfricaClient(settings.mailafrica_api_base, settings.mailafrica_api_key)
        self.ngamia = NgamiaClient(settings.ngamia_base_url, settings.ngamia_api_key, settings.ngamia_model)
        self.store = Store(str(settings.db_path))
        self.agent = Agent(settings, self.sendafrica, self.ngamia, self.store)
        self.chat = ChatRunner(settings, self.sendafrica, self.mailafrica, self.ngamia, self.store)
        self._connected = False

    async def connect(self) -> None:
        if self._connected:
            return
        await self.store.connect()
        self._connected = True

    async def aclose(self) -> None:
        if not self._connected:
            return
        self._connected = False
        await self.store.close()
        await self.sendafrica.aclose()
        await self.mailafrica.aclose()
        await self.ngamia.aclose()


def build_server(runtime: Runtime) -> FastMCP:
    @asynccontextmanager
    async def lifespan(_: FastMCP):
        await runtime.connect()
        try:
            yield {}
        finally:
            await runtime.aclose()

    allowed_hosts = [host.strip() for host in runtime.settings.agent_allowed_hosts.split(",") if host.strip()]
    allowed_origins = [origin.strip() for origin in runtime.settings.agent_allowed_origins.split(",") if origin.strip()]
    ts = TransportSecuritySettings(allowed_hosts=allowed_hosts, allowed_origins=allowed_origins)
    mcp = FastMCP("camel-assistant", lifespan=lifespan, transport_security=ts)
    sendafrica = runtime.sendafrica
    mailafrica = runtime.mailafrica
    ngamia = runtime.ngamia

    # ---- SendAfrica Dashboard Tool Surface (SMS) -----------------------------

    @mcp.tool()
    async def get_agent_capabilities() -> dict[str, Any]:
        """Discover service version, transports, tool safety, and SMS behavior."""
        return get_capabilities()

    @mcp.tool()
    async def send_sms(
        to: str,
        message: str,
        sender_id: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        """Send a single SMS with an optional registered sender and retry key."""
        return await sendafrica.send_sms(
            to,
            message,
            sender_id=sender_id or None,
            idempotency_key=idempotency_key or None,
        )

    @mcp.tool()
    async def send_bulk_sms(
        recipients: list[str],
        message: str,
        sender_id: str = "",
        idempotency_key: str = "",
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """Send bulk SMS; more than 10 recipients requires explicit confirmation."""
        args = {"recipients": recipients, "message": message, "confirmed": confirmed}
        decision = confirmation_decision("send_bulk_sms", args)
        if decision.required and not confirmed:
            return confirmation_payload("send_bulk_sms", args)
        return await sendafrica.send_bulk_sms(
            recipients,
            message,
            sender_id=sender_id or None,
            idempotency_key=idempotency_key or None,
        )

    @mcp.tool()
    async def get_delivery_status(message_id: str = "") -> dict[str, Any]:
        """Check delivery status for one public SendAfrica message ID."""
        if not message_id.strip():
            return {"error": "message_id_required"}
        return await sendafrica.get_delivery_status(message_id.strip())

    @mcp.tool()
    async def list_contacts(list_id: str = "1", query: str = "") -> list[dict[str, Any]]:
        """List or search contacts for the account."""
        return await sendafrica.list_contacts(list_id, search=query or None)

    @mcp.tool()
    async def create_campaign(
        name: str,
        message: str,
        contact_group_id: str,
        scheduled_at: str = "",
        confirmed: bool = False,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        """Create and schedule a bulk SMS campaign after explicit confirmation."""
        args = {"name": name, "message": message, "contact_list_id": contact_group_id, "confirmed": confirmed}
        if not confirmed:
            return confirmation_payload("create_campaign", args)
        return await sendafrica.create_campaign(
            name,
            contact_group_id,
            message,
            scheduled_at=scheduled_at or None,
            idempotency_key=idempotency_key or None,
        )

    @mcp.tool()
    async def get_account_balance() -> dict[str, Any]:
        """Check SMS credit / wallet balance."""
        return await sendafrica.get_balance()

    @mcp.tool()
    async def get_usage_summary(period: str = "this_month") -> dict[str, Any]:
        """Summarize SMS sent, delivered, and failed for a period."""
        logs = await sendafrica.list_sms_logs(limit=100)
        counts: dict[str, int] = {}
        for log in logs:
            status = str(log.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
        return {"period": period, "counts": counts, "logs_count": len(logs), "recent_logs": logs[:5]}

    # ---- MailAfrica Dashboard Tool Surface (Email - Phase 2) -----------------

    @mcp.tool()
    async def send_email(
        to: list[str],
        subject: str,
        body: str,
        from_address: str = "",
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """Send transactional email; more than 5 recipients requires confirmation."""
        args = {"to": to, "subject": subject, "body": body, "confirmed": confirmed}
        decision = confirmation_decision("send_email", args)
        if decision.required and not confirmed:
            return confirmation_payload("send_email", args)
        return await mailafrica.send_email(
            to=to, subject=subject, text_body=body, from_address=from_address or None
        )

    @mcp.tool()
    async def list_inbound_emails(address_id: int = 1, limit: int = 20) -> list[dict[str, Any]]:
        """List received inbound emails for a MailAfrica receiving address."""
        return await mailafrica.list_messages(address_id=address_id, limit=limit)

    @mcp.tool()
    async def get_email_balance() -> dict[str, Any]:
        """Get MailAfrica email balance and credit ledger."""
        return await mailafrica.balance()

    # ---- Documentation & SDK Tools (docs.sendafrica.online & sdk.sendafrica.online) ----

    @mcp.tool()
    async def search_documentation(query: str, target: str = "all") -> list[dict[str, Any]]:
        """Search documentation and SDK resources with a bounded local lookup."""
        return search_docs(query, target=target)

    @mcp.tool()
    async def get_documentation_topic(topic_id: str) -> dict[str, Any]:
        """Fetch full documentation content, endpoints, and code examples for a specific topic."""
        return get_doc_topic(topic_id)

    # ---- Gateway Tools ------------------------------------------------------

    @mcp.tool()
    async def list_models() -> list[str]:
        """List available AI models on the Ngamia gateway."""
        return await ngamia.list_models()

    return mcp
