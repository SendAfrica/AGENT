# SendAfrica Agent

Model Context Protocol (MCP) server & automated SMS auto-reply agent for the [SendAfrica API](https://api.sendafrica.online).

Provides:
- **MCP Server** (`sendafrica-agent mcp`): Exposes FastMCP tools to AI assistants for SMS sending, contact management, campaign scheduling, credit accounting, and top-ups.
- **Webhook Auto-Reply Server** (`sendafrica-agent serve`): FastAPI endpoint (`POST /webhooks/sendafrica`) that receives inbound SMS, maintains turn-by-turn thread context in SQLite, and generates AI responses using the Ngamia LLM gateway.

---

## Quick Start

### 1. Configuration
Copy `.env.example` to `.env` and fill in credentials:

```bash
cp .env.example .env
```

Key environment variables:
- `SENDAFRICA_API_BASE`: `https://api.sendafrica.online/v1`
- `SENDAFRICA_API_KEY`: Your SendAfrica API key (`SA-...`)
- `NGAMIA_BASE_URL`: `https://api.ngamia.cc/v1`
- `NGAMIA_API_KEY`: Ngamia API key (`ngm_...`)
- `NGAMIA_MODEL`: `openai/gpt-4o-mini`

---

## Usage

### Run as MCP Server (Stdio)
For integration with AI assistants (Claude Desktop, Cursor, Gemini, etc.):

```bash
uv run sendafrica-agent mcp
# or
python -m sendafrica_agent mcp
```

### Run HTTP Webhook Server (FastAPI / Uvicorn)
To listen for inbound SMS webhooks:

```bash
uv run sendafrica-agent serve
# or
python -m sendafrica_agent serve
```

---

## MCP Tools Offered

| Category | Tool | Description |
|---|---|---|
| **SMS** | `send_sms` | Send single SMS |
| **SMS** | `send_bulk_sms` | Send bulk SMS |
| **SMS** | `get_sms_logs` | Fetch SMS status logs |
| **Credits** | `get_credit_balance` | Check current credit balance |
| **Credits** | `get_credit_history` | Ledger transaction history |
| **Credits** | `get_voucher_rate` | Pay-as-you-go voucher pricing tiers |
| **Contacts** | `list_contact_lists` | List contact lists |
| **Contacts** | `create_contact_list` | Create contact list |
| **Contacts** | `list_contacts` | List contacts in list |
| **Contacts** | `create_contact` | Add contact to list |
| **Campaigns**| `list_campaigns` | List SMS campaigns |
| **Campaigns**| `create_campaign` | Schedule bulk SMS campaign |
| **Campaigns**| `get_campaign` | Get campaign details & recipient stats |
| **Payments** | `initiate_payment` | Mobile money top-up (Snippe/manual) |
| **Agent** | `agent_config` | Configure SMS auto-reply mode/persona per phone |
| **Agent** | `agent_handle_sms` | Test inbound SMS auto-reply pipeline |
| **Agent** | `list_models` | List LLM models from Ngamia gateway |

---

## License

MIT License.
