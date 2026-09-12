from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_GSM_BASIC = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")


def sms_parts(message: str) -> tuple[int, str]:
    """Return conservative SMS part count and encoding for a preview."""
    if all(char in _GSM_BASIC for char in message):
        return (max(1, (len(message) + 152) // 153) if len(message) > 160 else 1, "GSM-7")
    return (max(1, (len(message) + 66) // 67) if len(message) > 70 else 1, "Unicode")


@dataclass(frozen=True, slots=True)
class ConfirmationDecision:
    required: bool
    action: str
    summary: str


def confirmation_decision(tool_name: str, args: dict[str, Any]) -> ConfirmationDecision:
    """Return the confirmation requirement for a potentially high-impact tool."""

    if tool_name in {"send_sms", "send_bulk_sms", "import_contacts"}:
        if tool_name == "import_contacts":
            return ConfirmationDecision(True, tool_name, f"Import contacts into list {args.get('list_id') or '(new list)'}")
        recipients = args.get("recipients") or []
        count = len(recipients) if tool_name == "send_bulk_sms" else 1
        return ConfirmationDecision(
            required=True,
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
            required=True,
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
    if tool_name == "send_sms":
        payload["recipient"] = args.get("to")
        payload["message"] = args.get("message", "")
        parts, encoding = sms_parts(str(args.get("message", "")))
        payload["sms_parts"] = parts
        payload["encoding"] = encoding
        payload["estimated_credits"] = parts
    elif tool_name == "send_bulk_sms":
        recipients_count = len(args.get("recipients") or [])
        payload["recipients_count"] = recipients_count
        payload["message"] = args.get("message", "")
        parts, encoding = sms_parts(str(args.get("message", "")))
        payload["sms_parts"] = parts
        payload["encoding"] = encoding
        payload["estimated_credits"] = parts * recipients_count
    elif tool_name == "import_contacts":
        payload["list_id"] = args.get("list_id")
        payload["phone_column"] = args.get("phone_column")
        payload["name_column"] = args.get("name_column")
        payload["notice"] = "Your CSV will be validated and imported into the selected contact list."
    elif tool_name == "create_campaign":
        payload.update(
            {
                "name": args.get("name"),
                "contact_list_id": args.get("contact_list_id"),
                "message": args.get("message", ""),
                "sender_id": args.get("sender_id"),
                "scheduled_at": args.get("scheduled_at"),
                "recipients_count": args.get("recipients_count"),
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
