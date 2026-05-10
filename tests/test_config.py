import pytest

from app.config import Config


def _clear_request_log_limit_env(monkeypatch):
    monkeypatch.delenv("REQUEST_LOG_BODY_LIMIT", raising=False)


def test_config_load_accepts_human_readable_request_log_body_limit(monkeypatch):
    _clear_request_log_limit_env(monkeypatch)
    monkeypatch.setenv("REQUEST_LOG_BODY_LIMIT", "1.5MB")

    Config.load()

    assert Config.REQUEST_LOG_BODY_LIMIT == 1572864


def test_config_load_uses_one_megabyte_default_request_log_body_limit(monkeypatch):
    _clear_request_log_limit_env(monkeypatch)

    Config.load()

    assert Config.REQUEST_LOG_BODY_LIMIT == 1048576


def test_config_load_rejects_invalid_request_log_body_limit(monkeypatch):
    _clear_request_log_limit_env(monkeypatch)
    monkeypatch.setenv("REQUEST_LOG_BODY_LIMIT", "10XB")

    with pytest.raises(ValueError, match="REQUEST_LOG_BODY_LIMIT"):
        Config.load()
