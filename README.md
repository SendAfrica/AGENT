# SendAfrica & MailAfrica Agent (`SendAfrica-Agent`)

An in-app **Multi-Channel AI Assistant** and **FastMCP Server** for [SendAfrica](https://app.sendafrica.online) (SMS) and [MailAfrica](https://app.mailafrica.online) (Transactional Email).

---

## Features

- **In-App Dashboard Assistant (`POST /v1/agent/chat`)**:
  - Embedded directly inside the SendAfrica web dashboard chat widget.
  - Serves as a **knowledgeable support chatbot** (answers questions about pricing, API keys, Snippe top-ups, contacts, and delivery rules).
  - Serves as an **action-taking agent** executing FastMCP tools on behalf of authenticated business users.
- **FastMCP Tool Server (`sendafrica-agent mcp`)**:
  - Exposes FastMCP tools for AI assistants (Claude, Cursor, Gemini, custom agents).
- **Safety Guardrails (Confirm-Before-Send)**:
  - Requires explicit user confirmation before executing bulk SMS campaigns or mass email dispatches to prevent unintended blasts.
- **Multi-Channel Synergy**:
  - Manages both **SMS** (SendAfrica) and **Email** (MailAfrica) through a unified tool-calling interface powered by the **Ngamia AI Gateway** (`api.ngamia.cc/v1`).

---

## System Architecture

```
┌────────────────────────────────────────────────────────┐
│               SendAfrica Web Dashboard                 │
│         (In-app Chat Widget at /admin or /app)          │
└──────────────────────────┬─────────────────────────────┘
                           │ POST /v1/support/chat
                           ▼
┌────────────────────────────────────────────────────────┐
│               SendAfrica Go Core API                   │
│             (https://api.sendafrica.online)            │
└──────────────────────────┬─────────────────────────────┘
                           │ Proxy to AGENT_SERVICE_URL
                           ▼
┌────────────────────────────────────────────────────────┐
│             SendAfrica Agent Service                   │
│  - Session History (agent_sessions / agent_messages)   │
│  - Knowledge Base System Prompt Resource               │
│  - Tool-Calling Loop with Ngamia LLM Gateway           │
│  - Safety Guardrail (Confirm-Before-Send)              │
└──────────────┬──────────────────────────┬──────────────┘
               │                          │
               │ FastMCP Tool Execution   │ Ngamia Chat Completions
               ▼                          ▼
┌─────────────────────────────┐  ┌─────────────────────────┐
│     FastMCP Server Tools    │  │   Ngamia AI Gateway     │
│   (SendAfrica & MailAfrica) │  │  (api.ngamia.cc/v1)     │
└──────────────┬──────────────┘  └─────────────────────────┘
               │
      ┌────────┴────────┐
      ▼                 ▼
┌──────────┐      ┌──────────┐
│SendAfrica│      │MailAfrica│
│ Go Core  │      │   API    │
└──────────┘      └──────────┘
```

---

## FastMCP Tools Offered

### SMS Tools (SendAfrica)
| Tool Name | Parameters | Description |
|---|---|---|
| `get_account_balance` | None | Check SendAfrica SMS credit balance |
| `get_usage_summary` | `period="this_month"` | Summarize sent/delivered/failed SMS |
| `list_contacts` | `list_id="1", query=""` | Search/list contacts in phonebook |
| `get_delivery_status` | `message_id=""` | Query delivery status logs |
| `send_sms` | `to, message` | Send a single SMS message |
| `create_campaign` | `name, message, contact_group_id` | Schedule bulk SMS campaign (Guardrail checked) |

### Documentation & SDK Tools (`docs.sendafrica.online` & `sdk.sendafrica.online`)
| Tool Name | Parameters | Description |
|---|---|---|
| `search_documentation` | `query, target="all"` | Search REST API docs and SDK code samples |
| `get_documentation_topic` | `topic_id` | Fetch full documentation guide & SDK code snippets |

### Email Tools (MailAfrica)
| Tool Name | Parameters | Description |
|---|---|---|
| `send_email` | `to: list[str], subject, body, from_address` | Send transactional email (Guardrail checked) |
| `list_inbound_emails` | `address_id=1, limit=20` | List received inbound emails |
| `get_email_balance` | None | Check MailAfrica wallet & credit balance |

---

## Embedded Knowledge Base Resource

The agent is pre-loaded with comprehensive knowledge regarding:
1. **SendAfrica Core**: Platform app (`app.sendafrica.online`), REST API (`api.sendafrica.online/v1`), and API key format (`SA-...`).
2. **MailAfrica Core**: Platform app (`app.mailafrica.online`), REST API (`api.mailafrica.online`), and API key format (`MA-...`).
3. **Pay-As-You-Go Voucher Rates (TZS)**:
   - Tier 1 (1,000 to 49,999 TZS): **35 TZS / credit**
   - Tier 2 (50,000 to 149,999 TZS): **32 TZS / credit**
   - Tier 3 (150,000 TZS and above): **30 TZS / credit**
4. **Mobile Money Top-Ups**: Snippe integration for M-Pesa, Tigo Pesa, Airtel Money, Halopesa, and manual bank transfers.
5. **Phonebook & Sync**: Contact list grouping, CSV imports, and Google Contacts one-way sync.

---

## Setup & Running

### 1. Configure Environment (`.env`)
```bash
cp .env.example .env
```

Set key credentials:
```ini
SENDAFRICA_API_BASE=https://api.sendafrica.online/v1
SENDAFRICA_API_KEY=SA-your-key-here

MAILAFRICA_API_BASE=https://api.mailafrica.online
MAILAFRICA_API_KEY=MA-your-key-here

NGAMIA_BASE_URL=https://api.ngamia.cc/v1
NGAMIA_API_KEY=ngm_your_key_here
NGAMIA_MODEL=openai/gpt-4o-mini
```

### 2. Run Assistant Webhook Server
```bash
uv run sendafrica-agent serve
# Starts FastAPI server on http://0.0.0.0:8000
```

### 3. Run as Stdio MCP Server
```bash
uv run sendafrica-agent mcp
```

---

## License

MIT License.
