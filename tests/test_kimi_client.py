import json

import httpx
import pytest

from app.kimi.client import Kimi2API
from app.kimi.model_catalog import KimiModelSpec
from app.kimi.protocol import ConversationContext, KimiAPIError


class FakeGrpcResponse:
    def __init__(self, *payloads: bytes):
        self._payloads = payloads

    async def aiter_bytes(self):
        for payload in self._payloads:
            yield payload


class BrokenGrpcResponse:
    async def aiter_bytes(self):
        raise httpx.RemoteProtocolError(
            "peer closed connection without sending complete message body "
            "(incomplete chunked read)"
        )
        yield b""


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


async def test_iter_grpc_events_wraps_incomplete_chunked_read_as_upstream_error():
    client = Kimi2API.__new__(Kimi2API)
    context = ConversationContext(request_conversation_id="local")
    response = BrokenGrpcResponse()

    with pytest.raises(KimiAPIError) as exc_info:
        [
            event
            async for event in client._iter_grpc_events(response, context)
        ]

    assert "Kimi upstream stream interrupted" in str(exc_info.value)
    assert exc_info.value.upstream_error_type == "stream_interrupted"


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


def test_build_chat_payload_uses_resolved_model_spec_fields():
    client = Kimi2API.__new__(Kimi2API)
    spec = KimiModelSpec(
        id="kimi-k2.6-agent",
        display_name="K2.6 Agent",
        scenario="SCENARIO_OK_COMPUTER",
        thinking=False,
        kimi_plus_id="ok-computer",
        agent_mode="TYPE_NORMAL",
    )

    payload = client._build_chat_payload(
        model_spec=spec,
        messages=[{"role": "user", "content": "hi"}],
        context=ConversationContext(request_conversation_id="local"),
        enable_web_search=False,
    )

    assert payload["scenario"] == "SCENARIO_OK_COMPUTER"
    assert payload["message"]["scenario"] == "SCENARIO_OK_COMPUTER"
    assert payload["options"]["thinking"] is False
    assert payload["kimiplusId"] == "ok-computer"
    assert payload["agentMode"] == "TYPE_NORMAL"


def test_build_chat_payload_preserves_thinking_model_flag():
    client = Kimi2API.__new__(Kimi2API)
    spec = KimiModelSpec(
        id="kimi-k2.6-thinking",
        display_name="K2.6 Thinking",
        scenario="SCENARIO_K2D5",
        thinking=True,
    )

    payload = client._build_chat_payload(
        model_spec=spec,
        messages=[{"role": "user", "content": "hi"}],
        context=ConversationContext(request_conversation_id="local"),
        enable_web_search=False,
    )

    assert payload["scenario"] == "SCENARIO_K2D5"
    assert payload["options"]["thinking"] is True
    assert "kimiplusId" not in payload
    assert "agentMode" not in payload
