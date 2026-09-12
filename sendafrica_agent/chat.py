from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from .capabilities import get_capabilities
from .config import Settings
from .docs import get_doc_topic, search_docs
from .mailafrica import MailAfricaClient
from .ngamia import NgamiaClient
from .policy import confirmation_decision, confirmation_payload
from .sendafrica import SendAfricaClient
from .store import Store

logger = logging.getLogger("sendafrica_agent.chat")

_READ_ONLY_TOOLS = {
    "get_agent_capabilities",
    "search_documentation",
    "get_documentation_topic",
    "get_account_balance",
    "get_usage_summary",
    "list_contacts",
    "list_contact_lists",
    "get_delivery_status",
    "list_inbound_emails",
    "get_email_balance",
    "list_models",
    "get_sender_id_requirements",
    "list_sender_ids",
    "get_sender_id",
    "list_usable_sender_ids",
}
_MAX_TOOL_RESULT_CHARS = 12_000

SENDAFRICA_AGENT_SYSTEM_PROMPT = """You are the official Multi-Channel Assistant for SendAfrica (SMS) & MailAfrica (Email) — an intelligent in-app assistant embedded in the business dashboard.
You serve as both a knowledgeable support advisor and an action-taking agent capable of executing tools on behalf of business owners.

=== SENDAFRICA & MAILAFRICA KNOWLEDGE RESOURCE ===

1. PLATFORM OVERVIEW:
   - SendAfrica (https://app.sendafrica.online) is an SMS and messaging platform for Tanzania and supported international destinations.
   - MailAfrica (https://app.mailafrica.online) is a transactional and receiving email platform.
   - Documentation & SDK Portals:
     * REST API Docs: https://docs.sendafrica.online
     * SDK Libraries: https://sdk.sendafrica.online (Python, Node.js/TypeScript, PHP, C#, C++, Dart)
   - API Base URLs:
     * SendAfrica API: https://api.sendafrica.online/v1
     * MailAfrica API: https://api.mailafrica.online

2. CREDITS & PRICING (TZS):
   - SMS Billing: GSM-7 uses septets (160 single / 153 multipart); Unicode uses UTF-16 code units (70 single / 67 multipart). Credits use the destination rate card; Tanzania Tier 1 is 1 credit per part.
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

5. DOCUMENTATION & SDK ASSISTANCE:
   - If a developer or user asks how to integrate SendAfrica, install SDKs, configure webhooks, or query endpoints, explain clearly with code samples.
   - Use the `search_documentation` and `get_documentation_topic` tools whenever needed to pull precise docs and SDK snippets for Python, Node.js, PHP, cURL, or Webhooks.

6. TONAL GUIDANCE & MANDATORY TOOL EXECUTION:
   - Be warm, helpful, personable, and concise. Avoid stiff corporate filler.
   - If asked a general question about SendAfrica/MailAfrica features, pricing, docs, or API setup, answer directly. Treat `Success` as provider submission, not handset delivery; use logs for final state.
   - CRITICAL TOOL CALLING RULE: You are an autonomous action-taking agent. WHENEVER the user asks to send an SMS, send an email, check balance, list contacts, or execute any supported feature, YOU MUST EXECUTE THE CORRESPONDING TOOL DIRECTLY (e.g. `send_sms`, `send_email`, `get_account_balance`, `list_contacts`).
   - NEVER reply with text telling the user to log into the dashboard or manually send an SMS. You ARE the action-taking assistant.
   - If the user asks to send an SMS to a phone number (e.g., `0628587749`) and does not specify a message, set `message="Hello! This is a test SMS sent via SendAfrica AI Agent."` and call `send_sms(to="0628587749", message=...)` IMMEDIATELY.

7. CONCISE MARKDOWN & NO FILLER:
   - When generating guides or technical answers, DO NOT include conversational filler like "Certainly! Here's a step-by-step guide...", "Sure, here is...", or "By following these steps...".
   - Jump straight into the guide headers (`### Step 1: ...`) and clean code blocks (` ```bash `, ` ```python `).

=== SAFETY & CONFIRMATION GUARDRAILS ===
- BULK CAMPAIGNS & MASS EMAILS:
  * Before executing bulk SMS sends, scheduling mass campaigns, or sending emails to > 5 recipients, describe the planned action clearly (recipient count, message, subject) and ask for user confirmation.
  * If the action requires user confirmation and hasn't been confirmed yet, inform the user clearly and await explicit confirmation.
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_agent_capabilities",
            "description": "Discover Agent version, chat features, MCP transports, tool safety, and SMS behavior.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ---- SMS Tools (SendAfrica) ---------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "list_contact_lists",
            "description": "List contact lists available to the authenticated account, including IDs and counts.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "import_contacts",
            "description": "Import contacts from CSV into an existing contact list. Always requires confirmation.",
            "parameters": {"type": "object", "properties": {
                "list_id": {"type": "string", "description": "Existing contact list ID"},
                "csv_content": {"type": "string", "description": "CSV text to import"},
                "phone_column": {"type": "string", "description": "Optional phone column header"},
                "name_column": {"type": "string", "description": "Optional full-name column header"},
                "confirmed": {"type": "boolean"}
            }, "required": ["list_id", "csv_content"]},
        },
    },
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
                    "sender_id": {"type": "string", "description": "Optional registered sender ID"},
                    "idempotency_key": {"type": "string", "description": "Stable retry key for this logical send"},
                },
                "required": ["to", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_bulk_sms",
            "description": "Send an SMS message to 2 or more recipient phone numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipients": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of recipient phone numbers e.g. ['0712345678', '0787654321']",
                    },
                    "message": {"type": "string", "description": "SMS message text"},
                    "sender_id": {"type": "string", "description": "Optional registered sender ID"},
                    "idempotency_key": {"type": "string", "description": "Stable retry key for this logical send"},
                    "confirmed": {
                        "type": "boolean",
                        "description": "Must be True if sending to more than 10 recipients",
                    },
                },
                "required": ["recipients", "message"],
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
                    "sender_id": {"type": "string", "description": "Optional registered sender ID"},
                    "scheduled_at": {"type": "string", "description": "Optional UTC schedule timestamp"},
                    "idempotency_key": {"type": "string", "description": "Stable retry key for this campaign"},
                    "confirmed": {
                        "type": "boolean",
                        "description": "Must be True if user explicitly confirmed campaign execution",
                    },
                },
                "required": ["name", "contact_list_id", "message"],
            },
        },
    },
    # ---- Sender ID Tools -----------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_sender_id_requirements",
            "description": "Get registration requirements, eligibility, and rules for sender IDs.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_sender_ids",
            "description": "List sender IDs registered for the authenticated account.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sender_id",
            "description": "Inspect a specific sender ID by its ID or name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sender_id": {"type": "string", "description": "Sender ID UUID or registered name"}
                },
                "required": ["sender_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_usable_sender_ids",
            "description": "List platform defaults and approved custom sender IDs available for sends.",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "description": "Optional provider filter: swala or africastalking"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_sender_id",
            "description": "Submit a new sender ID registration request (free). Requires explicit confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Sender ID name (3-11 chars, letters/numbers/spaces)"},
                    "purpose": {"type": "string", "description": "Purpose e.g. Notification, Transactional, OTP, Marketing"},
                    "sample_message": {"type": "string", "description": "A real example message (50-500 chars)"},
                    "country": {"type": "string", "description": "Country code, defaults to TZ"},
                    "documents": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Optional supporting documents with requirement_uid, filename, content_base64",
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": "Must be True if user explicitly confirmed sender ID registration",
                    },
                },
                "required": ["name", "purpose", "sample_message"],
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
    # ---- Documentation & SDK Tools (docs.sendafrica.online & sdk.sendafrica.online) ----
    {
        "type": "function",
        "function": {
            "name": "search_documentation",
            "description": "Search docs.sendafrica.online REST API and sdk.sendafrica.online SDK resources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Topic or keyword e.g. 'python', 'webhook', 'send sms'"},
                    "target": {"type": "string", "description": "all, docs.sendafrica.online, or sdk.sendafrica.online"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_documentation_topic",
            "description": "Get detailed documentation, code examples, and setup guide for a topic_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string", "description": "Topic ID e.g. 'python_sdk', 'sms_send', 'webhooks'"}
                },
                "required": ["topic_id"],
            },
        },
    },
]


class ChatRunner:
    """Orchestrates multi-turn chat sessions with tool calling and safety guardrails across SMS, Email & Docs."""

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
        message_text = message_text.strip()
        if not message_text:
            return {
                "session_id": session_id,
                "status": "validation_error",
                "response": "Message cannot be empty.",
                "tool_events": [],
            }

        await self.store.get_or_create_session(session_id, account_id, user_id)
        await self.store.append_message(session_id, role="user", content=message_text)

        history = await self.store.get_session_messages(
            session_id, limit=self.settings.agent_chat_history_limit
        )
        messages_payload: list[dict[str, Any]] = [
            {"role": "system", "content": SENDAFRICA_AGENT_SYSTEM_PROMPT}
        ]

        for stored in history:
            item: dict[str, Any] = {"role": stored.role}
            if stored.content:
                item["content"] = stored.content
            if stored.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": call["arguments"],
                        },
                    }
                    for call in stored.tool_calls
                ]
            if stored.tool_id:
                item["tool_call_id"] = stored.tool_id
            messages_payload.append(item)

        max_loops = max(1, self.settings.agent_chat_max_loops)
        loop_count = 0
        final_response_text = ""
        confirmation_required_data: dict[str, Any] | None = None
        events: list[dict[str, Any]] = []

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
            messages_payload.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": call["arguments"],
                            },
                        }
                        for call in tool_calls
                    ],
                }
            )

            async def execute_call(call: dict[str, Any]) -> tuple[dict[str, Any], bool, float]:
                started = time.perf_counter()
                try:
                    args = json.loads(call.get("arguments", "{}"))
                except (TypeError, ValueError):
                    args = {}
                try:
                    result, requires_confirm = await asyncio.wait_for(
                        self._execute_tool(
                            tool_name=call.get("name", ""),
                            args=args,
                            user_confirmation=user_confirmation,
                        ),
                        timeout=self.settings.agent_tool_timeout_seconds,
                    )
                except TimeoutError:
                    result, requires_confirm = {
                        "error": "tool_timeout",
                        "message": "The tool exceeded the configured execution timeout.",
                    }, False
                duration_ms = round((time.perf_counter() - started) * 1000, 1)
                return result, requires_confirm, duration_ms

            names = [call.get("name", "") for call in tool_calls]
            args_list = []
            for call in tool_calls:
                try:
                    args_list.append(json.loads(call.get("arguments", "{}")))
                except (TypeError, ValueError):
                    args_list.append({})
            needs_confirmation = any(confirmation_decision(name, args).required for name, args in zip(names, args_list, strict=True))
            if len(tool_calls) > 1 and not needs_confirmation:
                executed = await asyncio.gather(*(execute_call(call) for call in tool_calls))
            else:
                executed = [await execute_call(call) for call in tool_calls]

            for call, (tool_result, requires_confirm, duration_ms) in zip(tool_calls, executed, strict=True):
                tool_name = call.get("name", "unknown")
                if requires_confirm:
                    confirmation_required_data = tool_result
                event: dict[str, Any] = {
                    "tool": tool_name,
                    "status": "confirmation_required" if requires_confirm else "completed",
                    "duration_ms": duration_ms,
                }
                if isinstance(tool_result, dict) and tool_result.get("error"):
                    event["status"] = "failed"
                    event["error"] = tool_result["error"]
                events.append(event)

                tool_result_str = json.dumps(tool_result, separators=(",", ":"))
                if len(tool_result_str) > _MAX_TOOL_RESULT_CHARS:
                    tool_result_str = json.dumps(
                        {
                            "error": "tool_result_too_large",
                            "message": "Tool output was truncated safely.",
                        }
                    )
                await self.store.append_message(
                    session_id,
                    role="tool",
                    content=tool_result_str,
                    tool_id=call.get("id", ""),
                )
                messages_payload.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": tool_result_str,
                    }
                )
                if requires_confirm:
                    break
            if confirmation_required_data is not None:
                break

        if confirmation_required_data is not None:
            response = "Confirmation is required before I execute that action."
            status = "confirmation_required"
        elif final_response_text:
            response = final_response_text
            status = "completed"
        else:
            response = "I could not complete the request within the tool-call limit."
            status = "loop_limit"

        return {
            "session_id": session_id,
            "status": status,
            "response": response,
            "confirmation_required": confirmation_required_data,
            "action": (
                {
                    "type": confirmation_required_data.get("action", "unknown"),
                    "status": "awaiting_confirmation",
                    "preview": confirmation_required_data,
                }
                if confirmation_required_data is not None
                else None
            ),
            "tool_events": events,
            "iterations": loop_count,
        }

    async def _execute_tool(
        self, tool_name: str, args: dict[str, Any], user_confirmation: bool
    ) -> tuple[dict[str, Any], bool]:
        """Execute SMS, Email, or Documentation tool with guardrail check."""
        try:
            decision = confirmation_decision(tool_name, args)
            if decision.required and not user_confirmation and not args.get("confirmed"):
                return confirmation_payload(tool_name, args), True

            # ---- Documentation & SDK Tools ----------------------------------
            if tool_name == "get_agent_capabilities":
                return get_capabilities(), False
            elif tool_name == "search_documentation":
                res = search_docs(args["query"], target=args.get("target", "all"))
                return {"results": res}, False

            elif tool_name == "get_documentation_topic":
                res = get_doc_topic(args["topic_id"])
                return res, False

            # ---- SendAfrica Tools -------------------------------------------
            elif tool_name == "get_account_balance":
                res = await self.sendafrica.get_balance()
                return res, False

            elif tool_name == "get_usage_summary":
                res = await self.sendafrica.list_sms_logs(limit=100)
                counts: dict[str, int] = {}
                for log in res:
                    status = str(log.get("status") or "unknown")
                    counts[status] = counts.get(status, 0) + 1
                return {"period": args.get("period", "this_month"), "counts": counts, "logs_count": len(res)}, False

            elif tool_name == "list_contacts":
                list_id = args.get("list_id") or "1"
                res = await self.sendafrica.list_contacts(list_id, search=args.get("search"))
                return {"contacts": res}, False

            elif tool_name == "list_contact_lists":
                return {"contact_lists": await self.sendafrica.list_contact_lists()}, False

            elif tool_name == "import_contacts":
                content = str(args.get("csv_content") or "")
                if not content.strip() or len(content.encode("utf-8")) > 10 * 1024 * 1024:
                    return {"error": "csv_content_invalid", "message": "CSV content is empty or exceeds 10MB."}, False
                return await self.sendafrica.import_contacts(
                    list_id=args["list_id"], csv_content=content,
                    phone_column=args.get("phone_column"), name_column=args.get("name_column"),
                ), False

            elif tool_name == "get_delivery_status":
                message_id = str(args.get("message_id") or "").strip()
                if not message_id:
                    return {"error": "message_id_required"}, False
                return await self.sendafrica.get_delivery_status(message_id), False

            elif tool_name == "send_sms":
                res = await self.sendafrica.send_sms(
                    to=args["to"],
                    message=args["message"],
                    sender_id=args.get("sender_id") or None,
                    idempotency_key=args.get("idempotency_key") or None,
                )
                return res, False

            elif tool_name == "send_bulk_sms":
                recipients = args.get("recipients") or []
                res = await self.sendafrica.send_bulk_sms(
                    recipients=recipients,
                    message=args["message"],
                    sender_id=args.get("sender_id") or None,
                    idempotency_key=args.get("idempotency_key") or None,
                )
                return res, False

            elif tool_name == "create_campaign":
                res = await self.sendafrica.create_campaign(
                    name=args["name"],
                    contact_list_id=args["contact_list_id"],
                    message=args["message"],
                    sender_id=args.get("sender_id") or None,
                    scheduled_at=args.get("scheduled_at") or None,
                    idempotency_key=args.get("idempotency_key") or None,
                )
                return res, False

            # ---- Sender ID Tools -------------------------------------------------
            elif tool_name == "get_sender_id_requirements":
                return await self.sendafrica.get_sender_id_requirements(), False

            elif tool_name == "list_sender_ids":
                return {"sender_ids": await self.sendafrica.list_sender_ids()}, False

            elif tool_name == "get_sender_id":
                return await self.sendafrica.get_sender_id(args["sender_id"]), False

            elif tool_name == "list_usable_sender_ids":
                return {"usable_sender_ids": await self.sendafrica.list_usable_sender_ids(provider=args.get("provider"))}, False

            elif tool_name == "request_sender_id":
                res = await self.sendafrica.request_sender_id(
                    name=args["name"],
                    purpose=args["purpose"],
                    sample_message=args["sample_message"],
                    country=args.get("country") or "TZ",
                    documents=args.get("documents"),
                )
                return res, False

            # ---- MailAfrica Tools (Phase 2) ----------------------------------
            elif tool_name == "send_email":
                recipients = args.get("to") or []
                res = await self.mailafrica.send_email(
                    to=recipients,
                    subject=args["subject"],
                    text_body=args.get("body"),
                    from_address=args.get("from_address") or self.settings.agent_default_from_address,
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
