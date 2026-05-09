import asyncio
import unittest

from app.config import Config
from app.core import token_manager
from app.core.token_manager import TokenManager
from app.kimi.client import Kimi2API


class KimiBaseUrlTest(unittest.TestCase):
    def setUp(self):
        self.previous_base_url = Config.KIMI_API_BASE
        self.previous_manager = token_manager._manager
        token_manager._manager = None

    def tearDown(self):
        current_manager = token_manager._manager
        if current_manager is not None:
            asyncio.run(current_manager.close())
        token_manager._manager = self.previous_manager
        Config.KIMI_API_BASE = self.previous_base_url

    def test_token_manager_uses_runtime_config_base_url_by_default(self):
        Config.KIMI_API_BASE = "https://kimi.example.test"
        manager = TokenManager("refresh-token")

        try:
            self.assertEqual(manager._base_url, "https://kimi.example.test")
        finally:
            asyncio.run(manager.close())

    def test_kimi_client_uses_runtime_config_base_url_by_default(self):
        Config.KIMI_API_BASE = "https://kimi.example.test"
        token_manager._manager = TokenManager("refresh-token")
        client = Kimi2API()

        try:
            self.assertEqual(client._base_url, "https://kimi.example.test")
        finally:
            asyncio.run(client.close())


if __name__ == "__main__":
    unittest.main()
