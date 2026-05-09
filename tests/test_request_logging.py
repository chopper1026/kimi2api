import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core import keys, logs
from app.main import create_app


@pytest.fixture
def client():
    keys._key_store.clear()
    logs._logs.clear()
    keys._key_store["sk-test"] = keys.ApiKey(
        key="sk-test",
        name="Test key",
        created_at=0.0,
    )
    try:
        yield TestClient(create_app())
    finally:
        keys._key_store.clear()
        logs._logs.clear()


def test_non_streaming_request_is_logged_immediately(client):
    response = client.get(
        "/v1/models",
        headers={"Authorization": "Bearer sk-test"},
    )

    assert response.status_code == 200
    recent_logs = logs.get_recent_logs()
    assert len(recent_logs) == 1
    assert recent_logs[0].api_key_name == "Test key"
    assert recent_logs[0].status == "success"
    assert recent_logs[0].is_stream is False


def test_streaming_request_duration_includes_body_iteration(client):
    async def slow_stream(**_kwargs):
        await asyncio.sleep(0.05)
        yield 'data: {"choices": []}\n\n'
        yield "data: [DONE]\n\n"

    with patch("app.api.routes._create_streaming_chat_response", slow_stream):
        with client.stream(
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

    assert response.status_code == 200
    assert "data: [DONE]" in body

    recent_logs = logs.get_recent_logs()
    assert len(recent_logs) == 1
    assert recent_logs[0].is_stream is True
    assert recent_logs[0].duration_ms >= 50
