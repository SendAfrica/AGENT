from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RequestCredentials:
    """Credentials and identity attached to one inbound request/task."""

    api_key: str | None = None
    authorization: str | None = None
    account_id: str | None = None
    user_id: str | None = None


_current_credentials: ContextVar[RequestCredentials | None] = ContextVar(
    "sendafrica_request_credentials", default=None
)


def get_request_credentials() -> RequestCredentials | None:
    return _current_credentials.get()


@contextmanager
def use_request_credentials(credentials: RequestCredentials) -> Iterator[None]:
    """Scope caller credentials to the current async task and restore them reliably."""

    token: Token[RequestCredentials | None] = _current_credentials.set(credentials)
    try:
        yield
    finally:
        _current_credentials.reset(token)
