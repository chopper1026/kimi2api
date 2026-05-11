import json

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
        "model": "kimi-k2.6-thinking",
        "status": "error",
        "status_code": 502,
        "duration_ms": 2345.6,
        "is_stream": True,
        "request_headers": {"authorization": "Bearer sk-secret", "content-type": "application/json"},
        "request_body": '{"model":"kimi-k2.6-thinking","messages":[{"role":"user","content":"你是什么大模型"}]}',
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
        "/admin/api/logs",
        params={"q": "timeout", "status": "error", "stream": "true"},
    )

    assert listing.status_code == 200
    body = listing.json()
    assert len(body["logs"]) == 1
    assert body["logs"][0]["request_id"] == "req-timeout"
    assert "timeout" in body["logs"][0]["error_message"]
    assert body["logs"][0]["duration_display"] == "2.3s"

    detail = authenticated_admin_client.get("/admin/api/logs/req-timeout")

    assert detail.status_code == 200
    detail_data = detail.json()
    assert detail_data["request_id"] == "req-timeout"
    assert detail_data["duration_display"] == "2.3s"
    assert "你是什么大模型" in json.dumps(detail_data["request_body_json"], ensure_ascii=False)
    assert "sk-secret" not in json.dumps(detail_data["request_body_json"], ensure_ascii=False)


def test_admin_log_detail_has_parsed_request_body_json(authenticated_admin_client, tmp_data_dir):
    _log(
        "req-json-body",
        request_body=(
            '{"model":"kimi-k2.6-thinking","messages":[{"role":"user",'
            '"content":"找字段","metadata":{"trace_id":"trace-123"}}],'
            '"enable_thinking":true}'
        ),
        response_body='{"raw_response_marker":"hide-me"}',
        raw_stream_body='{"raw_response_marker":"hide-me"}',
        parsed_response_text="",
        parsed_reasoning_content="",
    )

    detail = authenticated_admin_client.get("/admin/api/logs/req-json-body")

    assert detail.status_code == 200
    detail_data = detail.json()
    assert detail_data["request_body_is_json"] is True
    assert detail_data["request_body_json"] is not None
    assert "messages" in str(detail_data["request_body_json"])
    assert "trace_id" in str(detail_data["request_body_json"])


def test_admin_logs_use_ms_for_short_duration(authenticated_admin_client, tmp_data_dir):
    _log("req-fast", status="success", status_code=200, duration_ms=42.4, error_message="")

    listing = authenticated_admin_client.get("/admin/api/logs")

    assert listing.status_code == 200
    assert listing.json()["logs"][0]["duration_display"] == "42.4ms"


def test_admin_logs_show_upstream_error_metadata(authenticated_admin_client, tmp_data_dir):
    _log(
        "req-upstream",
        error_message="upstream rate limited",
        upstream_status_code=429,
        upstream_error_type="rate_limited",
        upstream_retry_after=1.5,
    )

    listing = authenticated_admin_client.get("/admin/api/logs", params={"q": "rate_limited"})
    detail = authenticated_admin_client.get("/admin/api/logs/req-upstream")

    assert listing.status_code == 200
    log_entry = listing.json()["logs"][0]
    assert "Kimi 429" in log_entry["upstream_summary"]
    assert "rate_limited" in log_entry["upstream_summary"]

    detail_data = detail.json()
    assert "Kimi 429" in detail_data["upstream_summary"]
    assert "rate_limited" in detail_data["upstream_summary"]
    assert "Retry-After: 1.5s" in detail_data["upstream_summary"]


def test_admin_logs_leave_model_blank_for_model_list_request(
    authenticated_admin_client,
    tmp_data_dir,
):
    _log("req-model-list", method="GET", path="/v1/models", model="unknown")

    listing = authenticated_admin_client.get("/admin/api/logs")

    assert listing.status_code == 200
    assert listing.json()["logs"][0]["model"] == ""


def test_admin_logs_are_paginated_twenty_per_page(authenticated_admin_client, tmp_data_dir):
    for index in range(25):
        _log(f"req-page-{index:02d}", timestamp=float(index), error_message="timeout")

    first_page = authenticated_admin_client.get("/admin/api/logs", params={"q": "timeout"})
    second_page = authenticated_admin_client.get(
        "/admin/api/logs",
        params={"q": "timeout", "page": "2"},
    )

    assert first_page.status_code == 200
    first_data = first_page.json()
    assert first_data["pagination"]["total"] == 25
    assert first_data["pagination"]["page_count"] == 2
    assert len(first_data["logs"]) == 20

    assert second_page.status_code == 200
    second_data = second_page.json()
    assert second_data["pagination"]["page"] == 2
    assert len(second_data["logs"]) == 5
