from __future__ import annotations

import argparse
import logging
import sys

import uvicorn

from .config import get_settings
from .mcp_server import Runtime, build_server
from .webhook import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="SendAfrica Agent MCP Server & Webhook Service")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # mcp subcommand
    subparsers.add_parser("mcp", help="Run as stdio MCP server for agent tool use")

    # serve subcommand
    subparsers.add_parser("serve", help="Run HTTP webhook app via uvicorn")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    settings = get_settings()

    if args.command == "mcp":
        runtime = Runtime(settings)
        server = build_server(runtime)
        server.run(transport="stdio")
    elif args.command == "serve":
        app = create_app(settings)
        uvicorn.run(app, host=settings.agent_host, port=settings.agent_port)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
