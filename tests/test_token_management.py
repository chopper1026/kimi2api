import base64
import json
import os
import stat
import time
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.core import auth
from app.core.token_manager import TokenManager
from app.core.kimi_token_store import load_configured_kimi_token, save_kimi_token
from app.kimi.protocol import KimiAPIError
from app.main import create_app, main


def _b64_json(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _jwt_access_token() -> str:
    return ".".join([
        _b64_json({"alg": "none", "typ": "JWT"}),
        _b64_json({
            "app_id": "kimi",
            "typ": "access",
            "exp": int(time.time()) + 30 * 24 * 60 * 60,
        }),
        "signature",
    ])


def test_saved_token_takes_precedence_over_env_token(admin_config, config_override):
    config_override(KIMI_TOKEN="env-token")

    save_kimi_token("saved-token")

    assert load_configured_kimi_token() == "saved-token"


def test_saved_token_file_is_private(admin_config, tmp_data_dir):
    save_kimi_token("saved-token")

    token_file = tmp_data_dir / "kimi_token.json"
    mode = stat.S_IMODE(os.stat(token_file).st_mode)
    assert mode == 0o600


def test_token_manager_exposes_state_snapshot():
    manager = TokenManager("refresh-token")

    try:
        state = manager.get_state()
        state.access_token = "changed"

        assert state.refresh_token == "refresh-token"
        assert manager.get_state().access_token == "refresh-token"
    finally:
        import asyncio

        asyncio.run(manager.close())


@pytest.mark.asyncio
async def test_token_manager_uses_valid_cached_access_token_without_refresh():
    class FailingTransport:
        async def request(self, *_args, **_kwargs):
            raise AssertionError("refresh endpoint should not be called")

    cached_access = _jwt_access_token()
    manager = TokenManager(
        "refresh-token",
        cached_access_token=cached_access,
        cached_access_expires_at=time.time() + 3600,
        transport=FailingTransport(),
    )

    try:
        assert await manager.get_access_token() == cached_access
        state = manager.get_state()
        assert state.access_token == cached_access
        assert state.refresh_token == "refresh-token"
        assert state.token_type == "jwt"
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_token_manager_persists_refreshed_access_token_via_callback():
    refreshed_access = _jwt_access_token()
    persisted = []

    class RefreshTransport:
        async def request(self, *_args, **_kwargs):
            return httpx.Response(200, json={"access_token": refreshed_access})

    def on_refreshed(state):
        persisted.append((state.access_token, state.expires_at))

    manager = TokenManager(
        "refresh-token",
        transport=RefreshTransport(),
        on_token_refreshed=on_refreshed,
    )

    try:
        assert await manager.get_access_token() == refreshed_access
    finally:
        await manager.close()

    assert persisted == [(refreshed_access, manager.get_state().expires_at)]


def test_main_starts_uvicorn_with_loaded_server_config(
    tmp_data_dir,
    token_manager_store,
    monkeypatch,
):
    env = {
        "KIMI_TOKEN": "",
        "ADMIN_PASSWORD": "admin-password",
        "SESSION_SECRET": "test-session-secret",
        "DATA_DIR": str(tmp_data_dir),
        "SECURE_COOKIES": "false",
        "OPENAI_API_KEY": "",
        "HOST": "127.0.0.1",
        "PORT": "8123",
        "RELOAD": "true",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    run = Mock()
    monkeypatch.setattr("app.main.uvicorn.run", run)

    main()

    run.assert_called_once_with(
        "app.main:create_app",
        host="127.0.0.1",
        port=8123,
        reload=True,
        factory=True,
    )
    assert token_manager_store.get() is None


def test_create_app_initializes_runtime_from_environment(
    tmp_data_dir,
    reset_key_store,
    token_manager_store,
    monkeypatch,
):
    monkeypatch.setattr(auth, "_admin_password", None)
    monkeypatch.setattr(auth, "_serializer", None)
    monkeypatch.setenv("KIMI_TOKEN", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("DATA_DIR", str(tmp_data_dir))
    monkeypatch.setenv("SECURE_COOKIES", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-test")

    client = TestClient(create_app())

    login = client.get("/admin/login")
    models = client.get(
        "/v1/models",
        headers={"Authorization": "Bearer sk-env-test"},
    )

    assert login.status_code == 200
    assert "Dashboard disabled" not in login.text
    assert models.status_code == 200
    assert token_manager_store.get() is None


def test_create_app_can_skip_runtime_initialization(
    tmp_data_dir,
    config_override,
    monkeypatch,
):
    monkeypatch.setenv("PORT", "9999")
    config_override(PORT=1234, DATA_DIR=str(tmp_data_dir))

    TestClient(create_app(initialize=False))

    assert Config.PORT == 1234


def test_admin_can_save_token_and_replace_runtime_manager(
    authenticated_admin_client,
    tmp_data_dir,
    token_manager_store,
):
    session = authenticated_admin_client.get("/admin/api/session")
    csrf = session.json()["csrf_token"]

    response = authenticated_admin_client.post(
        "/admin/api/token",
        json={"raw_token": "new-refresh-token"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["token"]["token_preview"] == "new****ken"
    assert body["token"]["token_type"] == "refresh token"
    assert "new-refresh-token" not in body["token"]["token_preview"]
    assert token_manager_store.get() is not None
    assert token_manager_store.refresh_token() == "new-refresh-token"

    token_file = tmp_data_dir / "kimi_token.json"
    with open(token_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["token"] == "new-refresh-token"


def test_admin_token_save_empty_token_returns_400(authenticated_admin_client):
    session = authenticated_admin_client.get("/admin/api/session")
    csrf = session.json()["csrf_token"]

    response = authenticated_admin_client.post(
        "/admin/api/token",
        json={"raw_token": ""},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert response.json()["success"] is False
    assert response.json()["error"] == "Token 不能为空"


def test_admin_token_refresh_without_token_returns_400(
    authenticated_admin_client,
    token_manager_store,
):
    session = authenticated_admin_client.get("/admin/api/session")
    csrf = session.json()["csrf_token"]

    assert token_manager_store.get() is None

    response = authenticated_admin_client.post(
        "/admin/api/token/refresh",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert response.json()["success"] is False
    assert response.json()["error"] == "请先保存 Token"


def test_admin_token_refresh_upstream_failure_returns_dashboard_json(
    authenticated_admin_client,
    monkeypatch,
):
    class FailingManager:
        async def invalidate_and_retry(self):
            raise KimiAPIError("upstream refresh failed")

    monkeypatch.setattr(
        "app.dashboard.api_routes.get_token_manager",
        lambda: FailingManager(),
    )
    session = authenticated_admin_client.get("/admin/api/session")
    csrf = session.json()["csrf_token"]

    response = authenticated_admin_client.post(
        "/admin/api/token/refresh",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 502
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "upstream refresh failed"
    assert isinstance(body["token"], dict)


def test_token_info_returns_current_state(authenticated_admin_client):
    response = authenticated_admin_client.get("/admin/api/token")

    assert response.status_code == 200
    body = response.json()
    assert "token_type" in body
    assert "token_healthy" in body
    assert "token_status" in body
