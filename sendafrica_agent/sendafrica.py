from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from .auth_context import get_request_credentials


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
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        api_key: str | None = None,
        authorization: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Make a request with caller credentials scoped to the current async task."""
        clean_path = path if path.startswith("/") else f"/{path}"
        headers = dict(kwargs.pop("headers", {}) or {})
        if "files" in kwargs:
            # Let httpx generate the multipart boundary and content type.
            headers.pop("Content-Type", None)
        credentials = get_request_credentials()
        if credentials is not None:
            api_key = credentials.api_key
            authorization = credentials.authorization

        headers.pop("X-API-Key", None)
        headers.pop("Authorization", None)
        if api_key:
            headers["X-API-Key"] = api_key
            headers["Authorization"] = f"Bearer {api_key}"
        elif authorization:
            headers["Authorization"] = authorization
        elif self.api_key:
            headers["X-API-Key"] = self.api_key
            headers["Authorization"] = f"Bearer {self.api_key}"

        resp = await self._client.request(method, clean_path, headers=headers, **kwargs)
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
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Send a single SMS message to a mobile number."""
        payload: dict[str, Any] = {"to": to, "message": message}
        if sender_id:
            payload["from"] = sender_id

        credentials = get_request_credentials()
        if credentials is not None:
            auth_header = credentials.authorization or (
                f"Bearer {credentials.api_key}" if credentials.api_key else ""
            )
        else:
            auth_header = f"Bearer {self.api_key}" if self.api_key else ""
        endpoint = "/sms/send" if auth_header.startswith("Bearer eyJ") else "/sms/"
        try:
            res = await self._request(
                "POST",
                endpoint,
                json=payload,
                headers={"Idempotency-Key": idempotency_key} if idempotency_key else None,
            )
        except SendAfricaError as err:
            if err.status in (401, 404) and endpoint == "/sms/":
                res = await self._request(
                    "POST",
                    "/sms/send",
                    json=payload,
                    headers={"Idempotency-Key": idempotency_key} if idempotency_key else None,
                )
            else:
                raise err

        return res if isinstance(res, dict) else {"result": res}

    async def send_bulk_sms(
        self,
        recipients: list[str],
        message: str,
        sender_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Send bulk SMS messages (up to 100 recipients per batch)."""
        payload: dict[str, Any] = {"to": recipients, "message": message}
        if sender_id:
            payload["from"] = sender_id
        res = await self._request(
            "POST",
            "/sms/bulk",
            json=payload,
            headers={"Idempotency-Key": idempotency_key} if idempotency_key else None,
        )
        return res if isinstance(res, dict) else {"result": res}

    async def list_sms_logs(
        self,
        limit: int = 20,
        page: int = 1,
        *,
        status: str | None = None,
        search: str | None = None,
        date_from: str | None = None,
    ) -> list[dict[str, Any]]:
        """List account-owned SMS logs with bounded filters."""
        params: dict[str, str | int] = {"per_page": max(1, min(limit, 200)), "page": max(1, page)}
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        if date_from:
            params["date_from"] = date_from
        res = await self._request("GET", f"/sms/logs?{urlencode(params)}")
        return res if isinstance(res, list) else []

    async def get_delivery_status(self, message_id: str) -> dict[str, Any]:
        """Find one public message log by its SendAfrica message ID."""
        public_id = message_id.removeprefix("SA-")
        logs = await self.list_sms_logs(limit=200)
        for log in logs:
            if str(log.get("id") or "") == public_id or str(log.get("message_id") or "") == message_id:
                return log
        return {"message_id": message_id, "status": "not_found"}

    # --- Credits & Billing ----------------------------------------------------

    async def get_balance(self) -> dict[str, Any]:
        """Get current credit balance and account details."""
        res = await self._request("GET", "/credits/balance")
        return res if isinstance(res, dict) else {"balance": res}

    async def get_credit_history(self, limit: int = 20, page: int = 1) -> list[dict[str, Any]]:
        """Get paginated credit transaction history."""
        params = urlencode({"per_page": max(1, min(limit, 200)), "page": max(1, page)})
        res = await self._request("GET", f"/credits/history?{params}")
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
        query = f"?{urlencode({'search': search})}" if search else ""
        res = await self._request("GET", f"/contact-lists/{list_id}/contacts{query}")
        return res if isinstance(res, list) else []

    async def import_contacts(self, list_id: str | int, csv_content: str, phone_column: str | None = None, name_column: str | None = None) -> dict[str, Any]:
        """Import CSV contacts through the account-scoped multipart API."""
        data: dict[str, str] = {}
        if phone_column:
            data["phone_column"] = phone_column
        if name_column:
            data["name_column"] = name_column
        res = await self._request(
            "POST",
            f"/contact-lists/{list_id}/import",
            data=data,
            files={"file": ("assistant-import.csv", csv_content.encode("utf-8"), "text/csv")},
            headers={},
        )
        return res if isinstance(res, dict) else {"result": res}

    async def create_contact(
        self,
        list_id: str | int,
        first_name: str,
        last_name: str | None = None,
        phone: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Add a contact to a contact list."""
        payload: dict[str, Any] = {"first_name": first_name}
        if last_name:
            payload["last_name"] = last_name
        if phone:
            payload["phone"] = phone
        if tags:
            payload["tags"] = tags
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
        sender_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Create and schedule an SMS campaign."""
        payload: dict[str, Any] = {
            "name": name,
            "contact_list_id": contact_list_id,
            "message": message,
        }
        if scheduled_at:
            payload["scheduled_at"] = scheduled_at
        if sender_id:
            payload["sender_id"] = sender_id
        res = await self._request(
            "POST",
            "/campaigns",
            json=payload,
            headers={"Idempotency-Key": idempotency_key} if idempotency_key else None,
        )
        return res if isinstance(res, dict) else {"result": res}

    async def get_campaign(self, campaign_id: str | int) -> dict[str, Any]:
        """Get details and stats for a specific campaign."""
        res = await self._request("GET", f"/campaigns/{campaign_id}")
        return res if isinstance(res, dict) else {"campaign": res}

    # --- Sender IDs -----------------------------------------------------------

    async def get_sender_id_requirements(self) -> dict[str, Any]:
        """Get registration requirements, rules, and eligibility for sender IDs."""
        res = await self._request("GET", "/sender-ids/requirements")
        return res if isinstance(res, dict) else {}

    async def list_sender_ids(self) -> list[dict[str, Any]]:
        """List sender IDs registered for the authenticated account."""
        res = await self._request("GET", "/sender-ids")
        return res if isinstance(res, list) else []

    async def get_sender_id(self, sender_id: str | int) -> dict[str, Any]:
        """Inspect a specific sender ID registered to the account."""
        res = await self._request("GET", f"/sender-ids/{sender_id}")
        return res if isinstance(res, dict) else {}

    async def list_usable_sender_ids(self, provider: str | None = None) -> list[dict[str, Any]]:
        """List platform defaults and account-approved custom sender IDs available for sends."""
        params: dict[str, str] = {}
        if provider:
            params["provider"] = provider
        res = await self._request("GET", f"/sender-ids/usable?{urlencode(params)}" if params else "/sender-ids/usable")
        return res if isinstance(res, list) else []

    async def request_sender_id(
        self,
        name: str,
        purpose: str,
        sample_message: str,
        country: str = "TZ",
        documents: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Submit a new sender ID registration request."""
        payload: dict[str, Any] = {
            "name": name,
            "country": country,
            "purpose": purpose,
            "sample_message": sample_message,
        }
        if documents:
            payload["documents"] = documents
        res = await self._request("POST", "/sender-ids", json=payload)
        return res if isinstance(res, dict) else {"result": res}

    # --- Payments -------------------------------------------------------------

    async def initiate_payment(
        self,
        phone: str,
        amount: int,
        package_id: str | int | None = None,
        provider: str = "snippe",
    ) -> dict[str, Any]:
        """Initiate top-up payment order (package or pay-as-you-go voucher)."""
        if package_id is not None:
            path = "/payments"
            payload: dict[str, Any] = {"phone": phone, "amount": amount, "package_id": package_id, "provider": provider}
        else:
            path = "/vouchers"
            payload = {"phone": phone, "amount": amount, "provider": provider}

        res = await self._request("POST", path, json=payload)
        return res if isinstance(res, dict) else {"result": res}
