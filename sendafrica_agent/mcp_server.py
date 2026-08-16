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
    agent = runtime.agent
    store = runtime.store

    # ---- SMS Tools ---------------------------------------------------------

    @mcp.tool()
    async def send_sms(to: str, message: str, sender_id: str = "") -> dict[str, Any]:
        """Send a single SMS message via SendAfrica."""
        return await sendafrica.send_sms(to, message, sender_id=sender_id or None)

    @mcp.tool()
    async def send_bulk_sms(recipients: list[str], message: str, sender_id: str = "") -> dict[str, Any]:
        """Send bulk SMS messages to multiple recipients via SendAfrica."""
        return await sendafrica.send_bulk_sms(recipients, message, sender_id=sender_id or None)

    @mcp.tool()
    async def get_sms_logs(limit: int = 20, page: int = 1) -> list[dict[str, Any]]:
        """Fetch SMS delivery status logs from SendAfrica."""
        return await sendafrica.list_sms_logs(limit=limit, page=page)

    # ---- Credits & Billing Tools -------------------------------------------

    @mcp.tool()
    async def get_credit_balance() -> dict[str, Any]:
        """Check current SMS credit balance."""
        return await sendafrica.get_balance()

    @mcp.tool()
    async def get_credit_history(limit: int = 20, page: int = 1) -> list[dict[str, Any]]:
        """Get credit ledger transactions."""
        return await sendafrica.get_credit_history(limit=limit, page=page)

    @mcp.tool()
    async def get_voucher_rate() -> dict[str, Any]:
        """Fetch current pay-as-you-go voucher pricing tiers (TZS per credit)."""
        return await sendafrica.get_voucher_rate()

    # ---- Contacts Tools ----------------------------------------------------

    @mcp.tool()
    async def list_contact_lists() -> list[dict[str, Any]]:
        """List all contact lists in the SendAfrica phonebook."""
        return await sendafrica.list_contact_lists()

    @mcp.tool()
    async def create_contact_list(name: str, description: str = "") -> dict[str, Any]:
        """Create a new contact list in the SendAfrica phonebook."""
        return await sendafrica.create_contact_list(name, description=description or None)

    @mcp.tool()
    async def list_contacts(list_id: str, search: str = "") -> list[dict[str, Any]]:
        """List contacts within a specific contact list (optionally searched)."""
        return await sendafrica.list_contacts(list_id, search=search or None)

    @mcp.tool()
    async def create_contact(list_id: str, phone: str, name: str = "", email: str = "") -> dict[str, Any]:
        """Add a contact to a contact list."""
        return await sendafrica.create_contact(list_id, phone, name=name or None, email=email or None)

    # ---- Campaigns Tools ---------------------------------------------------

    @mcp.tool()
    async def list_campaigns() -> list[dict[str, Any]]:
        """List scheduled and completed SMS campaigns."""
        return await sendafrica.list_campaigns()

    @mcp.tool()
    async def create_campaign(
        name: str, contact_list_id: str, message: str, scheduled_at: str = ""
    ) -> dict[str, Any]:
        """Create and schedule an SMS campaign."""
        return await sendafrica.create_campaign(
            name, contact_list_id, message, scheduled_at=scheduled_at or None
        )

    @mcp.tool()
    async def get_campaign(campaign_id: str) -> dict[str, Any]:
        """Get campaign details and live recipient delivery statistics."""
        return await sendafrica.get_campaign(campaign_id)

    # ---- Payments Tools ----------------------------------------------------

    @mcp.tool()
    async def initiate_payment(
        phone_number: str, package_id: str = "", amount_tzs: float = 0.0, provider: str = "snippe"
    ) -> dict[str, Any]:
        """Initiate credit top-up order via mobile money (Snippe) or manual transfer."""
        return await sendafrica.initiate_payment(
            phone_number=phone_number,
            package_id=package_id or None,
            amount_tzs=amount_tzs if amount_tzs > 0 else None,
            provider=provider,
        )

    # ---- Agent & LLM Tools -------------------------------------------------

    @mcp.tool()
    async def agent_config(phone: str, mode: str = "off", persona: str = "", enabled: bool = True) -> dict[str, Any]:
        """Configure SMS auto-reply for a recipient phone number.
        mode is 'auto' (reply directly), 'draft' (generate preview), or 'off'."""
        if mode not in MODES:
            return {"error": f"mode must be one of {MODES}"}
        await store.set_config(phone, mode=mode, persona=persona or None, enabled=enabled)
        return {"status": "updated", "phone": phone, "mode": mode, "enabled": enabled}

    @mcp.tool()
    async def agent_get_config(phone: str) -> dict[str, Any]:
        """Get auto-reply configuration for a phone number."""
        cfg = await store.get_config(phone)
        return cfg or {"phone": phone, "mode": "off", "enabled": True}

    @mcp.tool()
    async def agent_handle_sms(phone: str, text: str) -> dict[str, Any]:
        """Manually trigger the SMS auto-reply pipeline for testing/simulation."""
        return await agent.handle_inbound_sms(phone, text)

    @mcp.tool()
    async def list_models() -> list[str]:
        """List available AI models on the Ngamia gateway."""
        return await ngamia.list_models()

    return mcp
