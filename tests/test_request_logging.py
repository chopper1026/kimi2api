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
    recent_logs = logs.get_recent_logs()
    assert len(recent_logs) == 1
    assert recent_logs[0].api_key_name == "Test key"
    assert recent_logs[0].status == "success"
    assert recent_logs[0].is_stream is False


def test_streaming_request_duration_includes_body_iteration(
    api_client,
    configured_api_key,
    reset_logs,
):
    async def slow_stream(**_kwargs):
        await asyncio.sleep(0.05)
        yield 'data: {"choices": []}\n\n'
        yield "data: [DONE]\n\n"

    with patch("app.api.routes._create_streaming_chat_response", slow_stream):
        with api_client.stream(
            "POST",
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {configured_api_key.key}"},
            json={
                "model": "kimi-2.6-thinking",
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
