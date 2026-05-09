import unittest

from fastapi.testclient import TestClient

from app.core import keys, token_manager
from app.main import create_app


class StreamingErrorTest(unittest.TestCase):
    def setUp(self):
        keys._key_store.clear()
        keys._key_store["sk-test"] = keys.ApiKey(
            key="sk-test",
            name="Test key",
            created_at=0.0,
        )
        self.previous_manager = token_manager._manager
        token_manager._manager = None
        self.client = TestClient(create_app())

    def tearDown(self):
        token_manager._manager = self.previous_manager
        keys._key_store.clear()

    def test_streaming_chat_reports_missing_kimi_token_as_sse_error(self):
        with self.assertLogs("kimi2api.api", level="WARNING") as logs:
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
        self.assertIn('"error"', body)
        self.assertIn("Kimi token is not configured", body)
        self.assertIn("data: [DONE]", body)
        self.assertIn("Streaming chat request failed", "\n".join(logs.output))

    def test_streaming_responses_reports_missing_kimi_token_as_sse_error(self):
        with self.assertLogs("kimi2api.api", level="WARNING") as logs:
            with self.client.stream(
                "POST",
                "/v1/responses",
                headers={"Authorization": "Bearer sk-test"},
                json={
                    "model": "kimi-2.6-thinking",
                    "stream": True,
                    "input": "hi",
                },
            ) as response:
                body = "".join(response.iter_text())

        self.assertEqual(response.status_code, 200)
        self.assertIn('"error"', body)
        self.assertIn("Kimi token is not configured", body)
        self.assertIn("data: [DONE]", body)
        self.assertIn("Streaming responses request failed", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
