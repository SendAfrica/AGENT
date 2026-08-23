from __future__ import annotations

import hmac

from starlette.types import ASGIApp, Receive, Scope, Send


class MCPAuthMiddleware:
    """Protect the remote MCP transport without affecting local stdio mode."""

    def __init__(self, app: ASGIApp, token: str):
        self.app = app
        self.token = token.strip()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        provided = authorization.removeprefix("Bearer ").strip()
        if not provided:
            provided = headers.get(b"x-mcp-token", b"").decode("latin-1").strip()

        if not self.token:
            await self._respond(send, 503, b"MCP remote authentication is not configured")
            return
        if not hmac.compare_digest(provided, self.token):
            await self._respond(send, 401, b"MCP authentication required")
            return
        await self.app(scope, receive, send)

    @staticmethod
    async def _respond(send: Send, status: int, body: bytes) -> None:
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/plain; charset=utf-8"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})
