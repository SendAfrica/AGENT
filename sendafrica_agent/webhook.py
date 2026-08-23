from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .auth_context import RequestCredentials, use_request_credentials
from .capabilities import SERVICE_VERSION, get_capabilities
from .config import Settings
from .mcp_auth import MCPAuthMiddleware
from .mcp_server import Runtime, build_server

logger = logging.getLogger("sendafrica_agent.webhook")

SIGNATURE_HEADERS = ("X-Webhook-Signature", "X-Signature")


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2000)
    user_confirmation: bool = False


def _csv_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id") or str(uuid.uuid4())


def _caller_credentials(
    authorization: str | None,
    x_api_key: str | None,
    account_id: str,
    user_id: str,
) -> RequestCredentials:
    if x_api_key and x_api_key.startswith("SA-"):
        return RequestCredentials(api_key=x_api_key, account_id=account_id, user_id=user_id)
    if authorization:
        token = authorization.removeprefix("Bearer ").strip()
        if token.startswith("SA-"):
            return RequestCredentials(api_key=token, account_id=account_id, user_id=user_id)
        return RequestCredentials(authorization=authorization, account_id=account_id, user_id=user_id)
    return RequestCredentials(account_id=account_id, user_id=user_id)


def create_app(settings: Settings) -> FastAPI:
    runtime = Runtime(settings)
    mcp_server = build_server(runtime)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await runtime.connect()
        yield
        await runtime.aclose()

    app = FastAPI(
        title="SendAfrica Agent & Dashboard Assistant",
        version=SERVICE_VERSION,
        lifespan=lifespan,
    )

    allowed_origins = _csv_values(settings.agent_allowed_origins)
    allowed_hosts = _csv_values(settings.agent_allowed_hosts)
    if allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Account-ID", "X-Request-Id"],
        expose_headers=["X-Request-Id"],
    )

    app.mount("/sse", MCPAuthMiddleware(mcp_server.sse_app(), settings.agent_mcp_auth_token))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": SERVICE_VERSION}

    @app.get("/ready")
    async def ready() -> JSONResponse:
        if not runtime._connected:
            return JSONResponse({"status": "starting", "version": SERVICE_VERSION}, status_code=503)
        return JSONResponse({"status": "ready", "version": SERVICE_VERSION})

    @app.get("/v1/agent/capabilities")
    async def capabilities() -> dict[str, object]:
        return get_capabilities()

    @app.post("/v1/agent/chat")
    async def dashboard_chat(
        req: ChatRequest,
        request: Request,
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
        x_account_id: str | None = Header(default=None),
        x_user_id: str | None = Header(default="default_user"),
    ) -> JSONResponse:
        """Structured dashboard chat endpoint with safe caller credential scoping."""
        request_id = _request_id(request)
        account_id = x_account_id or ""
        credentials = _caller_credentials(authorization, x_api_key, account_id, x_user_id or "default_user")
        if settings.agent_require_caller_auth and not (credentials.api_key or credentials.authorization):
            return JSONResponse(
                {"status": "unauthorized", "error": "API key or JWT is required", "request_id": request_id},
                status_code=401,
                headers={"X-Request-Id": request_id},
            )
        if not account_id:
            return JSONResponse(
                {"status": "validation_error", "error": "X-Account-ID is required", "request_id": request_id},
                status_code=400,
                headers={"X-Request-Id": request_id},
            )

        try:
            with use_request_credentials(credentials):
                result = await asyncio.wait_for(
                    runtime.chat.handle_user_message(
                        session_id=req.session_id,
                        account_id=account_id,
                        user_id=x_user_id or "default_user",
                        message_text=req.message,
                        user_confirmation=req.user_confirmation,
                    ),
                    timeout=settings.agent_request_timeout_seconds,
                )
            result["request_id"] = request_id
            return JSONResponse(result, headers={"X-Request-Id": request_id})
        except TimeoutError:
            logger.warning("dashboard chat timed out request_id=%s session=%s", request_id, req.session_id)
            return JSONResponse(
                {"status": "timeout", "error": "The assistant took too long to respond", "request_id": request_id},
                status_code=504,
                headers={"X-Request-Id": request_id},
            )
        except Exception:
            logger.exception("dashboard chat failed request_id=%s session=%s", request_id, req.session_id)
            return JSONResponse(
                {"status": "error", "error": "The assistant is temporarily unavailable", "request_id": request_id},
                status_code=503,
                headers={"X-Request-Id": request_id},
            )

    @app.post("/webhooks/sendafrica")
    async def sendafrica_webhook(request: Request) -> JSONResponse:
        request_id = _request_id(request)
        body = await request.body()
        if settings.agent_webhook_secret and not _verify_signature(
            body, request, settings.agent_webhook_secret
        ):
            return JSONResponse(
                {"status": "unauthorized", "request_id": request_id},
                status_code=401,
                headers={"X-Request-Id": request_id},
            )

        try:
            payload = await request.json()
        except ValueError:
            return JSONResponse(
                {"status": "invalid_json", "request_id": request_id},
                status_code=400,
                headers={"X-Request-Id": request_id},
            )

        event = payload.get("event")
        if event and event != "sms.inbound_received":
            return JSONResponse({"status": "ignored", "event": event, "request_id": request_id})

        from_phone = payload.get("from") or payload.get("from_phone") or payload.get("sender")
        text = payload.get("text") or payload.get("message") or payload.get("body")
        message_id = payload.get("id") or payload.get("message_id") or ""
        if not from_phone or not text:
            return JSONResponse(
                {"status": "missing_fields", "request_id": request_id},
                status_code=400,
                headers={"X-Request-Id": request_id},
            )

        logger.info("received inbound SMS webhook request_id=%s from=%s", request_id, from_phone)

        async def _run() -> None:
            try:
                await runtime.agent.handle_inbound_sms(from_phone, text, message_id=message_id)
            except Exception:
                logger.exception("agent pipeline failed request_id=%s from=%s", request_id, from_phone)

        asyncio.create_task(_run(), name=f"inbound-agent-{request_id}")
        return JSONResponse(
            {"status": "queued", "from": from_phone, "request_id": request_id},
            headers={"X-Request-Id": request_id},
        )

    return app


def _verify_signature(body: bytes, request: Request, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    for header in SIGNATURE_HEADERS:
        provided = request.headers.get(header)
        if provided and hmac.compare_digest(provided, expected):
            return True
    return False
