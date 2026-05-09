import asyncio
import json
import os
import re
import stat
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Config
from app.core import auth, token_manager
from app.main import create_app, main


class TokenManagementTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_config = {
            "KIMI_TOKEN": Config.KIMI_TOKEN,
            "DATA_DIR": Config.DATA_DIR,
            "ADMIN_PASSWORD": Config.ADMIN_PASSWORD,
            "SESSION_SECRET": Config.SESSION_SECRET,
            "SECURE_COOKIES": Config.SECURE_COOKIES,
        }
        self.previous_manager = token_manager._manager
        token_manager._manager = None
        Config.DATA_DIR = self.tmp.name
        Config.KIMI_TOKEN = ""
        Config.ADMIN_PASSWORD = "admin-password"
        Config.SESSION_SECRET = "test-session-secret"
        Config.SECURE_COOKIES = False
        auth.init_auth()

    def tearDown(self):
        current_manager = token_manager._manager
        if current_manager is not None:
            asyncio.run(current_manager.close())
        token_manager._manager = self.previous_manager
        for key, value in self.previous_config.items():
            setattr(Config, key, value)
        self.tmp.cleanup()

    def test_saved_token_takes_precedence_over_env_token(self):
        from app.core.kimi_token_store import load_configured_kimi_token, save_kimi_token

        Config.KIMI_TOKEN = "env-token"
        save_kimi_token("saved-token")

        self.assertEqual(load_configured_kimi_token(), "saved-token")

    def test_saved_token_file_is_private(self):
        from app.core.kimi_token_store import save_kimi_token

        save_kimi_token("saved-token")

        token_file = os.path.join(self.tmp.name, "kimi_token.json")
        mode = stat.S_IMODE(os.stat(token_file).st_mode)
        self.assertEqual(mode, 0o600)

    def test_main_starts_without_kimi_token(self):
        env = {
            "KIMI_TOKEN": "",
            "ADMIN_PASSWORD": "admin-password",
            "SESSION_SECRET": "test-session-secret",
            "DATA_DIR": self.tmp.name,
            "SECURE_COOKIES": "false",
            "OPENAI_API_KEY": "",
            "HOST": "127.0.0.1",
            "PORT": "8000",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("app.main.uvicorn.run") as run:
                with self.assertLogs("kimi2api.main", level="WARNING") as logs:
                    main()

        run.assert_called_once()
        self.assertIsNone(token_manager._manager)
        self.assertIn("Kimi token is not configured", "\n".join(logs.output))

    def test_admin_can_save_token_and_replace_runtime_manager(self):
        client = TestClient(create_app())

        login = client.post(
            "/admin/login",
            data={"password": "admin-password"},
            follow_redirects=False,
        )
        self.assertEqual(login.status_code, 302)

        page = client.get("/admin/token")
        csrf = re.search(r'name="csrf-token" content="([^"]+)"', page.text).group(1)

        response = client.post(
            "/admin/token",
            data={"raw_token": "new-refresh-token"},
            headers={"X-CSRF-Token": csrf},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("new-****", response.text)
        self.assertNotIn("new-refresh-token", response.text)
        self.assertIsNotNone(token_manager._manager)
        self.assertEqual(token_manager._manager._state.refresh_token, "new-refresh-token")

        token_file = os.path.join(self.tmp.name, "kimi_token.json")
        with open(token_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["token"], "new-refresh-token")

    def test_token_editor_is_hidden_until_requested(self):
        client = TestClient(create_app())

        login = client.post(
            "/admin/login",
            data={"password": "admin-password"},
            follow_redirects=False,
        )
        self.assertEqual(login.status_code, 302)

        panel = client.get("/admin/token")
        self.assertEqual(panel.status_code, 200)
        self.assertIn('rel="icon"', panel.text)
        self.assertIn("/static/favicon.svg", panel.text)
        self.assertNotIn('name="raw_token"', panel.text)
        self.assertIn("配置 Token", panel.text)

        editor = client.get("/admin/token/edit")

        self.assertEqual(editor.status_code, 200)
        self.assertIn('name="raw_token"', editor.text)
        self.assertIn("保存 Token", editor.text)


if __name__ == "__main__":
    unittest.main()
