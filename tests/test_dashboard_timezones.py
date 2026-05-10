from app.config import Config
from app.core import logs
from app.dashboard.view_models import fmt_time, log_detail, log_list


def _log(request_id: str, timestamp: float = 1.0):
    logs.log_request(
        logs.RequestLog(
            request_id=request_id,
            timestamp=timestamp,
            method="GET",
            path="/v1/models",
            query_params={},
            client_ip="127.0.0.1",
            user_agent="pytest",
            api_key_name="Key 1",
            model="unknown",
            status="success",
            status_code=200,
            duration_ms=12.3,
            is_stream=False,
        )
    )


def test_fmt_time_uses_configured_timezone(config_override):
    config_override(TIMEZONE="Asia/Shanghai")

    assert fmt_time(1) == "1970-01-01 08:00:01 Asia/Shanghai"


def test_fmt_time_falls_back_to_shanghai_for_invalid_timezone(config_override):
    config_override(TIMEZONE="Invalid/Timezone")

    assert fmt_time(1) == "1970-01-01 08:00:01 Asia/Shanghai"


def test_log_list_and_detail_use_configured_timezone(tmp_data_dir, config_override):
    config_override(TIMEZONE="Asia/Shanghai")
    _log("req-timezone")

    listing = log_list()
    detail = log_detail("req-timezone", "http://testserver/")

    assert listing[0]["time_str"] == "01-01 08:00:01"
    assert detail is not None
    assert detail["time_str"] == "1970-01-01 08:00:01 Asia/Shanghai"


def test_config_load_prefers_timezone_and_falls_back_to_tz(monkeypatch):
    monkeypatch.delenv("TIMEZONE", raising=False)
    monkeypatch.setenv("TZ", "UTC")

    Config.load()

    assert Config.TIMEZONE == "UTC"

    monkeypatch.setenv("TIMEZONE", "Asia/Shanghai")

    Config.load()

    assert Config.TIMEZONE == "Asia/Shanghai"
