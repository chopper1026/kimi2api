import asyncio
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core import keys, logs
from app.main import create_app


class RequestLoggingTest(unittest.TestCase):
    def setUp(self):
        keys._key_store.clear()
        logs._logs.clear()
        keys._key_store["sk-test"] = keys.ApiKey(
            key="sk-test",
            name="Test key",
            created_at=0.0,
        )
        self.client = TestClient(create_app())

    def tearDown(self):
        keys._key_store.clear()
        logs._logs.clear()

    def test_non_streaming_request_is_logged_immediately(self):
        response = self.client.get(
            "/v1/models",
            headers={"Authorization": "Bearer sk-test"},
        )

        self.assertEqual(response.status_code, 200)
        recent_logs = logs.get_recent_logs()
        self.assertEqual(len(recent_logs), 1)
        self.assertEqual(recent_logs[0].api_key_name, "Test key")
        self.assertEqual(recent_logs[0].status, "success")
        self.assertFalse(recent_logs[0].is_stream)

    def test_streaming_request_duration_includes_body_iteration(self):
        async def slow_stream(**_kwargs):
            await asyncio.sleep(0.05)
            yield 'data: {"choices": []}\n\n'
            yield "data: [DONE]\n\n"

        with patch("app.api.routes._create_streaming_chat_response", slow_stream):
            with self.client.stream(
                "POST",
                "/v1/chat/completions",
                headers={"Authorization": "Bearer sk-test"},
                json={
                    "model": "kimi-2.6-thinking",
                    "stream": True,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            ) as response:
                body = "".join(response.iter_text())

        self.assertEqual(response.status_code, 200)
        self.assertIn("data: [DONE]", body)

        recent_logs = logs.get_recent_logs()
        self.assertEqual(len(recent_logs), 1)
        self.assertTrue(recent_logs[0].is_stream)
        self.assertGreaterEqual(recent_logs[0].duration_ms, 50)


if __name__ == "__main__":
    unittest.main()
