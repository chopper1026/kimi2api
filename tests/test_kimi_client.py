import asyncio
import json
import unittest

from app.kimi.client import Kimi2API
from app.kimi.protocol import ConversationContext


class FakeGrpcResponse:
    def __init__(self, *payloads: bytes):
        self._payloads = payloads

    async def aiter_bytes(self):
        for payload in self._payloads:
            yield payload


def grpc_frame(payload: bytes, flag: int = 0) -> bytes:
    return bytes([flag]) + len(payload).to_bytes(4, "big") + payload


class KimiClientTest(unittest.TestCase):
    def test_iter_grpc_events_skips_non_json_frames(self):
        client = Kimi2API.__new__(Kimi2API)
        context = ConversationContext(request_conversation_id="local")
        response = FakeGrpcResponse(
            grpc_frame(b"not json"),
            grpc_frame(json.dumps({"done": {}}).encode("utf-8")),
        )

        async def collect_events():
            return [
                event
                async for event in client._iter_grpc_events(response, context)
            ]

        self.assertEqual(asyncio.run(collect_events()), [{"done": {}}])

    def test_unflagged_text_after_thinking_is_answer_content(self):
        client = Kimi2API.__new__(Kimi2API)

        delta = client._extract_delta(
            {
                "mask": "block.text",
                "block": {"text": {"content": "这是最终回答"}},
            },
            current_phase="thinking",
        )

        self.assertEqual(delta["content"], "这是最终回答")
        self.assertIsNone(delta["reasoning_content"])

    def test_explicit_thinking_text_remains_reasoning_content(self):
        client = Kimi2API.__new__(Kimi2API)

        delta = client._extract_delta(
            {
                "mask": "block.text",
                "block": {"text": {"content": "这里是推理", "flags": "thinking"}},
            },
            current_phase=None,
        )

        self.assertIsNone(delta["content"])
        self.assertEqual(delta["reasoning_content"], "这里是推理")


if __name__ == "__main__":
    unittest.main()
