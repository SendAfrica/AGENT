# SendAfrica Agent

The SendAfrica Agent is a multi-channel action-taking assistant and FastMCP server for SendAfrica SMS, MailAfrica email, and developer documentation. It powers dashboard chat through the Go API and can also run as a local stdio MCP server or protected remote SSE service.

## Highlights

| Capability | Behavior |
|---|---|
| Dashboard chat | Structured responses with status, session ID, confirmation state, tool events, iterations, and request ID. |
| Fast tool execution | Independent read-only tools run concurrently; write tools run in parallel when safe. Each tool has a timeout and bounded output. |
| Safe side effects | Bulk SMS, campaigns, mass email, and sender ID requests use explicit confirmation thresholds across chat and MCP. |
| Credential isolation | Caller credentials are scoped to the current async task; shared HTTP headers are never mutated. |
| MCP | Local stdio and authenticated remote SSE transports. |
| SMS correctness | Uses the merged SendAfrica API contract, including `from`, public `SA-<uuid>` IDs, international destinations, exact parts, and destination-specific credit math. |
| Reliable automation | Inbound replies use provider message IDs as idempotency keys when available. |
| Circuit breaker | Agent upstream failures trigger a cooldown to avoid cascading latency. |

## Architecture

```text
Dashboard → SendAfrica Go API /v1/support/chat
                     │ caller auth + session + confirmation
                     ▼
           SendAfrica Agent /v1/agent/chat
              ├─ SQLite session/history store (per-session locks)
              ├─ bounded ChatRunner tool loop
              ├─ SendAfrica / MailAfrica clients
              └─ Ngamia OpenAI-compatible gateway

MCP clients → stdio or protected /sse → same tool surface
Provider inbound callback → /webhooks/sendafrica → async Agent reply
```

The Go support route remains the public dashboard boundary. It forwards the authenticated caller credential and returns the Agent's structured result while retaining the legacy `reply` field.

## Tool surface

| Tool | Purpose | Confirmation |
|---|---|---|
| `get_agent_capabilities` | Feature and version discovery. | None. |
| `send_sms` | Send one SMS; supports sender ID and idempotency key. | None by threshold. |
| `send_bulk_sms` | Send one SMS to multiple recipients. | More than 10 recipients. |
| `get_delivery_status` | Look up one public SendAfrica message ID. | None. |
| `list_contacts` | List or search a contact list. | None. |
| `create_campaign` | Create and schedule a campaign. | Always. |
| `get_account_balance` | Read SendAfrica balance. | None. |
| `get_usage_summary` | Count recent log states. | None. |
| `send_email` | Send MailAfrica transactional email. | More than 5 recipients. |
| `list_inbound_emails` | Read MailAfrica inbound messages. | None. |
| `get_email_balance` | Read MailAfrica balance. | None. |
| `search_documentation` | Search the local docs index. | None. |
| `get_documentation_topic` | Retrieve a complete docs topic. | None. |
| `list_models` | Cached Ngamia model discovery. | None. |
| `get_sender_id_requirements` | Get sender ID registration rules and eligibility. | None. |
| `list_sender_ids` | List sender IDs registered for the account. | None. |
| `get_sender_id` | Inspect a specific sender ID by ID or name. | None. |
| `list_usable_sender_ids` | List platform defaults and approved custom sender IDs. | None. |
| `request_sender_id` | Submit a new sender ID registration request. | Always. |

When confirmation is required, the tool returns a preview payload and performs no side effect. Clients should render the preview and call again with `confirmed: true` only after explicit user approval.

## SMS semantics

The Agent delegates parts, normalization, pricing, and refunds to the SendAfrica API. GSM-7 uses septets: 160 for a single part and 153 per multipart segment. Unicode uses UTF-16 code units: 70 for a single part and 67 per multipart segment. A provider submission `Success` is not handset delivery; read message logs for final state. International credits are destination-rate-card specific, not universally one credit per part.

## Security considerations

This project is open source. Do not commit secrets or production credentials.

- `.env` is gitignored. Copy `.env.example` to `.env` and fill in your own values.
- The agent does **not** expose admin endpoints. Admin operations (sender ID approval/rejection, profit reports, account management) remain JWT-only and live in the SendAfrica API backend.
- Remote SSE requires `AGENT_MCP_AUTH_TOKEN`. Keep it long and random.
- Keep `AGENT_REQUIRE_CALLER_AUTH=true` in production.
- Restrict `AGENT_ALLOWED_ORIGINS` and `AGENT_ALLOWED_HOSTS` to your actual dashboards and domains.
- The webhook endpoint verifies HMAC-SHA256 signatures using `AGENT_WEBHOOK_SECRET`.

## Install and configure

```bash
git clone https://github.com/SendAfrica/SendAfrica-Agent.git
cd SendAfrica-Agent
uv sync --frozen
cp .env.example .env
```

Edit `.env` and set `SENDAFRICA_API_KEY`, `MAILAFRICA_API_KEY`, `NGAMIA_API_KEY`, `AGENT_WEBHOOK_SECRET`, and runtime options.

### Required environment variables

| Variable | Purpose |
|---|---|
| `SENDAFRICA_API_KEY` | SendAfrica API key (`SA-...`). |
| `MAILAFRICA_API_KEY` | MailAfrica API key (`MA-...`). |
| `NGAMIA_API_KEY` | Ngamia LLM gateway key. |
| `AGENT_WEBHOOK_SECRET` | HMAC secret for inbound SMS webhooks. |

### Security environment variables

| Variable | Purpose |
|---|---|
| `AGENT_REQUIRE_CALLER_AUTH` | Must be `true` in production. |
| `AGENT_MCP_AUTH_TOKEN` | Long random token for remote SSE. |
| `AGENT_ALLOWED_ORIGINS` | Comma-separated allowed CORS origins. |
| `AGENT_ALLOWED_HOSTS` | Comma-separated allowed hostnames. |

## Run

```bash
# Dashboard chat, inbound callbacks, health, and protected remote SSE
uv run sendafrica-agent serve

# Local MCP over stdio
uv run sendafrica-agent mcp
```

Important HTTP endpoints are `GET /health`, `GET /ready`, `GET /v1/agent/capabilities`, `POST /v1/agent/chat`, `POST /webhooks/sendafrica`, and protected `/sse`. See the [Agent Docs](https://github.com/troubleman96/SendAfrica-Agent-Docs) for the complete contracts and deployment guide.

## Docker

```bash
docker compose up -d --build
```

The container exposes port `8099` and expects `.env` variables or Compose `environment:` entries.

## Validation

```bash
uv run ruff check sendafrica_agent tests
uv run pytest tests -v
uv run python -m compileall -q sendafrica_agent
```

## License

MIT License.
