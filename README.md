# SendAfrica Agent

The SendAfrica Agent is a multi-channel action-taking assistant and FastMCP server for SendAfrica SMS, MailAfrica email, and developer documentation. It powers dashboard chat through the Go API and can also run as a local stdio MCP server or protected remote SSE service.

## Highlights

| Capability | Behavior |
|---|---|
| Dashboard chat | Structured responses with status, session ID, confirmation state, tool events, iterations, and request ID. |
| Fast tool execution | Independent read-only tools run concurrently; each tool has a timeout and bounded output. |
| Safe side effects | Bulk SMS, campaigns, and mass email use explicit confirmation thresholds across chat and MCP. |
| Credential isolation | Caller credentials are scoped to the current async task; shared HTTP headers are never mutated. |
| MCP | Local stdio and authenticated remote SSE transports. |
| SMS correctness | Uses the merged SendAfrica API contract, including `from`, public `SA-<uuid>` IDs, international destinations, exact parts, and destination-specific credit math. |
| Reliable automation | Inbound replies use provider message IDs as idempotency keys when available. |

## Architecture

```text
Dashboard → SendAfrica Go API /v1/support/chat
                    │ caller auth + session + confirmation
                    ▼
          SendAfrica Agent /v1/agent/chat
             ├─ SQLite session/history store
             ├─ bounded ChatRunner tool loop
             ├─ SendAfrica / MailAfrica clients
             └─ Ngamia OpenAI-compatible gateway

MCP clients → stdio or protected /sse → same tool surface
Provider inbound callback → /webhooks/sendafrica → async Agent reply
```

The Go support route remains the public dashboard boundary. It forwards the authenticated caller credential and returns the Agent’s structured result while retaining the legacy `reply` field.

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

When confirmation is required, the tool returns a preview payload and performs no side effect. Clients should render the preview and call again with `confirmed: true` only after explicit user approval.

## SMS semantics

The Agent delegates parts, normalization, pricing, and refunds to the SendAfrica API. GSM-7 uses septets: 160 for a single part and 153 per multipart segment. Unicode uses UTF-16 code units: 70 for a single part and 67 per multipart segment. A provider submission `Success` is not handset delivery; read message logs for final state. International credits are destination-rate-card specific, not universally one credit per part.

## Install and configure

```bash
git clone https://github.com/SendAfrica/SendAfrica-Agent.git
cd SendAfrica-Agent
uv sync --frozen
cp .env.example .env
```

Set `SENDAFRICA_API_KEY`, `MAILAFRICA_API_KEY`, `NGAMIA_API_KEY`, and the required runtime options. For a secure HTTP deployment, use explicit `AGENT_ALLOWED_ORIGINS` and `AGENT_ALLOWED_HOSTS`, keep `AGENT_REQUIRE_CALLER_AUTH=true`, and configure a long random `AGENT_MCP_AUTH_TOKEN` if remote SSE is enabled.

## Run

```bash
# Dashboard chat, inbound callbacks, health, and protected remote SSE
uv run sendafrica-agent serve

# Local MCP over stdio
uv run sendafrica-agent mcp
```

Important HTTP endpoints are `GET /health`, `GET /ready`, `GET /v1/agent/capabilities`, `POST /v1/agent/chat`, `POST /webhooks/sendafrica`, and protected `/sse`. See the [Agent Docs](https://github.com/troubleman96/SendAfrica-Agent-Docs) for the complete contracts and deployment guide.

## Validation

All checks are offline and do not send live SMS, initiate payments, or call production callbacks:

```bash
uv run ruff check sendafrica_agent tests
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q sendafrica_agent
```

## License

MIT License.
