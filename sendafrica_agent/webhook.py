from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .config import Settings
from .mcp_server import Runtime, build_server

logger = logging.getLogger("sendafrica_agent.webhook")

SIGNATURE_HEADERS = ("X-Webhook-Signature", "X-Signature")


class ChatRequest(BaseModel):
    session_id: str
    message: str
    user_confirmation: bool = False


def create_app(settings: Settings) -> FastAPI:
    runtime = Runtime(settings)
    mcp_server = build_server(runtime)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await runtime.connect()
        yield
        await runtime.aclose()

    app = FastAPI(title="SendAfrica Agent & Dashboard Assistant", lifespan=lifespan)

    # Enable CORS for dashboard UI integration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount FastMCP SSE App (serves /sse and /messages)
    app.mount("/sse", mcp_server.sse_app())

    @app.options("/{full_path:path}")
    async def options_handler(full_path: str):
        return JSONResponse(
            content={"status": "ok"},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
            },
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.options("/v1/agent/chat")
    async def dashboard_chat_options() -> JSONResponse:
        return JSONResponse(
            {"status": "ok"},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS, GET",
                "Access-Control-Allow-Headers": "*",
            },
        )

    @app.post("/v1/agent/chat")
    async def dashboard_chat(
        req: ChatRequest,
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
        x_account_id: str | None = Header(default="default_account"),
        x_user_id: str | None = Header(default="default_user"),
    ) -> JSONResponse:
        """Endpoint consumed by SendAfrica & MailAfrica Dashboard Chat Widgets & Assistant Pages.

        Accepts user chat input, maintains session history, executes MCP tools
        via Ngamia LLM tool-calling loop, and returns response or safety confirmation requests.
        """
        cors_headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS, GET",
            "Access-Control-Allow-Headers": "*",
        }

        original_sa_key = runtime.sendafrica._client.headers.get("X-API-Key")
        original_sa_auth = runtime.sendafrica._client.headers.get("Authorization")

        dynamic_key = x_api_key or (authorization.replace("Bearer ", "") if authorization else None)

        # Only apply dynamic key if valid SendAfrica API Key prefix
        if dynamic_key and dynamic_key.startswith("SA-"):
            runtime.sendafrica._client.headers["X-API-Key"] = dynamic_key
            runtime.sendafrica._client.headers["Authorization"] = f"Bearer {dynamic_key}"

        try:
            res = await runtime.chat.handle_user_message(
                session_id=req.session_id,
                account_id=x_account_id or "default_account",
                user_id=x_user_id or "default_user",
                message_text=req.message,
                user_confirmation=req.user_confirmation,
            )
            return JSONResponse(res, headers=cors_headers)
        except Exception as exc:
            logger.exception("dashboard chat failed for session %s", req.session_id)
            return JSONResponse({"error": str(exc)}, status_code=500, headers=cors_headers)
        finally:
            if original_sa_key:
                runtime.sendafrica._client.headers["X-API-Key"] = original_sa_key
            if original_sa_auth:
                runtime.sendafrica._client.headers["Authorization"] = original_sa_auth

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

        event = payload.get("event")
        if event and event != "sms.inbound_received":
            return JSONResponse({"status": "ignored", "event": event})

        from_phone = payload.get("from") or payload.get("from_phone") or payload.get("sender")
        text = payload.get("text") or payload.get("message") or payload.get("body")
        message_id = payload.get("id") or payload.get("message_id") or ""

        if not from_phone or not text:
            return JSONResponse({"status": "missing_fields"}, status_code=400)

        logger.info("received inbound SMS webhook from %s", from_phone)

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
