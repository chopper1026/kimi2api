import asyncio

import httpx
import pytest

from app.kimi.protocol import generate_device_id


def test_client_identity_persists_device_id(tmp_data_dir):
    from app.kimi.transport import load_or_create_client_identity

    first = load_or_create_client_identity()
    second = load_or_create_client_identity()

    assert first.device_id == second.device_id
    assert first.device_id.isdigit()
    assert (tmp_data_dir / "kimi_client_identity.json").exists()


def test_kimi_headers_use_runtime_config(config_override):
    from app.kimi.transport import build_kimi_headers

    config_override(
        TIMEZONE="UTC",
        KIMI_ACCEPT_LANGUAGE="en-US,en;q=0.9",
    )

    headers = build_kimi_headers(
        base_url="https://kimi.example.test",
        token="access-token",
        device_id="device-1",
        session_id="session-1",
        extra={"Content-Type": "application/connect+json"},
    )

    assert headers["Origin"] == "https://kimi.example.test"
    assert headers["R-Timezone"] == "UTC"
    assert headers["Accept-Language"] == "en-US,en;q=0.9"
    assert headers["Authorization"] == "Bearer access-token"
    assert headers["X-Msh-Device-Id"] == "device-1"
    assert headers["X-Msh-Session-Id"] == "session-1"
    assert headers["Content-Type"] == "application/connect+json"


@pytest.mark.asyncio
async def test_transport_retries_429_after_retry_after(monkeypatch):
    from app.kimi import transport as transport_module
    from app.kimi.transport import KimiRateLimiter, KimiTransport

    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(transport_module.asyncio, "sleep", fake_sleep)
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "1.5"})
        return httpx.Response(200, json={"ok": True})

    transport = KimiTransport(
        base_url="https://kimi.example.test",
        max_retries=2,
        http_transport=httpx.MockTransport(handler),
        rate_limiter=KimiRateLimiter(max_concurrency=10, min_interval_seconds=0),
    )
    try:
        response = await transport.request("GET", "/api/test", headers={})
    finally:
        await transport.close()

    assert response.status_code == 200
    assert calls == 2
    assert sleeps == [1.5]


def test_shared_transport_reuses_connection_pool(config_override):
    from app.kimi.transport import close_shared_transports, get_shared_transport

    config_override(KIMI_API_BASE="https://kimi.example.test", TIMEOUT=30)

    first = get_shared_transport()
    second = get_shared_transport()

    try:
        assert first is second
        assert first.is_closed is False
    finally:
        asyncio.run(close_shared_transports())


def test_kimi_client_uses_shared_transport(
    tmp_data_dir,
    token_manager_store,
):
    from app.core.token_manager import TokenManager
    from app.kimi.client import Kimi2API
    from app.kimi.transport import close_shared_transports

    token_manager_store.set(TokenManager("refresh-token"))
    first = Kimi2API()
    second = Kimi2API()

    try:
        assert first._transport is second._transport
        asyncio.run(first.close())
        assert second._transport.is_closed is False
    finally:
        asyncio.run(second.close())
        asyncio.run(close_shared_transports())


def test_generate_device_id_remains_numeric_range():
    device_id = generate_device_id()

    assert device_id.isdigit()
    assert len(device_id) == 19
