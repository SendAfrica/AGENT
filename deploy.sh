#!/usr/bin/env bash
# Deploy script for SendAfrica Agent — invoked locally or on VPS
set -euo pipefail

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

echo "==> Deploying SendAfrica Agent in $PROJECT_DIR..."

if [ -f ".git" ] || [ -d ".git" ]; then
    echo "==> Pulling latest changes from git repository..."
    git pull --ff-only origin main || true
fi

if command -v docker >/dev/null 2>&1 && [ -f "docker-compose.yml" ]; then
    echo "==> Deploying container via Docker Compose..."
    docker compose up -d --build
elif systemctl is-active --quiet sendafrica-agent-webhook 2>/dev/null; then
    echo "==> Installing dependencies (uv)..."
    if command -v uv >/dev/null 2>&1; then
        uv sync --frozen
    fi
    echo "==> Restarting systemd service..."
    systemctl restart sendafrica-agent-webhook
else
    echo "==> Falling back to uv run..."
    if command -v uv >/dev/null 2>&1; then
        uv sync
        nohup uv run sendafrica-agent serve > agent.log 2>&1 &
    fi
fi

echo "==> SendAfrica Agent deployment complete!"
