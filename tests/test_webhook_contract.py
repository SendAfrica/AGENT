from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from sendafrica_agent.config import Settings
from sendafrica_agent.webhook import create_app


class WebhookContractTests(unittest.TestCase):
    def make_client(self) -> TestClient:
        settings = Settings(
            sendafrica_api_key="SA-test",
            mailafrica_api_key="MA-test",
            ngamia_api_key="ngm-test",
            agent_allowed_hosts="testserver",
            agent_allowed_origins="http://testserver",
            agent_mcp_auth_token="mcp-test",
        )
        return TestClient(create_app(settings))

    def test_health_and_ready(self):
        with self.make_client() as client:
            self.assertEqual(client.get("/health").status_code, 200)
            ready = client.get("/ready")
            self.assertEqual(ready.status_code, 200)
            self.assertEqual(ready.json()["status"], "ready")

    def test_chat_requires_caller_auth_and_account(self):
        with self.make_client() as client:
            body = {"session_id": "s", "message": "hello"}
            self.assertEqual(client.post("/v1/agent/chat", json=body).status_code, 401)
            response = client.post(
                "/v1/agent/chat",
                headers={"X-API-Key": "SA-test"},
                json=body,
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["status"], "validation_error")

    def test_remote_mcp_requires_dedicated_token(self):
        with self.make_client() as client:
            self.assertEqual(client.get("/sse").status_code, 401)
            response = client.get("/sse", headers={"X-MCP-Token": "mcp-test"})
            self.assertNotEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
