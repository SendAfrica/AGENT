from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ConfirmationDecision:
    required: bool
    action: str
    summary: str


def confirmation_decision(tool_name: str, args: dict[str, Any]) -> ConfirmationDecision:
    """Return the confirmation requirement for a potentially high-impact tool."""

    if tool_name == "send_bulk_sms":
        recipients = args.get("recipients") or []
        count = len(recipients)
        return ConfirmationDecision(
            required=count > 10,
            action=tool_name,
            summary=f"Send the SMS to {count} recipients",
        )

    if tool_name == "create_campaign":
        return ConfirmationDecision(
            required=True,
            action=tool_name,
            summary=f"Create campaign {args.get('name') or '(unnamed)'}",
        )

    if tool_name == "send_email":
        recipients = args.get("to") or []
        count = len(recipients)
        return ConfirmationDecision(
            required=count > 5,
            action=tool_name,
            summary=f"Send the email to {count} recipients",
        )

    if tool_name == "request_sender_id":
        return ConfirmationDecision(
            required=True,
            action=tool_name,
            summary=f"Request sender ID '{args.get('name') or '(unnamed)'}'",
        )

    return ConfirmationDecision(required=False, action=tool_name, summary="")


def confirmation_payload(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    decision = confirmation_decision(tool_name, args)
    payload: dict[str, Any] = {
        "status": "confirmation_required",
        "action": decision.action,
        "summary": decision.summary,
        "notice": "Explicit confirmation is required before this side effect is executed.",
    }
    if tool_name == "send_bulk_sms":
        payload["recipients_count"] = len(args.get("recipients") or [])
        payload["message"] = args.get("message", "")
    elif tool_name == "create_campaign":
        payload.update(
            {
                "name": args.get("name"),
                "contact_list_id": args.get("contact_list_id"),
                "message": args.get("message", ""),
            }
        )
    elif tool_name == "send_email":
        payload["recipients"] = args.get("to") or []
        payload["subject"] = args.get("subject", "")
    elif tool_name == "request_sender_id":
        payload["name"] = args.get("name")
        payload["purpose"] = args.get("purpose")
        payload["country"] = args.get("country") or "TZ"
    return payload
