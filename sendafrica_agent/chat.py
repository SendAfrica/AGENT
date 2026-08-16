from __future__ import annotations

import json
import logging
from typing import Any

from .config import Settings
from .ngamia import NgamiaClient
from .sendafrica import SendAfricaClient
from .store import Store

logger = logging.getLogger("sendafrica_agent.chat")

SENDAFRICA_AGENT_SYSTEM_PROMPT = """You are the SendAfrica Assistant — an intelligent in-app assistant embedded in the SendAfrica business dashboard.
Your goal is to help business owners manage SMS campaigns, check credit balances, look up delivery status, and search contacts.

IMPORTANT RULES & GUARDRAILS:
1. You can ONLY perform actions on behalf of the authenticated account.
2. Keep responses helpful, professional, and clear.
3. BULK CAMPAIGNS & MASS SMS GUARDRAIL:
   - Before executing bulk SMS sends or scheduling mass campaigns, you MUST describe the planned action clearly (recipient count, message, cost) and ask the user to confirm.
   - If the action requires user confirmation and hasn't been confirmed yet, inform the user clearly and wait for their explicit confirmation.
"""

# Available tool schemas formatted for OpenAI tool calling spec
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_account_balance",
            "description": "Check current SMS credit and wallet balance for the account.",
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
            "description": "Fetch delivery status for a specific message ID.",
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
]


class ChatRunner:
    """Orchestrates multi-turn chat sessions with tool calling and safety guardrails."""

    def __init__(self, settings: Settings, sendafrica: SendAfricaClient, ngamia: NgamiaClient, store: Store):
        self.settings = settings
        self.sendafrica = sendafrica
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

        # Build message context for LLM
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

            # Record assistant turn with tool calls
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

            # Execute requested tools
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
        """Execute tool or return safety confirmation guardrail block."""
        try:
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
                    # Safety Guardrail Triggered!
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

            else:
                return {"error": f"Unknown tool: {tool_name}"}, False

        except Exception as exc:
            logger.exception("tool execution error for %s", tool_name)
            return {"error": str(exc)}, False
