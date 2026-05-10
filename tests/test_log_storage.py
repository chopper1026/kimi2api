from app.core import logs


def _entry(request_id: str, **overrides):
    data = {
        "request_id": request_id,
        "timestamp": 1000.0,
        "method": "POST",
        "path": "/v1/chat/completions",
        "query_params": {"debug": "1"},
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "api_key_name": "Key 1",
        "model": "kimi-k2.6-thinking",
        "status": "success",
        "status_code": 200,
        "duration_ms": 12.3,
        "is_stream": False,
        "request_headers": {"authorization": "Bearer sk-secret", "x-trace": "trace-1"},
        "request_body": '{"messages":[{"role":"user","content":"hello"}]}',
        "response_headers": {"content-type": "application/json"},
        "response_body": '{"id":"chatcmpl-test","choices":[]}',
    }
    data.update(overrides)
    return logs.RequestLog(**data)


def test_request_logs_are_persisted_and_trimmed(tmp_data_dir, config_override):
    config_override(REQUEST_LOG_RETENTION=2)

    logs.log_request(_entry("req-1", model="kimi-k2.5"))
    logs.log_request(_entry("req-2", status="error", error_message="upstream timeout"))
    logs.log_request(_entry("req-3", path="/v1/responses", response_body="final answer"))

    assert (tmp_data_dir / "request_logs.sqlite3").exists()
    recent = logs.get_recent_logs(10)
    assert [entry.request_id for entry in recent] == ["req-3", "req-2"]
    assert logs.get_log("req-1") is None

    detail = logs.get_log("req-3")
    assert detail is not None
    assert detail.path == "/v1/responses"
    assert detail.response_body == ""


def test_request_logs_redact_credentials_and_truncate_bodies(tmp_data_dir, config_override):
    config_override(REQUEST_LOG_BODY_LIMIT_BYTES=32)

    logs.log_request(
        _entry(
            "req-redacted",
            request_headers={
                "Authorization": "Bearer sk-secret",
                "Cookie": "kimi2api_session=session-secret",
                "X-Trace": "trace-1",
            },
            request_body='{"token":"refresh-secret","message":"abcdefghijklmnopqrstuvwxyz"}',
            response_headers={"Set-Cookie": "session=secret", "Content-Type": "application/json"},
            response_body="x" * 128,
        )
    )

    detail = logs.get_log("req-redacted")
    assert detail is not None
    assert detail.request_headers["authorization"] == "[redacted]"
    assert detail.request_headers["cookie"] == "[redacted]"
    assert detail.request_headers["x-trace"] == "trace-1"
    assert detail.response_headers["set-cookie"] == "[redacted]"
    assert "refresh-secret" not in detail.request_body
    assert detail.request_body_truncated is True
    assert detail.response_body == ""
    assert detail.response_body_truncated is False


def test_stream_response_raw_body_is_parsed_but_not_persisted(tmp_data_dir, config_override):
    raw_stream = "\n".join(
        [
            'data: {"choices":[{"delta":{"reasoning_content":"先想"}}]}',
            'data: {"choices":[{"delta":{"content":"答案"}}]}',
            "data: [DONE]",
        ]
    )

    logs.log_request(
        _entry(
            "req-stream",
            is_stream=True,
            response_body=raw_stream,
            raw_stream_body=raw_stream,
        )
    )

    detail = logs.get_log("req-stream")
    assert detail is not None
    assert detail.response_body == ""
    assert detail.response_body_truncated is False
    assert detail.raw_stream_body == ""
    assert detail.parsed_response_text == "答案"
    assert detail.parsed_reasoning_content == "先想"

    results = logs.search_logs(q="先想", limit=10)
    assert [entry.request_id for entry in results] == ["req-stream"]


def test_request_logs_can_be_filtered(tmp_data_dir, config_override):
    config_override(REQUEST_LOG_RETENTION=10)
    logs.log_request(_entry("req-success", model="kimi-k2.5"))
    logs.log_request(
        _entry(
            "req-error",
            status="error",
            is_stream=True,
            error_message="upstream timeout",
            response_body="stream failed",
        )
    )

    results = logs.search_logs(
        q="timeout",
        status="error",
        model="kimi-k2.6-thinking",
        api_key_name="Key 1",
        path="/v1/chat/completions",
        stream="true",
        limit=10,
    )

    assert [entry.request_id for entry in results] == ["req-error"]


def test_request_logs_support_offset_and_filtered_count(tmp_data_dir, config_override):
    config_override(REQUEST_LOG_RETENTION=30)
    for index in range(25):
        logs.log_request(
            _entry(
                f"req-{index:02d}",
                timestamp=float(index),
                status="error" if index % 2 else "success",
                error_message="timeout" if index % 2 else "",
            )
        )

    first_page = logs.search_logs(limit=20)
    second_page = logs.search_logs(limit=20, offset=20)

    assert [entry.request_id for entry in first_page] == [
        f"req-{index:02d}" for index in range(24, 4, -1)
    ]
    assert [entry.request_id for entry in second_page] == [
        f"req-{index:02d}" for index in range(4, -1, -1)
    ]
    assert logs.count_logs() == 25
    assert logs.count_logs(q="timeout", status="error") == 12
