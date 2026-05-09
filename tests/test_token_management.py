import json
import logging
import os
import re
import stat
from unittest.mock import Mock

from app.core.token_manager import TokenManager
from app.core.kimi_token_store import load_configured_kimi_token, save_kimi_token
from app.main import main


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


def test_main_starts_without_kimi_token(
    tmp_data_dir,
    token_manager_store,
    monkeypatch,
    caplog,
):
    env = {
        "KIMI_TOKEN": "",
        "ADMIN_PASSWORD": "admin-password",
        "SESSION_SECRET": "test-session-secret",
        "DATA_DIR": str(tmp_data_dir),
        "SECURE_COOKIES": "false",
        "OPENAI_API_KEY": "",
        "HOST": "127.0.0.1",
        "PORT": "8000",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    run = Mock()
    monkeypatch.setattr("app.main.uvicorn.run", run)
    caplog.set_level(logging.WARNING, logger="kimi2api.main")

    main()

    run.assert_called_once()
    assert token_manager_store.get() is None
    assert "Kimi token is not configured" in caplog.text


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
