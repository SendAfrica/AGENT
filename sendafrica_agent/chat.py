from __future__ import annotations

import json
import logging
from typing import Any

from .config import Settings
from .mailafrica import MailAfricaClient
from .ngamia import NgamiaClient
from .sendafrica import SendAfricaClient
from .store import Store

logger = logging.getLogger("sendafrica_agent.chat")

SENDAFRICA_AGENT_SYSTEM_PROMPT = """You are the official Multi-Channel Assistant for SendAfrica (SMS) & MailAfrica (Email) — an intelligent in-app assistant embedded in the business dashboard.
You serve as both a knowledgeable support advisor and an action-taking agent capable of executing tools on behalf of business owners.

=== SENDAFRICA & MAILAFRICA KNOWLEDGE RESOURCE ===

1. PLATFORM OVERVIEW:
   - SendAfrica (https://app.sendafrica.online) is a Tanzania-first bulk SMS & messaging platform for developers and businesses.
   - MailAfrica (https://app.mailafrica.online) is a transactional and receiving email platform.
   - API Base URLs:
     * SendAfrica API: https://api.sendafrica.online/v1
     * MailAfrica API: https://api.mailafrica.online

2. CREDITS & PRICING (TZS):
   - SMS Billing: 1 SMS credit = 1 SMS part (up to 160 standard characters).
   - Pay-As-You-Go Voucher Rates:
     * Tier 1 (1,000 TZS to 49,999 TZS): 35 TZS per credit.
     * Tier 2 (50,000 TZS to 149,999 TZS): 32 TZS per credit.
     * Tier 3 (150,000 TZS and above): 30 TZS per credit.
   - Mobile Money Payments: Integrated via Snippe (M-Pesa, Tigo Pesa, Airtel Money, Halopesa) or manual bank transfer.
   - Signup Bonus: New registered accounts receive 5 free trial credits.

3. API KEYS & AUTHENTICATION:
   - SendAfrica API Keys start with prefix `SA-` (e.g., `SA-9f8a...`).
   - MailAfrica API Keys start with prefix `MA-` (e.g., `MA-3b1c...`).
   - Passed via `X-API-Key` header or `Authorization: Bearer <key>`.

4. CONTACTS & CAMPAIGNS:
   - Contact lists group recipients. Features include search, CSV import, and one-way Google Contacts sync.
   - Campaigns can be sent immediately or scheduled for future delivery (UTC timestamp).

5. TONAL GUIDANCE:
   - Be warm, helpful, personable, and clear. Avoid stiff corporate jargon.
   - If asked a general question about SendAfrica/MailAfrica features, pricing, or API setup, answer directly using the knowledge base above.
   - If asked to perform an action (check balance, send SMS, look up contacts, schedule campaign, send email), use your available tools.

=== SAFETY & CONFIRMATION GUARDRAILS ===
- BULK CAMPAIGNS & MASS EMAILS:
  * Before executing bulk SMS sends, scheduling mass campaigns, or sending emails to > 5 recipients, describe the planned action clearly (recipient count, message, subject) and ask for user confirmation.
  * If the action requires user confirmation and hasn't been confirmed yet, inform the user clearly and await explicit confirmation.
"""

TOOL_SCHEMAS = [
    # ---- SMS Tools (SendAfrica) ---------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_account_balance",
            "description": "Check current SMS credit and wallet balance for SendAfrica.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_usage_summary",
            "description": "Summarize SMS sent, delivered, and failed for a given time period.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["today", "this_week", "this_month"],
                        "description": "Time period summary.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_contacts",
            "description": "List or search contacts within the account phonebook.",
            "parameters": {
                "type": "object",
                "properties": {
                    "list_id": {"type": "string", "description": "Optional contact list ID"},
                    "search": {"type": "string", "description": "Search term for contact name or phone"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_delivery_status",
            "description": "Fetch delivery status for a specific SMS message ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "Message ID to query"}
                },
                "required": ["message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_sms",
            "description": "Send a single SMS message to a recipient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient phone number"},
                    "message": {"type": "string", "description": "SMS message text"},
                },
                "required": ["to", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_campaign",
            "description": "Create and schedule a bulk SMS campaign.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Campaign name"},
                    "contact_list_id": {"type": "string", "description": "Target contact list ID"},
                    "message": {"type": "string", "description": "Campaign message text"},
                    "confirmed": {
                        "type": "boolean",
                        "description": "Must be True if user explicitly confirmed campaign execution",
                    },
                },
                "required": ["name", "contact_list_id", "message"],
            },
        },
    },
    # ---- Email Tools (MailAfrica - Phase 2) ----------------------------------
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send a transactional email through MailAfrica.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of recipient email addresses",
                    },
                    "subject": {"type": "string", "description": "Email subject line"},
                    "body": {"type": "string", "description": "Email body content (text/markdown)"},
                    "from_address": {
                        "type": "string",
                        "description": "Sender address e.g. support@domain.com",
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": "Must be True if sending to > 5 recipients",
                    },
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_inbound_emails",
            "description": "List received inbound emails for a MailAfrica receiving address.",
            "parameters": {
                "type": "object",
                "properties": {
                    "address_id": {"type": "integer", "description": "Inbound address ID (default 1)"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_email_balance",
            "description": "Check MailAfrica email balance and credit ledger.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


class ChatRunner:
    """Orchestrates multi-turn chat sessions with tool calling and safety guardrails across SMS & Email."""

    def __init__(
        self,
        settings: Settings,
        sendafrica: SendAfricaClient,
        mailafrica: MailAfricaClient,
        ngamia: NgamiaClient,
        store: Store,
    ):
        self.settings = settings
        self.sendafrica = sendafrica
        self.mailafrica = mailafrica
        self.ngamia = ngamia
        self.store = store

    async def handle_user_message(
        self,
        session_id: str,
        account_id: str,
        user_id: str,
        message_text: str,
        user_confirmation: bool = False,
    ) -> dict[str, Any]:
        await self.store.get_or_create_session(session_id, account_id, user_id)
        await self.store.append_message(session_id, role="user", content=message_text)

        history = await self.store.get_session_messages(session_id, limit=30)
        messages_payload: list[dict[str, Any]] = [
            {"role": "system", "content": SENDAFRICA_AGENT_SYSTEM_PROMPT}
        ]

        for m in history:
            item: dict[str, Any] = {"role": m.role}
            if m.content:
                item["content"] = m.content
            if m.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in m.tool_calls
                ]
            if m.tool_id:
                item["tool_call_id"] = m.tool_id
            messages_payload.append(item)

        max_loops = 5
        loop_count = 0
        final_response_text = ""
        confirmation_required_data: dict[str, Any] | None = None

        while loop_count < max_loops:
            loop_count += 1
            llm_res = await self.ngamia.chat_with_tools(messages_payload, tools=TOOL_SCHEMAS)
            content = llm_res.get("content", "")
            tool_calls = llm_res.get("tool_calls", [])

            if not tool_calls:
                final_response_text = content
                await self.store.append_message(session_id, role="assistant", content=content)
                break

            await self.store.append_message(
                session_id, role="assistant", content=content, tool_calls=tool_calls
            )
            messages_payload.append({
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                tool_id = tc["id"]
                tool_name = tc["name"]
                try:
                    args = json.loads(tc["arguments"])
                except Exception:
                    args = {}

                tool_result, requires_confirm = await self._execute_tool(
                    tool_name, args, user_confirmation=user_confirmation
                )

                if requires_confirm:
                    confirmation_required_data = tool_result

                tool_result_str = json.dumps(tool_result)
                await self.store.append_message(
                    session_id, role="tool", content=tool_result_str, tool_id=tool_id
                )
                messages_payload.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": tool_result_str,
                })

        return {
            "session_id": session_id,
            "response": final_response_text or "Task completed.",
            "confirmation_required": confirmation_required_data,
        }

    async def _execute_tool(
        self, tool_name: str, args: dict[str, Any], user_confirmation: bool
    ) -> tuple[dict[str, Any], bool]:
        """Execute SMS or Email tool with guardrail check."""
        try:
            # ---- SendAfrica Tools -------------------------------------------
            if tool_name == "get_account_balance":
                res = await self.sendafrica.get_balance()
                return res, False

            elif tool_name == "get_usage_summary":
                res = await self.sendafrica.list_sms_logs(limit=50)
                return {"summary": "Recent usage fetched", "logs_count": len(res)}, False

            elif tool_name == "list_contacts":
                list_id = args.get("list_id") or "1"
                res = await self.sendafrica.list_contacts(list_id, search=args.get("search"))
                return {"contacts": res}, False

            elif tool_name == "get_delivery_status":
                res = await self.sendafrica.list_sms_logs(limit=10)
                return {"logs": res}, False

            elif tool_name == "send_sms":
                res = await self.sendafrica.send_sms(to=args["to"], message=args["message"])
                return res, False

            elif tool_name == "create_campaign":
                if not user_confirmation and not args.get("confirmed"):
                    return (
                        {
                            "status": "confirmation_required",
                            "action": "create_campaign",
                            "name": args.get("name"),
                            "contact_list_id": args.get("contact_list_id"),
                            "message": args.get("message"),
                            "notice": "Please explicitly confirm to execute campaign send.",
                        },
                        True,
                    )
                res = await self.sendafrica.create_campaign(
                    name=args["name"],
                    contact_list_id=args["contact_list_id"],
                    message=args["message"],
                )
                return res, False

            # ---- MailAfrica Tools (Phase 2) ----------------------------------
            elif tool_name == "send_email":
                recipients = args.get("to") or []
                if len(recipients) > 5 and not user_confirmation and not args.get("confirmed"):
                    return (
                        {
                            "status": "confirmation_required",
                            "action": "send_email",
                            "recipients": recipients,
                            "subject": args.get("subject"),
                            "notice": f"Sending email to {len(recipients)} recipients requires explicit user confirmation.",
                        },
                        True,
                    )
                res = await self.mailafrica.send_email(
                    to=recipients,
                    subject=args["subject"],
                    text_body=args.get("body"),
                    from_address=args.get("from_address"),
                )
                return res, False

            elif tool_name == "list_inbound_emails":
                addr_id = int(args.get("address_id") or 1)
                res = await self.mailafrica.list_messages(address_id=addr_id, limit=20)
                return {"messages": res}, False

            elif tool_name == "get_email_balance":
                res = await self.mailafrica.balance()
                return res, False

            else:
                return {"error": f"Unknown tool: {tool_name}"}, False

        except Exception as exc:
            logger.exception("tool execution error for %s", tool_name)
            return {"error": str(exc)}, False
