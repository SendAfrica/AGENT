from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI


class NgamiaError(Exception):
    """Raised when the Ngamia gateway rejects a chat completion."""


class NgamiaClient:
    """Thin wrapper over the Ngamia OpenAI-compatible gateway (https://docs.ngamia.cc)."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 60.0):
        if not api_key:
            raise NgamiaError("NGAMIA_API_KEY is required")
        self.model = model
        self._client = AsyncOpenAI(base_url=base_url.rstrip("/"), api_key=api_key, timeout=timeout)

    async def list_models(self) -> list[str]:
        try:
            models = await self._client.models.list()
        except Exception as exc:
            raise NgamiaError(f"list models failed: {exc}") from exc
        return [getattr(m, "model", None) or m.id for m in models.data]

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 300,
        temperature: float = 0.5,
    ) -> str:
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            raise NgamiaError(f"chat completion failed: {exc}") from exc
        content = resp.choices[0].message.content
        if not content:
            raise NgamiaError("chat completion returned an empty reply")
        return content.strip()

    async def aclose(self) -> None:
        await self._client.close()
