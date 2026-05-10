import asyncio
from unittest.mock import patch

from app.core import logs


def test_non_streaming_request_is_logged_immediately(
    api_client,
    configured_api_key,
    reset_logs,
):
    response = api_client.get(
        "/v1/models",
        headers={"Authorization": f"Bearer {configured_api_key.key}"},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    recent_logs = logs.get_recent_logs()
    assert len(recent_logs) == 1
    assert recent_logs[0].api_key_name == "Test key"
    assert recent_logs[0].status == "success"
    assert recent_logs[0].is_stream is False
    assert recent_logs[0].request_id == response.headers["x-request-id"]
    assert recent_logs[0].method == "GET"
    assert recent_logs[0].path == "/v1/models"
    assert recent_logs[0].request_headers["authorization"] == "[redacted]"
    assert recent_logs[0].response_body == ""


def test_streaming_request_duration_includes_body_iteration(
    api_client,
    configured_api_key,
    reset_logs,
):
    async def slow_stream(**_kwargs):
        await asyncio.sleep(0.05)
        yield 'data: {"choices":[{"delta":{"reasoning_content":"想一下"}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":"好了"}}]}\n\n'
        yield "data: [DONE]\n\n"

    with patch("app.api.routes._create_streaming_chat_response", slow_stream):
        with api_client.stream(
            "POST",
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {configured_api_key.key}"},
            json={
                "model": "kimi-k2.6-thinking",
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
        ) as response:
            body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "data: [DONE]" in body

    recent_logs = logs.get_recent_logs()
    assert len(recent_logs) == 1
    assert recent_logs[0].is_stream is True
    assert recent_logs[0].duration_ms >= 50
    detail = logs.get_log(recent_logs[0].request_id)
    assert detail.raw_stream_body == ""
    assert detail.response_body == ""
    assert detail.parsed_response_text == "好了"
    assert detail.parsed_reasoning_content == "想一下"
