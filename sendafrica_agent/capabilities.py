from __future__ import annotations

from typing import Any

SERVICE_VERSION = "0.2.0"


def get_capabilities() -> dict[str, Any]:
    return {
        "service": "sendafrica-agent",
        "version": SERVICE_VERSION,
        "chat": {
            "structured_response": True,
            "tool_events": True,
            "confirmation_required": True,
            "streaming": False,
        },
        "mcp": {
            "transports": ["stdio", "sse"],
            "remote_path": "/sse",
        },
        "tools": {
            "read_only_parallelism": True,
            "confirmation_required": ["send_bulk_sms (>10)", "create_campaign", "send_email (>5)"],
        },
        "sms": {
            "submission_status": "Success",
            "delivery_is_async": True,
            "encoding": ["GSM-7 septets", "UTF-16 code units"],
        },
    }
