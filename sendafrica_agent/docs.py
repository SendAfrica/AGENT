from __future__ import annotations

from typing import Any

DOCS_INDEX: dict[str, dict[str, Any]] = {
    "auth": {
        "title": "API Authentication (SA- Keys & JWT)",
        "site": "docs.sendafrica.online",
        "description": "How to authenticate requests to the SendAfrica API.",
        "content": (
            "SendAfrica API uses API Keys or JWT Access Tokens for authentication.\n\n"
            "Headers:\n"
            "  X-API-Key: SA-your-api-key-here\n"
            "  Authorization: Bearer <your-jwt-token>\n\n"
            "API keys can be generated in the SendAfrica Dashboard under Developer / API Keys.\n"
            "All developer API keys are prefixed with 'SA-'."
        ),
        "code_examples": {
            "curl": "curl -X GET https://api.sendafrica.online/v1/credits/balance -H 'X-API-Key: SA-xxxx'",
            "python": "from sendafrica import SendAfrica\nclient = SendAfrica(api_key='SA-xxxx')",
            "nodejs": "import { SendAfrica } from 'sendafrica';\nconst client = new SendAfrica({ apiKey: 'SA-xxxx' });",
        },
    },
    "sms_send": {
        "title": "Send Single SMS (POST /v1/sms/send)",
        "site": "docs.sendafrica.online",
        "description": "Send an SMS message to a single phone number.",
        "content": (
            "Endpoint: POST /v1/sms/send\n"
            "Content-Type: application/json\n\n"
            "Request Body:\n"
            "{\n"
            '  "to": "+255712345678",\n'
            '  "message": "Your verification code is 4921.",\n'
            '  "sender_id": "SendAfrika"\n'
            "}\n\n"
            "Billing: 1 credit per 160 standard characters (1 SMS part)."
        ),
        "code_examples": {
            "python": "res = client.sms.send(to='+255712345678', message='Hello from SendAfrica!')",
            "nodejs": "const res = await client.sms.send({ to: '+255712345678', message: 'Hello!' });",
            "php": "$res = $client->sms->send(['to' => '+255712345678', 'message' => 'Hello!']);",
        },
    },
    "sms_bulk": {
        "title": "Send Bulk SMS (POST /v1/sms/bulk)",
        "site": "docs.sendafrica.online",
        "description": "Send SMS messages to multiple recipient phone numbers in a single call.",
        "content": (
            "Endpoint: POST /v1/sms/bulk\n"
            "Request Body:\n"
            "{\n"
            '  "recipients": ["+255712345678", "+255787654321"],\n'
            '  "message": "Holiday Special! 20% discount on all items."\n'
            "}"
        ),
        "code_examples": {
            "python": "res = client.sms.send_bulk(recipients=['+255712...', '+255787...'], message='Sale!')",
            "nodejs": "const res = await client.sms.sendBulk({ recipients: ['+255712...'], message: 'Sale!' });",
        },
    },
    "webhooks": {
        "title": "Inbound SMS Webhooks & Signature Verification",
        "site": "docs.sendafrica.online",
        "description": "Receive real-time notifications for inbound customer SMS.",
        "content": (
            "Configure your Webhook URL in Developer Settings.\n"
            "SendAfrica sends POST requests with payload:\n"
            "{\n"
            '  "event": "sms.inbound_received",\n'
            '  "from": "+255712345678",\n'
            '  "text": "Hello, I need assistance",\n'
            '  "message_id": "msg_98124"\n'
            "}\n\n"
            "Signature Header: X-Webhook-Signature (HMAC SHA-256 hex digest using your Webhook Secret)."
        ),
        "code_examples": {
            "python_fastapi": (
                "import hmac, hashlib\n"
                "expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()\n"
                "is_valid = hmac.compare_digest(request.headers['X-Webhook-Signature'], expected)"
            )
        },
    },
    "python_sdk": {
        "title": "Python SDK Guide (sdk.sendafrica.online)",
        "site": "sdk.sendafrica.online",
        "description": "Official SendAfrica Python Library.",
        "content": (
            "Installation:\n"
            "  pip install sendafrica\n"
            "  # or\n"
            "  uv add sendafrica\n\n"
            "Async Client Support:\n"
            "  from sendafrica import AsyncSendAfrica\n"
            "  async with AsyncSendAfrica(api_key='SA-xxxx') as client:\n"
            "      await client.sms.send(to='+255712345678', message='Hi!')"
        ),
        "code_examples": {
            "python": (
                "from sendafrica import SendAfrica\n"
                "client = SendAfrica(api_key='SA-xxxx')\n"
                "balance = client.credits.get_balance()\n"
                "print(f'Credits available: {balance.credits}')"
            )
        },
    },
    "nodejs_sdk": {
        "title": "TypeScript / Node.js SDK Guide (sdk.sendafrica.online)",
        "site": "sdk.sendafrica.online",
        "description": "Official SendAfrica Node.js & TypeScript Library.",
        "content": (
            "Installation:\n"
            "  npm install sendafrica\n"
            "  # or\n"
            "  pnpm add sendafrica\n\n"
            "TypeScript Usage:\n"
            "  import { SendAfrica } from 'sendafrica';\n"
            "  const sendafrica = new SendAfrica({ apiKey: process.env.SENDAFRICA_API_KEY });\n"
            "  const res = await sendafrica.sms.send({ to: '+255712345678', message: 'Hello!' });"
        ),
        "code_examples": {
            "typescript": (
                "import { SendAfrica } from 'sendafrica';\n"
                "const client = new SendAfrica({ apiKey: 'SA-xxxx' });\n"
                "const contacts = await client.contacts.list({ listId: '1' });"
            )
        },
    },
    "php_sdk": {
        "title": "PHP SDK Guide (sdk.sendafrica.online)",
        "site": "sdk.sendafrica.online",
        "description": "Official SendAfrica PHP Library.",
        "content": (
            "Installation:\n"
            "  composer require sendafrica/sendafrica-php\n\n"
            "PHP Usage:\n"
            "  $client = new SendAfrica\\Client(['api_key' => 'SA-xxxx']);\n"
            "  $res = $client->sms->send(['to' => '+255712345678', 'message' => 'Hello!']);"
        ),
        "code_examples": {
            "php": "$balance = $client->credits->getBalance();"
        },
    },
    "pricing_vouchers": {
        "title": "Pricing Tiers & Voucher Top-Ups",
        "site": "docs.sendafrica.online",
        "description": "SMS credit pricing structure and Snippe payment integration.",
        "content": (
            "Pay-As-You-Go Voucher Tiers:\n"
            "  • Tier 1 (1,000 TZS – 49,999 TZS): 35 TZS per credit\n"
            "  • Tier 2 (50,000 TZS – 149,999 TZS): 32 TZS per credit\n"
            "  • Tier 3 (150,000 TZS and above): 30 TZS per credit\n\n"
            "Mobile Money Integration:\n"
            "  Supports M-Pesa, Tigo Pesa, Airtel Money, Halopesa via Snippe USSD push.\n"
            "  Initiate via POST /v1/vouchers/initiate with phone_number."
        ),
        "code_examples": {
            "curl": "curl -X POST https://api.sendafrica.online/v1/vouchers/initiate -d '{\"phone_number\":\"0712345678\",\"amount_tzs\":10000}'"
        },
    },
}


def search_docs(query: str, target: str = "all") -> list[dict[str, Any]]:
    """Search documentation topics for docs.sendafrica.online and sdk.sendafrica.online."""
    q = query.lower().strip()
    results = []
    for topic_id, item in DOCS_INDEX.items():
        if target != "all" and item["site"] != target:
            continue
        text = f"{item['title']} {item['description']} {item['content']}".lower()
        if q in text or any(q in k.lower() for k in item.get("code_examples", {})):
            results.append({
                "topic_id": topic_id,
                "title": item["title"],
                "site": item["site"],
                "description": item["description"],
            })
    if not results:
        # Fallback list all topics if no direct match
        return [
            {
                "topic_id": k,
                "title": v["title"],
                "site": v["site"],
                "description": v["description"],
            }
            for k, v in DOCS_INDEX.items()
        ]
    return results


def get_doc_topic(topic_id: str) -> dict[str, Any]:
    """Retrieve full documentation topic with code examples."""
    topic = DOCS_INDEX.get(topic_id)
    if not topic:
        return {
            "error": f"Topic '{topic_id}' not found.",
            "available_topics": list(DOCS_INDEX.keys()),
        }
    return topic
