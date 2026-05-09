import json

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


async def test_iter_grpc_events_skips_non_json_frames():
    client = Kimi2API.__new__(Kimi2API)
    context = ConversationContext(request_conversation_id="local")
    response = FakeGrpcResponse(
        grpc_frame(b"not json"),
        grpc_frame(json.dumps({"done": {}}).encode("utf-8")),
    )

    events = [
        event
        async for event in client._iter_grpc_events(response, context)
    ]

    assert events == [{"done": {}}]


def test_unflagged_text_after_thinking_is_answer_content():
    client = Kimi2API.__new__(Kimi2API)

    delta = client._extract_delta(
        {
            "mask": "block.text",
            "block": {"text": {"content": "这是最终回答"}},
        },
        current_phase="thinking",
    )

    assert delta["content"] == "这是最终回答"
    assert delta["reasoning_content"] is None


def test_explicit_thinking_text_remains_reasoning_content():
    client = Kimi2API.__new__(Kimi2API)

    delta = client._extract_delta(
        {
            "mask": "block.text",
            "block": {"text": {"content": "这里是推理", "flags": "thinking"}},
        },
        current_phase=None,
    )

    assert delta["content"] is None
    assert delta["reasoning_content"] == "这里是推理"
