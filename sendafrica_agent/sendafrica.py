from __future__ import annotations

from typing import Any

import httpx


class SendAfricaError(Exception):
    """Raised when the SendAfrica API returns an error envelope."""

    def __init__(self, code: str, message: str, status: int, request_id: str | None = None):
        self.code = code
        self.message = message
        self.status = status
        self.request_id = request_id
        super().__init__(f"SendAfrica {code}: {message} (status {status})")


class SendAfricaClient:
    """Async client for the SendAfrica API (https://api.sendafrica.online/v1).

    Authenticates via Authorization: Bearer SA-... or X-API-Key headers.
    Responses arrive in the envelope {"success": bool, "data": {...}, "message": str, "error": {...}}.
    """

    def __init__(self, base_url: str, api_key: str, timeout: float = 20.0):
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-API-Key": api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        # Handle path formatting cleanly
        clean_path = path if path.startswith("/") else f"/{path}"
        resp = await self._client.request(method, clean_path, **kwargs)
        try:
            body = resp.json()
        except ValueError:
            body = {}

        if resp.status_code >= 400 or (isinstance(body, dict) and body.get("success") is False):
            err_info = body.get("error") if isinstance(body, dict) else None
            code = "HTTP_ERROR"
            message = resp.text[:200]
            if isinstance(err_info, dict):
                code = err_info.get("code", "ERROR")
                message = err_info.get("message", message)
            elif isinstance(body, dict) and body.get("message"):
                message = body.get("message")

            raise SendAfricaError(
                code=code,
                message=message,
                status=resp.status_code,
                request_id=resp.headers.get("X-Request-Id"),
            )

        if isinstance(body, dict) and "data" in body:
            return body["data"]
        return body

    # --- SMS Endpoints --------------------------------------------------------

    async def send_sms(
        self,
        to: str,
        message: str,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a single SMS message to a mobile number."""
        payload: dict[str, Any] = {"to": to, "message": message}
        if sender_id:
            payload["sender_id"] = sender_id
        res = await self._request("POST", "/sms", json=payload)
        return res if isinstance(res, dict) else {"result": res}

    async def send_bulk_sms(
        self,
        recipients: list[str],
        message: str,
        sender_id: str | None = None,
    ) -> dict[str, Any]:
        """Send bulk SMS messages (up to 100 recipients per batch)."""
        payload: dict[str, Any] = {"recipients": recipients, "message": message}
        if sender_id:
            payload["sender_id"] = sender_id
        res = await self._request("POST", "/sms/bulk", json=payload)
        return res if isinstance(res, dict) else {"result": res}

    async def list_sms_logs(self, limit: int = 20, page: int = 1) -> list[dict[str, Any]]:
        """List SMS delivery status logs."""
        res = await self._request("GET", f"/sms/logs?per_page={limit}&page={page}")
        return res if isinstance(res, list) else []

    # --- Credits & Billing ----------------------------------------------------

    async def get_balance(self) -> dict[str, Any]:
        """Get current credit balance and account details."""
        res = await self._request("GET", "/credits/balance")
        return res if isinstance(res, dict) else {"balance": res}

    async def get_credit_history(self, limit: int = 20, page: int = 1) -> list[dict[str, Any]]:
        """Get paginated credit transaction history."""
        res = await self._request("GET", f"/credits/history?per_page={limit}&page={page}")
        return res if isinstance(res, list) else []

    async def get_voucher_rate(self) -> dict[str, Any]:
        """Get current pay-as-you-go voucher pricing tiers."""
        res = await self._request("GET", "/vouchers/rate")
        return res if isinstance(res, dict) else {"rate": res}

    # --- Contacts & Phonebook -------------------------------------------------

    async def list_contact_lists(self) -> list[dict[str, Any]]:
        """List all contact lists."""
        res = await self._request("GET", "/contact-lists")
        return res if isinstance(res, list) else []

    async def create_contact_list(self, name: str, description: str | None = None) -> dict[str, Any]:
        """Create a new contact list."""
        payload: dict[str, Any] = {"name": name}
        if description:
            payload["description"] = description
        res = await self._request("POST", "/contact-lists", json=payload)
        return res if isinstance(res, dict) else {"result": res}

    async def list_contacts(self, list_id: str | int, search: str | None = None) -> list[dict[str, Any]]:
        """List contacts in a specific contact list."""
        query = f"?search={search}" if search else ""
        res = await self._request("GET", f"/contact-lists/{list_id}/contacts{query}")
        return res if isinstance(res, list) else []

    async def create_contact(
        self,
        list_id: str | int,
        phone: str,
        name: str | None = None,
        email: str | None = None,
    ) -> dict[str, Any]:
        """Add a contact to a contact list."""
        payload: dict[str, Any] = {"phone": phone}
        if name:
            payload["name"] = name
        if email:
            payload["email"] = email
        res = await self._request("POST", f"/contact-lists/{list_id}/contacts", json=payload)
        return res if isinstance(res, dict) else {"result": res}

    # --- Campaigns ------------------------------------------------------------

    async def list_campaigns(self) -> list[dict[str, Any]]:
        """List scheduled and completed SMS campaigns."""
        res = await self._request("GET", "/campaigns")
        return res if isinstance(res, list) else []

    async def create_campaign(
        self,
        name: str,
        contact_list_id: str | int,
        message: str,
        scheduled_at: str | None = None,
    ) -> dict[str, Any]:
        """Create and schedule an SMS campaign."""
        payload: dict[str, Any] = {
            "name": name,
            "contact_list_id": contact_list_id,
            "message": message,
        }
        if scheduled_at:
            payload["scheduled_at"] = scheduled_at
        res = await self._request("POST", "/campaigns", json=payload)
        return res if isinstance(res, dict) else {"result": res}

    async def get_campaign(self, campaign_id: str | int) -> dict[str, Any]:
        """Get details and stats for a specific campaign."""
        res = await self._request("GET", f"/campaigns/{campaign_id}")
        return res if isinstance(res, dict) else {"campaign": res}

    # --- Payments -------------------------------------------------------------

    async def initiate_payment(
        self,
        phone_number: str,
        package_id: str | int | None = None,
        amount_tzs: float | None = None,
        provider: str = "snippe",
    ) -> dict[str, Any]:
        """Initiate top-up payment order (package or pay-as-you-go voucher)."""
        if amount_tzs is not None:
            path = "/vouchers"
            payload: dict[str, Any] = {"phone_number": phone_number, "amount_tzs": amount_tzs, "provider": provider}
        else:
            path = "/payments"
            payload = {"phone_number": phone_number, "package_id": package_id, "provider": provider}

        res = await self._request("POST", path, json=payload)
        return res if isinstance(res, dict) else {"result": res}
