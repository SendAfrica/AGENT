from __future__ import annotations

from typing import Any

DOCS_INDEX: dict[str, dict[str, Any]] = {
    "auth": {
        "title": "API Authentication (API Keys and JWT)",
        "site": "docs.sendafrica.online",
        "description": "Choose API-key or JWT authentication based on the caller and protect credentials server-side.",
        "content": (
            "Account-scoped SendAfrica API routes accept X-API-Key: SA-... or an opaque "
            "Authorization: Bearer SA-... credential. JWT-shaped bearer tokens are used for "
            "dashboard/session callers. Credential lifecycle, password, OTP, OAuth linking, "
            "and administrative operations remain JWT-only. Never put API keys in browser code."
        ),
        "code_examples": {
            "curl": "curl -H 'X-API-Key: SA-xxxx' https://api.sendafrica.online/v1/credits/balance",
            "python": "from sendafrica import SendAfrica\nclient = SendAfrica(api_key='SA-xxxx')",
            "nodejs": "import { SendAfrica } from 'sendafrica';\nconst client = new SendAfrica({ apiKey: 'SA-xxxx' });",
        },
    },
    "sms_send": {
        "title": "Send Single SMS (POST /v1/sms/send)",
        "site": "docs.sendafrica.online",
        "description": "Send one SMS with the merged public payload and exact billing semantics.",
        "content": (
            "Request fields are to, message, and optional from. Prefer E.164 for international "
            "destinations. SendAfrica calculates parts after normalization: GSM-7 uses septets "
            "(160 single / 153 multipart); Unicode uses UTF-16 code units (70 single / 67 multipart). "
            "A successful response is provider submission, not handset delivery."
        ),
        "code_examples": {
            "curl": "curl -X POST https://api.sendafrica.online/v1/sms/send -H 'X-API-Key: SA-xxxx' -H 'Content-Type: application/json' -d '{\"to\":\"+255712345678\",\"message\":\"Hello!\",\"from\":\"SendAfrika\"}'",
            "python": "res = client.sms.send(to='+255712345678', message='Hello from SendAfrica!')",
            "nodejs": "const res = await client.sms.send({ to: '+255712345678', message: 'Hello!' });",
            "php": "$res = $client->sms->send(['to' => '+255712345678', 'message' => 'Hello!']);",
        },
    },
    "sms_bulk": {
        "title": "Send Bulk SMS (POST /v1/sms/bulk)",
        "site": "docs.sendafrica.online",
        "description": "Send one message to multiple recipients with per-recipient results and safe retries.",
        "content": (
            "The request uses a to array, not recipients. The synchronous batch limit is 100. "
            "Send an Idempotency-Key header for safe retries. Immediate provider refusals are "
            "refunded individually; accepted late failures are refunded exactly once."
        ),
        "code_examples": {
            "curl": "curl -X POST https://api.sendafrica.online/v1/sms/bulk -H 'X-API-Key: SA-xxxx' -H 'Idempotency-Key: batch-123' -H 'Content-Type: application/json' -d '{\"to\":[\"+255712345678\"],\"message\":\"Sale!\"}'",
            "python": "res = client.sms.send_bulk(to=['+255712345678'], message='Sale!', idempotency_key='batch-123')",
            "nodejs": "const res = await client.sms.sendBulk({ to: ['+255712345678'], message: 'Sale!' });",
        },
    },
    "sms_delivery": {
        "title": "SMS Delivery and Message Logs",
        "site": "docs.sendafrica.online",
        "description": "Reconcile provider submission and final delivery from account-owned logs.",
        "content": (
            "The public send response uses an SA-<uuid> message_id. Provider submission Success "
            "is not handset delivery. Read GET /v1/sms/logs with per_page, page, status, search, "
            "and date_from filters. A delivered message is terminal."
        ),
        "code_examples": {
            "curl": "curl -G https://api.sendafrica.online/v1/sms/logs -H 'X-API-Key: SA-xxxx' --data-urlencode 'status=failed'",
            "python": "logs = client.sms.logs(status='failed', date_from='2026-08-01')",
        },
    },
    "chat_contract": {
        "title": "Structured Dashboard Chat Contract",
        "site": "docs.sendafrica.online",
        "description": "Use structured status, confirmation, and tool-event fields for a responsive UI.",
        "content": (
            "POST /v1/agent/chat accepts session_id, message, and user_confirmation. The response "
            "includes status, response, confirmation_required, tool_events, iterations, and request_id. "
            "Confirmation is required for campaigns, bulk SMS over 10 recipients, email over 5 recipients, "
            "and sender ID registration requests."
        ),
        "code_examples": {
            "curl": "curl -X POST https://agent.example.com/v1/agent/chat -H 'X-API-Key: SA-xxxx' -H 'X-Account-ID: account-uuid' -H 'Content-Type: application/json' -d '{\"session_id\":\"chat-1\",\"message\":\"Show my balance\"}'",
        },
    },
    "sender_id_request": {
        "title": "Register a Sender ID (POST /v1/sender-ids)",
        "site": "docs.sendafrica.online",
        "description": "Submit a free sender ID registration request with name, purpose, sample message, and optional documents.",
        "content": (
            "Sender ID registration is free. The name must be 3-11 characters matching ^[A-Za-z0-9]+( [A-Za-z0-9]+)*$. "
            "Reserved names like ADMIN, ALERT, BANK, GOV, OTP, SAFARICOM, VODACOM, and WHATSAPP are blocked. "
            "Provide a sample message (50-500 chars) and a purpose from the allowed list. "
            "Optional documents are arrays of requirement_uid, filename, and content_base64. "
            "The account must have at least 100 purchased sender ID units (TZS 1,300 minimum). "
            "Status transitions from pending to approved/rejected/suspended. Approved IDs become usable for sends."
        ),
        "code_examples": {
            "curl": "curl -X POST https://api.sendafrica.online/v1/sender-ids -H 'X-API-Key: SA-xxxx' -H 'Content-Type: application/json' -d '{\"name\":\"MyBrand\",\"purpose\":\"Notification\",\"sample_message\":\"Your order is ready\",\"country\":\"TZ\"}'",
            "python": "res = client.sender_ids.request(name='MyBrand', purpose='Notification', sample_message='Your order is ready')",
        },
    },
    "sender_id_usable": {
        "title": "List Usable Sender IDs (GET /v1/sender-ids/usable)",
        "site": "docs.sendafrica.online",
        "description": "Get platform defaults and account-approved custom sender IDs available for sends.",
        "content": (
            "Returns platform defaults (SendAfrika for Africa's Talking, SENDAFRICA for SwalaSMS) "
            "plus any account-approved custom sender IDs. Filter by provider query param (swala or africastalking). "
            "Only usable IDs (approved and not suspended) appear here. Use these values for the from field in SMS sends."
        ),
        "code_examples": {
            "curl": "curl https://api.sendafrica.online/v1/sender-ids/usable -H 'X-API-Key: SA-xxxx'",
            "python": "usable = client.sender_ids.usable()",
        },
    },
    "email_from": {
        "title": "SendAfrica Agent Default From Address",
        "site": "docs.sendafrica.online",
        "description": "The agent uses agent@mailafrica.online as the default from address for MailAfrica emails.",
        "content": (
            "When sending emails via the SendAfrica Agent (MCP or dashboard chat), if no from_address is provided, "
            "the agent automatically uses agent@mailafrica.online. You can override this by passing a custom from_address."
        ),
        "code_examples": {
            "python": "await agent.send_email(to=['user@example.com'], subject='Hello', body='Test')",
        },
    },

    "webhooks": {
        "title": "Inbound SMS Webhooks and Provider Callbacks",
        "site": "docs.sendafrica.online",
        "description": "Distinguish Agent inbound callbacks from SendAfrica delivery processing.",
        "content": (
            "The Agent /webhooks/sendafrica endpoint accepts verified inbound SMS events and queues "
            "automatic replies. Delivery callbacks from Africa's Talking are processed by the SendAfrica "
            "API with the configured provider callback token; applications should reconcile through logs."
        ),
        "code_examples": {
            "python_fastapi": (
                "expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()\n"
                "valid = hmac.compare_digest(signature, expected)"
            )
        },
    },
    "python_sdk": {
        "title": "Python SDK Guide (sdk.sendafrica.online)",
        "site": "sdk.sendafrica.online",
        "description": "Official SendAfrica Python integration patterns.",
        "content": (
            "Use a server-side API key. Prefer async clients for interactive services and pass a stable "
            "Idempotency-Key for logical retries of sends."
        ),
        "code_examples": {
            "python": (
                "from sendafrica import AsyncSendAfrica\n"
                "async with AsyncSendAfrica(api_key='SA-xxxx') as client:\n"
                "    await client.sms.send(to='+255712345678', message='Hi!')"
            )
        },
    },
    "nodejs_sdk": {
        "title": "TypeScript / Node.js SDK Guide",
        "site": "sdk.sendafrica.online",
        "description": "Official SendAfrica Node.js and TypeScript integration patterns.",
        "content": "Keep API keys server-side and use E.164 destinations for international SMS.",
        "code_examples": {
            "typescript": (
                "import { SendAfrica } from 'sendafrica';\n"
                "const client = new SendAfrica({ apiKey: process.env.SENDAFRICA_API_KEY });\n"
                "const result = await client.sms.send({ to: '+255712345678', message: 'Hello!' });"
            )
        },
    },
    "php_sdk": {
        "title": "PHP SDK Guide",
        "site": "sdk.sendafrica.online",
        "description": "Official SendAfrica PHP integration patterns.",
        "content": "Use composer packages from the SDK portal and never expose the API key to a browser.",
        "code_examples": {
            "php": "$client = new SendAfrica\\Client(['api_key' => 'SA-xxxx']);\n$res = $client->sms->send(['to' => '+255712345678', 'message' => 'Hello!']);"
        },
    },
    "pricing_rates": {
        "title": "Customer Rates, Provider Reference, and Credits",
        "site": "docs.sendafrica.online",
        "description": "Understand the SendAfrica customer rate card and additive provider metadata.",
        "content": (
            "rate_tzs is the SendAfrica customer billing source. provider_bulk_sms is an informational "
            "Africa's Talking reference snapshot, not a live quote and not an automatic customer price. "
            "International credits are calculated per destination rate and SMS part."
        ),
        "code_examples": {
            "curl": "curl https://api.sendafrica.online/v1/rates"
        },
    },
}


def search_docs(query: str, target: str = "all") -> list[dict[str, Any]]:
    """Search the local documentation index without a network round trip."""
    q = query.lower().strip()
    results: list[dict[str, Any]] = []
    for topic_id, item in DOCS_INDEX.items():
        if target != "all" and item["site"] != target:
            continue
        text = f"{item['title']} {item['description']} {item['content']}".lower()
        if not q or q in text or any(q in key.lower() for key in item.get("code_examples", {})):
            results.append(
                {
                    "topic_id": topic_id,
                    "title": item["title"],
                    "site": item["site"],
                    "description": item["description"],
                }
            )
    return results


def get_doc_topic(topic_id: str) -> dict[str, Any]:
    """Retrieve one documentation topic with its code examples."""
    topic = DOCS_INDEX.get(topic_id)
    if not topic:
        return {"error": f"Topic '{topic_id}' not found.", "available_topics": list(DOCS_INDEX)}
    return topic
