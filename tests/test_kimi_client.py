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


if __name__ == "__main__":
    unittest.main()
