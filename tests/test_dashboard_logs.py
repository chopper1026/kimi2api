from app.core import logs


def _log(request_id: str, **overrides):
    data = {
        "request_id": request_id,
        "timestamp": 1000.0,
        "method": "POST",
        "path": "/v1/chat/completions",
        "query_params": {},
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "api_key_name": "Key 1",
        "model": "kimi-2.6-thinking",
        "status": "error",
        "status_code": 502,
        "duration_ms": 2345.6,
        "is_stream": True,
        "request_headers": {"authorization": "Bearer sk-secret", "content-type": "application/json"},
        "request_body": '{"model":"kimi-2.6-thinking","messages":[{"role":"user","content":"你是什么大模型"}]}',
        "response_headers": {"content-type": "text/event-stream"},
        "response_body": 'data: {"error":{"message":"upstream timeout"}}\n\n',
        "raw_stream_body": 'data: {"error":{"message":"upstream timeout"}}\n\n',
        "parsed_response_text": "",
        "parsed_reasoning_content": "",
        "error_message": "upstream timeout",
    }
    data.update(overrides)
    logs.log_request(logs.RequestLog(**data))


def test_admin_logs_can_filter_and_open_detail(authenticated_admin_client, tmp_data_dir):
    _log("req-timeout")
    _log("req-ok", status="success", status_code=200, duration_ms=42.4, error_message="", response_body="ok")

    listing = authenticated_admin_client.get(
        "/admin/logs",
        params={"q": "timeout", "status": "error", "stream": "true"},
    )

    assert listing.status_code == 200
    assert "req-timeout" in listing.text
    assert "req-ok" not in listing.text
    assert "upstream timeout" in listing.text
    assert "2.3s" in listing.text

    detail = authenticated_admin_client.get("/admin/logs/req-timeout")

    assert detail.status_code == 200
    assert "请求详情" in detail.text
    assert "复制 curl" not in detail.text
    assert "Bearer &lt;API_KEY&gt;" not in detail.text
    assert "2345.6ms" not in detail.text
    assert "2.3s" in detail.text
    assert "你是什么大模型" in detail.text
    assert "sk-secret" not in detail.text


def test_admin_log_detail_renders_request_body_as_collapsible_json_without_response_body(
    authenticated_admin_client,
    tmp_data_dir,
):
    _log(
        "req-json-body",
        request_body=(
            '{"model":"kimi-2.6-thinking","messages":[{"role":"user",'
            '"content":"找字段","metadata":{"trace_id":"trace-123"}}],'
            '"enable_thinking":true}'
        ),
        response_body='{"raw_response_marker":"hide-me"}',
        raw_stream_body='{"raw_response_marker":"hide-me"}',
        parsed_response_text="",
        parsed_reasoning_content="",
    )

    detail = authenticated_admin_client.get("/admin/logs/req-json-body")

    assert detail.status_code == 200
    assert 'data-json-view="request-body"' in detail.text
    assert "<summary" in detail.text
    assert "messages" in detail.text
    assert "trace_id" in detail.text
    assert "hide-me" not in detail.text

    response_section = detail.text.split('<h3 class="font-medium">响应</h3>', 1)[1]
    assert "Body" not in response_section


def test_admin_logs_use_ms_for_short_duration(authenticated_admin_client, tmp_data_dir):
    _log("req-fast", status="success", status_code=200, duration_ms=42.4, error_message="")

    listing = authenticated_admin_client.get("/admin/logs")

    assert listing.status_code == 200
    assert "42.4ms" in listing.text


def test_admin_logs_are_paginated_twenty_per_page(authenticated_admin_client, tmp_data_dir):
    for index in range(25):
        _log(f"req-page-{index:02d}", timestamp=float(index), error_message="timeout")

    first_page = authenticated_admin_client.get("/admin/logs", params={"q": "timeout"})
    second_page = authenticated_admin_client.get(
        "/admin/logs",
        params={"q": "timeout", "page": "2"},
    )

    assert first_page.status_code == 200
    assert "共 25 条" in first_page.text
    assert "第 1 / 2 页" in first_page.text
    assert "req-page-24" in first_page.text
    assert "req-page-05" in first_page.text
    assert "req-page-04" not in first_page.text
    assert "page=2" in first_page.text
    assert "q=timeout" in first_page.text

    assert second_page.status_code == 200
    assert "第 2 / 2 页" in second_page.text
    assert "req-page-04" in second_page.text
    assert "req-page-00" in second_page.text
    assert "req-page-24" not in second_page.text
