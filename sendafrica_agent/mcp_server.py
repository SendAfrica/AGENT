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
from .ngamia import NgamiaClient
from .sendafrica import SendAfricaClient
from .store import Store

MODES = ("auto", "draft", "off")


class Runtime:
    """Shared component container for MCP server and Webhook HTTP app."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.sendafrica = SendAfricaClient(settings.sendafrica_api_base, settings.sendafrica_api_key)
        self.ngamia = NgamiaClient(settings.ngamia_base_url, settings.ngamia_api_key, settings.ngamia_model)
        self.store = Store(str(settings.db_path))
        self.agent = Agent(settings, self.sendafrica, self.ngamia, self.store)
        self.chat = ChatRunner(settings, self.sendafrica, self.ngamia, self.store)
        self._connected = False

    async def connect(self) -> None:
        await self.store.connect()
        self._connected = True

    async def aclose(self) -> None:
        if self._connected:
            await self.store.close()
        await self.sendafrica.aclose()
        await self.ngamia.aclose()


def build_server(runtime: Runtime) -> FastMCP:
    @asynccontextmanager
    async def lifespan(_: FastMCP):
        await runtime.connect()
        try:
            yield {}
        finally:
            await runtime.aclose()

    mcp = FastMCP("sendafrica-agent", lifespan=lifespan)
    sendafrica = runtime.sendafrica
    ngamia = runtime.ngamia
    store = runtime.store

    # ---- SendAfrica Dashboard Tool Surface (v1) ------------------------------

    @mcp.tool()
    async def send_sms(to: str, message: str, sender_id: str = "") -> dict[str, Any]:
        """Send a single SMS to a recipient."""
        return await sendafrica.send_sms(to, message, sender_id=sender_id or None)

    @mcp.tool()
    async def get_delivery_status(message_id: str = "") -> dict[str, Any]:
        """Check delivery status of sent messages."""
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
        """Create and schedule a bulk campaign."""
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

    @mcp.tool()
    async def list_models() -> list[str]:
        """List available AI models on the Ngamia gateway."""
        return await ngamia.list_models()

    return mcp
