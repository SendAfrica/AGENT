from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from typing import Any

import httpx

from sendafrica_agent.auth_context import RequestCredentials, use_request_credentials
from sendafrica_agent.chat import ChatRunner
from sendafrica_agent.config import Settings
from sendafrica_agent.sendafrica import SendAfricaClient
from sendafrica_agent.store import Store, StoreError


class FakeNgamia:
    def __init__(self, responses: list[dict[str, Any]]):
        self.responses = iter(responses)
        self.calls: list[list[dict[str, Any]]] = []

    async def chat_with_tools(self, messages, tools=None):
        self.calls.append(messages)
        return next(self.responses)


class FakeSendAfrica:
    async def get_balance(self):
        return {"balance": 42}

    async def list_sms_logs(self, **kwargs):
        await asyncio.sleep(0)
        return [{"status": "delivered"}, {"status": "failed"}]

    async def get_delivery_status(self, message_id):
        return {"id": message_id, "status": "delivered"}

    async def close(self):
        return None


class FakeMailAfrica:
    async def balance(self):
        return {"balance": 9}

    async def list_messages(self, **kwargs):
        return []


class StoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_returns_newest_bounded_window_in_model_order(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "agent.db"))
            await store.connect()
            await store.get_or_create_session("session", "account", "user")
            for index in range(5):
                await store.append_message("session", "user", f"message-{index}")
            messages = await store.get_session_messages("session", limit=2)
            self.assertEqual([message.content for message in messages], ["message-3", "message-4"])
            await store.close()

    async def test_session_cannot_be_reused_by_another_account(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "agent.db"))
            await store.connect()
            await store.get_or_create_session("session", "account-a", "user-a")
            with self.assertRaises(StoreError):
                await store.get_or_create_session("session", "account-b", "user-b")
            await store.close()


class RequestScopedClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_requests_use_their_own_api_keys(self):
        seen: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("X-API-Key", ""))
            await asyncio.sleep(0)
            return httpx.Response(200, json={"success": True, "data": {"balance": 1}})

        client = SendAfricaClient("https://api.example.test/v1", "SA-default")
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            base_url="https://api.example.test/v1", transport=httpx.MockTransport(handler)
        )
        try:
            async def request(key: str):
                with use_request_credentials(RequestCredentials(api_key=key)):
                    return await client.get_balance()

            await asyncio.gather(request("SA-one"), request("SA-two"))
            self.assertEqual(set(seen), {"SA-one", "SA-two"})
        finally:
            await client.aclose()


class ChatRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_sms_returns_action_preview_without_sending(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "agent.db"))
            await store.connect()
            runner = ChatRunner(Settings(ngamia_api_key="test"), FakeSendAfrica(), FakeMailAfrica(), FakeNgamia([
                {"content": "", "tool_calls": [{"id": "call-1", "name": "send_sms", "arguments": '{"to":"+255700000001","message":"Hi"}'}]}
            ]), store)
            result = await runner.handle_user_message("s", "a", "u", "send this")
            self.assertEqual(result["action"]["type"], "send_sms")
            self.assertEqual(result["action"]["status"], "awaiting_confirmation")
            await store.close()

    async def test_bulk_action_returns_structured_confirmation_without_sending(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "agent.db"))
            await store.connect()
            runner = ChatRunner(
                Settings(ngamia_api_key="test"),
                FakeSendAfrica(),
                FakeMailAfrica(),
                FakeNgamia(
                    [
                        {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "name": "send_bulk_sms",
                                    "arguments": '{"recipients":["+255700000001","+255700000002","+255700000003","+255700000004","+255700000005","+255700000006","+255700000007","+255700000008","+255700000009","+255700000010","+255700000011"],"message":"Hi"}',
                                }
                            ],
                        }
                    ]
                ),
                store,
            )
            result = await runner.handle_user_message("s", "a", "u", "send this")
            self.assertEqual(result["status"], "confirmation_required")
            self.assertEqual(result["tool_events"][0]["status"], "confirmation_required")
            await store.close()


if __name__ == "__main__":
    unittest.main()
