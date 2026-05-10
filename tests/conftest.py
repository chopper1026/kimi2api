import asyncio
from dataclasses import dataclass
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.core import auth, keys, logs, token_manager
from app.core.keys import ApiKey
from app.main import create_app


CONFIG_FIELDS = (
    "KIMI_TOKEN",
    "KIMI_API_BASE",
    "TIMEOUT",
    "DEFAULT_MODEL",
    "OPENAI_API_KEY",
    "ADMIN_PASSWORD",
    "SESSION_SECRET",
    "SECURE_COOKIES",
    "HOST",
    "PORT",
    "RELOAD",
    "DATA_DIR",
    "REQUEST_LOG_RETENTION",
    "REQUEST_LOG_BODY_LIMIT_BYTES",
    "TIMEZONE",
)


@pytest.fixture(autouse=True)
def restore_config_state():
    previous = {name: getattr(Config, name) for name in CONFIG_FIELDS}
    try:
        yield
    finally:
        for name, value in previous.items():
            setattr(Config, name, value)


@pytest.fixture
def reset_key_store():
    keys._key_store.clear()
    try:
        yield
    finally:
        keys._key_store.clear()


@pytest.fixture
def reset_logs(tmp_data_dir):
    logs.clear_logs()
    try:
        yield
    finally:
        logs.clear_logs()


@dataclass
class TokenManagerStore:
    def get(self):
        return token_manager._manager

    def set(self, manager) -> None:
        token_manager._manager = manager

    def refresh_token(self) -> Optional[str]:
        manager = token_manager._manager
        if manager is None:
            return None
        return manager.get_state().refresh_token


@pytest.fixture
def token_manager_store():
    previous_manager = token_manager._manager
    token_manager._manager = None
    try:
        yield TokenManagerStore()
    finally:
        current_manager = token_manager._manager
        if current_manager is not None:
            asyncio.run(current_manager.close())
        token_manager._manager = previous_manager


@pytest.fixture
def config_override(monkeypatch):
    def apply(**values: Any) -> None:
        for name, value in values.items():
            monkeypatch.setattr(Config, name, value)

    return apply


@pytest.fixture
def tmp_data_dir(tmp_path, config_override):
    config_override(DATA_DIR=str(tmp_path))
    return tmp_path


@pytest.fixture
def admin_config(tmp_data_dir, config_override):
    config_override(
        KIMI_TOKEN="",
        ADMIN_PASSWORD="admin-password",
        SESSION_SECRET="test-session-secret",
        SECURE_COOKIES=False,
    )
    auth.init_auth()


@pytest.fixture
def configured_api_key(reset_key_store):
    api_key = ApiKey(
        key="sk-test",
        name="Test key",
        created_at=0.0,
    )
    keys._key_store[api_key.key] = api_key
    return api_key


@pytest.fixture
def api_client(tmp_data_dir):
    return TestClient(create_app())


@pytest.fixture
def authenticated_admin_client(api_client, admin_config):
    response = api_client.post(
        "/admin/login",
        data={"password": "admin-password"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    return api_client
