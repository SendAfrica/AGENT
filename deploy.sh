#!/usr/bin/env bash
set -euo pipefail

echo "==> Deploying SendAfrica-Agent..."

if ! command -v uv &> /dev/null; then
    echo "uv not found, installing virtual environment via venv..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install .
else
    echo "Syncing dependencies with uv..."
    uv sync
fi

echo "==> Environment check completed."
echo "==> Ready to run via 'uv run sendafrica-agent serve' or systemd service."
