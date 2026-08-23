from __future__ import annotations

import asyncio
import time
from typing import Any

from openai import AsyncOpenAI


class NgamiaError(Exception):
    """Raised when the Ngamia gateway rejects a request."""


class NgamiaClient:
    """Wrapper over the Ngamia OpenAI-compatible gateway (https://docs.ngamia.cc).

    Supports chat completion with tool calling (OpenAI wire format).
    """

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 45.0):
        if not api_key:
            raise NgamiaError("NGAMIA_API_KEY is required")
        self.model = model
        self._client = AsyncOpenAI(
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            timeout=timeout,
            max_retries=1,
        )
        self._models_cache: tuple[float, list[str]] | None = None
        self._models_lock = asyncio.Lock()

    async def list_models(self) -> list[str]:
        now = time.monotonic()
        if self._models_cache and now - self._models_cache[0] < 60:
            return list(self._models_cache[1])
        async with self._models_lock:
            now = time.monotonic()
            if self._models_cache and now - self._models_cache[0] < 60:
                return list(self._models_cache[1])
            try:
                models = await self._client.models.list()
            except Exception as exc:
                raise NgamiaError(f"list models failed: {exc}") from exc
            names = [getattr(m, "model", None) or m.id for m in models.data]
            self._models_cache = (now, names)
            return list(names)

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        max_tokens: int = 1000,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Execute a chat completion with optional tool definitions.

        Returns a dictionary with 'content' and optional 'tool_calls'.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise NgamiaError(f"chat completion failed: {exc}") from exc

        choice = resp.choices[0].message
        result: dict[str, Any] = {
            "content": choice.content or "",
            "tool_calls": [],
        }

        if choice.tool_calls:
            for tc in choice.tool_calls:
                result["tool_calls"].append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                })

        return result

    async def aclose(self) -> None:
        await self._client.close()
