# Multi-stage Dockerfile for SendAfrica Agent using uv
FROM python:3.11-slim as builder

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy dependency definition files
COPY pyproject.toml uv.lock ./

# Sync dependencies into virtualenv
RUN uv sync --frozen --no-install-project --no-dev

# Copy application source code
COPY sendafrica_agent/ ./sendafrica_agent/
COPY README.md ./

# Sync project package
RUN uv sync --frozen --no-dev

# Runtime stage
FROM python:3.11-slim as runner

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy virtualenv and application from builder stage
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/sendafrica_agent /app/sendafrica_agent
COPY --from=builder /app/pyproject.toml /app/

# Create data directory for SQLite database storage
RUN mkdir -p /app/data

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV AGENT_HOST=0.0.0.0
ENV AGENT_PORT=8099
ENV AGENT_DB_PATH=/app/data/agent.db

EXPOSE 8099

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8099/health || exit 1

CMD ["sendafrica-agent", "serve"]
