import logging

from app.core import logs as request_logs


def test_streaming_chat_reports_missing_kimi_token_as_sse_error(
    api_client,
    configured_api_key,
    reset_logs,
    token_manager_store,
    caplog,
):
    caplog.set_level(logging.WARNING, logger="kimi2api.api")

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
    assert '"error"' in body
    assert "Kimi token is not configured" in body
    assert "data: [DONE]" in body
    assert "Streaming chat request failed" in caplog.text

    recent_logs = request_logs.get_recent_logs()
    assert len(recent_logs) == 1
    assert recent_logs[0].status == "error"
    assert recent_logs[0].is_stream is True


def test_streaming_responses_reports_missing_kimi_token_as_sse_error(
    api_client,
    configured_api_key,
    reset_logs,
    token_manager_store,
    caplog,
):
    caplog.set_level(logging.WARNING, logger="kimi2api.api")

    with api_client.stream(
        "POST",
        "/v1/responses",
        headers={"Authorization": f"Bearer {configured_api_key.key}"},
        json={
            "model": "kimi-k2.6-thinking",
            "stream": True,
            "input": "hi",
        },
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"error"' in body
    assert "Kimi token is not configured" in body
    assert "data: [DONE]" in body
    assert "Streaming responses request failed" in caplog.text

    recent_logs = request_logs.get_recent_logs()
    assert len(recent_logs) == 1
    assert recent_logs[0].status == "error"
    assert recent_logs[0].is_stream is True
