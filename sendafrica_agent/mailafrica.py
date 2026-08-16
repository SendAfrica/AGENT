from __future__ import annotations

from typing import Any

import httpx


class MailAfricaError(Exception):
    """Raised when the MailAfrica API returns an error envelope."""

    def __init__(self, code: str, message: str, status: int, request_id: str | None = None):
        self.code = code
        self.message = message
        self.status = status
        self.request_id = request_id
        super().__init__(f"MailAfrica {code}: {message} (status {status})")


class MailAfricaClient:
    """Async client for the MailAfrica API (https://api.mailafrica.online)."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        clean_path = path if path.startswith("/") else f"/{path}"
        resp = await self._client.request(method, f"/api{clean_path}", **kwargs)
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code >= 400 or not body.get("success", False):
            errors = body.get("errors") or []
            first = errors[0] if errors else {}
            raise MailAfricaError(
                code=first.get("code", "HTTP_ERROR"),
                message=first.get("message", body.get("message", resp.text[:200])),
                status=resp.status_code,
                request_id=body.get("request_id"),
            )
        return body.get("data") or {}

    # --- Outbound Email -------------------------------------------------------

    async def send_email(
        self,
        to: list[str],
        subject: str,
        text_body: str | None = None,
        html_body: str | None = None,
        from_address: str | None = None,
    ) -> dict[str, Any]:
        """Send a transactional email through MailAfrica."""
        payload: dict[str, Any] = {"to": to, "subject": subject}
        if text_body:
            payload["text_body"] = text_body
        if html_body:
            payload["html_body"] = html_body
        if from_address:
            payload["from_address"] = from_address
        return await self._request("POST", "/outbound/emails", json=payload)

    async def list_outbound(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent outbound email logs."""
        data = await self._request("GET", f"/outbound/emails?per_page={limit}")
        return data if isinstance(data, list) else []

    # --- Inbound Email & Addresses --------------------------------------------

    async def list_addresses(self) -> list[dict[str, Any]]:
        """List inbound email receiving addresses."""
        data = await self._request("GET", "/inbound/addresses")
        return data if isinstance(data, list) else []

    async def list_messages(self, address_id: int, limit: int = 20) -> list[dict[str, Any]]:
        """List received inbound emails for an address."""
        data = await self._request("GET", f"/inbound/messages?address_id={address_id}&per_page={limit}")
        return data if isinstance(data, list) else []

    # --- Billing --------------------------------------------------------------

    async def balance(self) -> dict[str, Any]:
        """Get MailAfrica wallet/credit balance."""
        return await self._request("GET", "/billing/balance")
