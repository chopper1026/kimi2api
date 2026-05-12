import json

import httpx
import pytest

from app.core.kimi_account_pool import close_account_pool, init_account_pool
from app.core.kimi_account_store import KimiAccountConfig
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


def _account(account_id: str, name: str) -> KimiAccountConfig:
    return KimiAccountConfig(
        id=account_id,
        name=name,
        raw_token=f"token-{account_id}",
        enabled=True,
        max_concurrency=1,
        min_interval_seconds=0,
        device_id="1" * 19 if account_id.endswith("a") else "2" * 19,
        created_at=1,
        updated_at=1,
    )


def _content_event(text: str):
    return {
        "mask": "block.text",
        "block": {"text": {"content": text}},
    }


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


@pytest.mark.asyncio
async def test_sync_chat_switches_accounts_when_first_fails_before_output(tmp_data_dir):
    pool = init_account_pool(
        [
            _account("acc-a", "A"),
            _account("acc-b", "B"),
        ],
        base_url="https://kimi.example.test",
    )
    client = Kimi2API(max_retries=2)
    calls = []

    async def fake_iter(runtime, _content, _context):
        calls.append(runtime.account_id)
        if runtime.account_id == "acc-a":
            raise KimiAPIError(
                "rate limited",
                upstream_status_code=429,
                upstream_error_type="rate_limited",
                retry_after=60,
            )
        yield _content_event("fallback ok")
        yield {"done": {}}

    client._iter_chat_events_for_runtime = fake_iter

    try:
        result = await client._sync_chat(
            {"message": {"blocks": []}},
            "kimi-k2.6",
            ConversationContext(request_conversation_id="local"),
        )
    finally:
        await client.close()
        await close_account_pool()

    assert calls == ["acc-a", "acc-b"]
    assert result.choices[0].message.content == "fallback ok"
    assert pool.account_infos()[0]["token_healthy"] is False
    assert "冷却" in pool.account_infos()[0]["token_status"]


@pytest.mark.asyncio
async def test_stream_chat_switches_only_before_first_chunk(tmp_data_dir):
    init_account_pool(
        [
            _account("acc-a", "A"),
            _account("acc-b", "B"),
        ],
        base_url="https://kimi.example.test",
    )
    client = Kimi2API(max_retries=2)
    calls = []

    async def fake_iter(runtime, _content, _context):
        calls.append(runtime.account_id)
        if runtime.account_id == "acc-a":
            raise KimiAPIError(
                "server error",
                upstream_status_code=500,
                upstream_error_type="server_error",
            )
        yield _content_event("stream fallback")
        yield {"done": {}}

    client._iter_chat_events_for_runtime = fake_iter

    try:
        chunks = [
            chunk
            async for chunk in client._stream_chat(
                {"message": {"blocks": []}},
                "kimi-k2.6",
                ConversationContext(request_conversation_id="local"),
            )
        ]
    finally:
        await client.close()
        await close_account_pool()

    assert calls == ["acc-a", "acc-b"]
    assert chunks[0].choices[0]["delta"]["role"] == "assistant"
    assert chunks[1].choices[0]["delta"]["content"] == "stream fallback"


@pytest.mark.asyncio
async def test_stream_chat_does_not_switch_after_chunk_is_sent(tmp_data_dir):
    init_account_pool(
        [
            _account("acc-a", "A"),
            _account("acc-b", "B"),
        ],
        base_url="https://kimi.example.test",
    )
    client = Kimi2API(max_retries=2)
    calls = []

    async def fake_iter(runtime, _content, _context):
        calls.append(runtime.account_id)
        yield _content_event("partial")
        raise KimiAPIError(
            "server error",
            upstream_status_code=500,
            upstream_error_type="server_error",
        )

    client._iter_chat_events_for_runtime = fake_iter

    try:
        with pytest.raises(KimiAPIError):
            [
                chunk
                async for chunk in client._stream_chat(
                    {"message": {"blocks": []}},
                    "kimi-k2.6",
                    ConversationContext(request_conversation_id="local"),
                )
            ]
    finally:
        await client.close()
        await close_account_pool()

    assert calls == ["acc-a"]
