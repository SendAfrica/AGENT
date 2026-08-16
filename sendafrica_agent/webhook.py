from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings
from .mcp_server import Runtime

logger = logging.getLogger("sendafrica_agent.webhook")

SIGNATURE_HEADERS = ("X-Webhook-Signature", "X-Signature")


def create_app(settings: Settings) -> FastAPI:
    runtime = Runtime(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await runtime.connect()
        yield
        await runtime.aclose()

    app = FastAPI(title="SendAfrica Agent", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhooks/sendafrica")
    async def sendafrica_webhook(request: Request) -> JSONResponse:
        body = await request.body()
        if settings.agent_webhook_secret:
            if not _verify_signature(body, request, settings.agent_webhook_secret):
                return JSONResponse({"status": "unauthorized"}, status_code=401)

        try:
            payload = await request.json()
        except ValueError:
            return JSONResponse({"status": "invalid_json"}, status_code=400)

        # Handle inbound SMS callback payload from SendAfrica / Africa's Talking
        event = payload.get("event")
        if event and event != "sms.inbound_received":
            return JSONResponse({"status": "ignored", "event": event})

        from_phone = payload.get("from") or payload.get("from_phone") or payload.get("sender")
        text = payload.get("text") or payload.get("message") or payload.get("body")
        message_id = payload.get("id") or payload.get("message_id") or ""

        if not from_phone or not text:
            return JSONResponse({"status": "missing_fields"}, status_code=400)

        logger.info("received inbound SMS webhook from %s", from_phone)

        # Run pipeline asynchronously in background to ensure fast HTTP response
        async def _run() -> None:
            try:
                await runtime.agent.handle_inbound_sms(from_phone, text, message_id=message_id)
            except Exception:
                logger.exception("agent pipeline failed for SMS from %s", from_phone)

        asyncio.create_task(_run())
        return JSONResponse({"status": "queued", "from": from_phone})

    return app


def _verify_signature(body: bytes, request: Request, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    for header in SIGNATURE_HEADERS:
        provided = request.headers.get(header)
        if provided and hmac.compare_digest(provided, expected):
            return True
    return False
