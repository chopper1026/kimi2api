import json
import os
import re
import stat
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.config import Config
from app.core import auth
from app.core.token_manager import TokenManager
from app.core.kimi_token_store import load_configured_kimi_token, save_kimi_token
from app.main import create_app, main


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
    page = authenticated_admin_client.get("/admin/token")
    csrf = re.search(r'name="csrf-token" content="([^"]+)"', page.text).group(1)

    response = authenticated_admin_client.post(
        "/admin/token",
        data={"raw_token": "new-refresh-token"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    assert "new-****" in response.text
    assert "new-refresh-token" not in response.text
    assert token_manager_store.get() is not None
    assert token_manager_store.refresh_token() == "new-refresh-token"

    token_file = tmp_data_dir / "kimi_token.json"
    with open(token_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["token"] == "new-refresh-token"


def test_token_editor_is_hidden_until_requested(authenticated_admin_client):
    panel = authenticated_admin_client.get("/admin/token")

    assert panel.status_code == 200
    assert 'rel="icon"' in panel.text
    assert "/static/favicon.svg" in panel.text
    assert 'name="raw_token"' not in panel.text
    assert "配置 Token" in panel.text

    editor = authenticated_admin_client.get("/admin/token/edit")

    assert editor.status_code == 200
    assert 'name="raw_token"' in editor.text
    assert "保存 Token" in editor.text
