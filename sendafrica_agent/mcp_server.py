from __future__ import annotations

import warnings
from contextlib import asynccontextmanager
from typing import Any

warnings.filterwarnings(
    "ignore",
    message="Field 'lifespan' has an incomplete definition",
    category=Warning,
)

from mcp.server.fastmcp import FastMCP

from .agent import Agent
from .chat import ChatRunner
from .config import Settings
from .docs import get_doc_topic, search_docs
from .mailafrica import MailAfricaClient
from .ngamia import NgamiaClient
from .sendafrica import SendAfricaClient
from .store import Store

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
        await self.store.connect()
        self._connected = True

    async def aclose(self) -> None:
        if self._connected:
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

    mcp = FastMCP("camel-assistant", lifespan=lifespan)
    sendafrica = runtime.sendafrica
    mailafrica = runtime.mailafrica
    ngamia = runtime.ngamia
    store = runtime.store

    # ---- SendAfrica Dashboard Tool Surface (SMS) -----------------------------

    @mcp.tool()
    async def send_sms(to: str, message: str, sender_id: str = "") -> dict[str, Any]:
        """Send a single SMS to a recipient via SendAfrica."""
        return await sendafrica.send_sms(to, message, sender_id=sender_id or None)

    @mcp.tool()
    async def get_delivery_status(message_id: str = "") -> dict[str, Any]:
        """Check delivery status of sent SMS messages."""
        logs = await sendafrica.list_sms_logs(limit=10)
        return {"logs": logs}

    @mcp.tool()
    async def list_contacts(list_id: str = "1", query: str = "") -> list[dict[str, Any]]:
        """List or search contacts for the account."""
        return await sendafrica.list_contacts(list_id, search=query or None)

    @mcp.tool()
    async def create_campaign(
        name: str, message: str, contact_group_id: str, scheduled_at: str = ""
    ) -> dict[str, Any]:
        """Create and schedule a bulk SMS campaign."""
        return await sendafrica.create_campaign(
            name, contact_group_id, message, scheduled_at=scheduled_at or None
        )

    @mcp.tool()
    async def get_account_balance() -> dict[str, Any]:
        """Check SMS credit / wallet balance."""
        return await sendafrica.get_balance()

    @mcp.tool()
    async def get_usage_summary(period: str = "this_month") -> dict[str, Any]:
        """Summarize SMS sent, delivered, failed for a period."""
        logs = await sendafrica.list_sms_logs(limit=50)
        return {"period": period, "total_sent": len(logs), "recent_logs": logs[:5]}

    # ---- MailAfrica Dashboard Tool Surface (Email - Phase 2) -----------------

    @mcp.tool()
    async def send_email(
        to: list[str], subject: str, body: str, from_address: str = ""
    ) -> dict[str, Any]:
        """Send a transactional email through MailAfrica."""
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
        """Search documentation and SDK resources for docs.sendafrica.online and sdk.sendafrica.online."""
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
