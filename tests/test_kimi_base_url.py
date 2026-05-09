import asyncio

from app.core.token_manager import TokenManager
from app.kimi.client import Kimi2API


def test_token_manager_uses_runtime_config_base_url_by_default(config_override):
    config_override(KIMI_API_BASE="https://kimi.example.test")
    manager = TokenManager("refresh-token")

    try:
        assert manager._base_url == "https://kimi.example.test"
    finally:
        asyncio.run(manager.close())


def test_kimi_client_uses_runtime_config_base_url_by_default(
    config_override,
    token_manager_store,
):
    config_override(KIMI_API_BASE="https://kimi.example.test")
    token_manager_store.set(TokenManager("refresh-token"))
    client = Kimi2API()

    try:
        assert client._base_url == "https://kimi.example.test"
    finally:
        asyncio.run(client.close())
