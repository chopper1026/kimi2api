import json
import os
import stat
import base64
import time

import httpx
import pytest

from app.config import Config
from app.kimi.protocol import KimiAPIError


def test_legacy_token_file_migrates_to_private_account_pool(tmp_data_dir, config_override):
    from app.core.kimi_account_store import load_kimi_accounts
    from app.core.kimi_token_store import save_kimi_token

    config_override(KIMI_TOKEN="env-token")
    save_kimi_token("saved-refresh-token")

    accounts = load_kimi_accounts()

    assert len(accounts) == 1
    assert accounts[0].name == "Kimi 1"
    assert accounts[0].raw_token == "saved-refresh-token"
    assert accounts[0].enabled is True
    assert accounts[0].max_concurrency == Config.KIMI_MAX_CONCURRENCY
    assert accounts[0].min_interval_seconds == Config.KIMI_MIN_REQUEST_INTERVAL
    assert accounts[0].device_id.isdigit()

    pool_file = tmp_data_dir / "kimi_accounts.json"
    mode = stat.S_IMODE(os.stat(pool_file).st_mode)
    assert mode == 0o600
    data = json.loads(pool_file.read_text())
    assert data["accounts"][0]["raw_token"] == "saved-refresh-token"


def test_env_token_imports_when_no_saved_account_pool(tmp_data_dir, config_override):
    from app.core.kimi_account_store import load_kimi_accounts

    config_override(KIMI_TOKEN="env-refresh-token")

    accounts = load_kimi_accounts()

    assert len(accounts) == 1
    assert accounts[0].name == "Kimi 1"
    assert accounts[0].raw_token == "env-refresh-token"
    assert (tmp_data_dir / "kimi_accounts.json").exists()


def test_account_access_token_cache_persists_in_private_account_file(
    tmp_data_dir,
    config_override,
):
    from app.core.kimi_account_store import (
        load_kimi_accounts,
        new_kimi_account,
        save_kimi_accounts,
        update_kimi_account_access_cache,
    )

    account = new_kimi_account(
        "refresh-token",
        name="Cached",
        now=1,
    )
    save_kimi_accounts([account])

    cached_access = _jwt_access_token()
    assert update_kimi_account_access_cache(
        account.id,
        cached_access,
        int(time.time()) + 3600,
        expected_raw_token="refresh-token",
    ) is True

    accounts = load_kimi_accounts()
    assert accounts[0].cached_access_token == cached_access
    assert accounts[0].cached_access_expires_at > time.time()
    assert accounts[0].cached_access_updated_at > 0

    pool_file = tmp_data_dir / "kimi_accounts.json"
    mode = stat.S_IMODE(os.stat(pool_file).st_mode)
    assert mode == 0o600


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


@pytest.mark.asyncio
async def test_pool_selects_least_busy_account_and_round_robins(tmp_data_dir):
    from app.core.kimi_account_pool import KimiAccountPool
    from app.core.kimi_account_store import KimiAccountConfig

    accounts = [
        KimiAccountConfig(
            id="acc-a",
            name="A",
            raw_token="token-a",
            enabled=True,
            max_concurrency=1,
            min_interval_seconds=0,
            device_id="1111111111111111111",
            created_at=1,
            updated_at=1,
        ),
        KimiAccountConfig(
            id="acc-b",
            name="B",
            raw_token="token-b",
            enabled=True,
            max_concurrency=1,
            min_interval_seconds=0,
            device_id="2222222222222222222",
            created_at=1,
            updated_at=1,
        ),
    ]
    pool = KimiAccountPool(accounts, base_url="https://kimi.example.test")

    try:
        async with pool.acquire() as first:
            async with pool.acquire() as second:
                assert {first.account_id, second.account_id} == {"acc-a", "acc-b"}

        async with pool.acquire() as third:
            third_id = third.account_id
        async with pool.acquire() as fourth:
            fourth_id = fourth.account_id

        assert [third_id, fourth_id] == ["acc-a", "acc-b"]
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_pool_persists_access_token_cache_after_refresh(
    tmp_data_dir,
    monkeypatch,
):
    from app.core.kimi_account_pool import KimiAccountPool
    from app.core.kimi_account_store import (
        load_kimi_accounts,
        new_kimi_account,
        save_kimi_accounts,
    )

    refreshed_access = _jwt_access_token()
    refresh_calls = []

    class RefreshTransport:
        def __init__(self, *, base_url=None, **_kwargs):
            self.base_url = (base_url or "https://kimi.example.test").rstrip("/")

        async def request(self, method, path_or_url, **_kwargs):
            refresh_calls.append((method, path_or_url))
            return httpx.Response(200, json={"access_token": refreshed_access})

        async def close(self):
            return None

    monkeypatch.setattr(
        "app.core.kimi_account_pool.KimiTransport",
        RefreshTransport,
    )
    account = new_kimi_account(
        "refresh-token",
        name="Cached",
        now=1,
    )
    save_kimi_accounts([account])
    pool = KimiAccountPool(load_kimi_accounts(), base_url="https://kimi.example.test")

    try:
        async with pool.acquire(account_id=account.id) as runtime:
            token = await runtime.token_manager.get_access_token()
    finally:
        await pool.close()

    assert token == refreshed_access
    assert refresh_calls == [("GET", "/api/auth/token/refresh")]
    cached = load_kimi_accounts()[0]
    assert cached.cached_access_token == refreshed_access
    assert cached.cached_access_expires_at == pytest.approx(
        runtime.token_manager.get_state().expires_at,
    )


@pytest.mark.asyncio
async def test_pool_cools_down_failed_account_and_reports_no_available(tmp_data_dir):
    from app.core.kimi_account_pool import KimiAccountPool
    from app.core.kimi_account_store import KimiAccountConfig

    account = KimiAccountConfig(
        id="acc-rate-limited",
        name="Rate Limited",
        raw_token="token-a",
        enabled=True,
        max_concurrency=1,
        min_interval_seconds=0,
        device_id="1111111111111111111",
        created_at=1,
        updated_at=1,
    )
    pool = KimiAccountPool([account], base_url="https://kimi.example.test")

    try:
        async with pool.acquire() as runtime:
            pool.record_failure(
                runtime,
                KimiAPIError(
                    "rate limited",
                    upstream_status_code=429,
                    upstream_error_type="rate_limited",
                    retry_after=60,
                ),
            )

        with pytest.raises(KimiAPIError) as exc_info:
            async with pool.acquire():
                pass

        assert "No available Kimi accounts" in str(exc_info.value)
        info = pool.account_infos()[0]
        assert info["token_healthy"] is False
        assert "冷却" in info["token_status"]
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_pool_can_acquire_unavailable_account_for_admin_recovery(tmp_data_dir):
    from app.core.kimi_account_pool import KimiAccountPool
    from app.core.kimi_account_store import KimiAccountConfig

    account = KimiAccountConfig(
        id="acc-unhealthy",
        name="Unhealthy",
        raw_token="token-a",
        enabled=True,
        max_concurrency=1,
        min_interval_seconds=0,
        device_id="1111111111111111111",
        created_at=1,
        updated_at=1,
    )
    pool = KimiAccountPool([account], base_url="https://kimi.example.test")

    try:
        async with pool.acquire() as runtime:
            pool.record_failure(
                runtime,
                KimiAPIError(
                    "refresh failed",
                    upstream_error_type="token_refresh_failed",
                ),
            )

        with pytest.raises(KimiAPIError):
            async with pool.acquire(account_id="acc-unhealthy"):
                pass

        async with pool.acquire(
            account_id="acc-unhealthy",
            require_selectable=False,
        ) as runtime:
            assert runtime.account_id == "acc-unhealthy"
            pool.record_success(runtime)

        assert pool.account_infos()[0]["token_healthy"] is True
    finally:
        await pool.close()


def test_admin_tokens_api_does_not_leak_full_token(
    authenticated_admin_client,
    tmp_data_dir,
):
    session = authenticated_admin_client.get("/admin/api/session")
    csrf = session.json()["csrf_token"]

    created = authenticated_admin_client.post(
        "/admin/api/tokens",
        json={
            "name": "Work",
            "raw_token": "work-refresh-token-secret",
            "max_concurrency": 3,
            "min_interval_seconds": 0.2,
            "enabled": True,
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert created.status_code == 200
    body = created.json()
    assert body["success"] is True
    account = body["account"]
    assert account["name"] == "Work"
    assert account["max_concurrency"] == 3
    assert account["min_interval_seconds"] == 0.2
    assert "work-refresh-token-secret" not in json.dumps(body)
    assert account["token_preview"] == "wor****ret"
    assert account["token_type"] == "refresh token"

    listing = authenticated_admin_client.get("/admin/api/tokens")
    assert listing.status_code == 200
    data = listing.json()
    assert data["summary"]["total"] == 1
    assert data["summary"]["enabled"] == 1
    assert data["accounts"][0]["name"] == "Work"


def test_admin_tokens_can_update_disable_and_delete(authenticated_admin_client):
    session = authenticated_admin_client.get("/admin/api/session")
    csrf = session.json()["csrf_token"]

    created = authenticated_admin_client.post(
        "/admin/api/tokens",
        json={"name": "Temporary", "raw_token": "temp-token"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    account_id = created["account"]["id"]

    updated = authenticated_admin_client.patch(
        f"/admin/api/tokens/{account_id}",
        json={"name": "Disabled", "enabled": False, "max_concurrency": 4},
        headers={"X-CSRF-Token": csrf},
    )

    assert updated.status_code == 200
    assert updated.json()["account"]["name"] == "Disabled"
    assert updated.json()["account"]["enabled"] is False
    assert updated.json()["account"]["max_concurrency"] == 4

    deleted = authenticated_admin_client.delete(
        f"/admin/api/tokens/{account_id}",
        headers={"X-CSRF-Token": csrf},
    )

    assert deleted.status_code == 200
    assert deleted.json()["success"] is True
    assert deleted.json()["summary"]["total"] == 0


def test_admin_refresh_jwt_account_does_not_mark_account_unhealthy(
    authenticated_admin_client,
):
    session = authenticated_admin_client.get("/admin/api/session")
    csrf = session.json()["csrf_token"]

    created = authenticated_admin_client.post(
        "/admin/api/tokens",
        json={"name": "Access Only", "raw_token": _jwt_access_token()},
        headers={"X-CSRF-Token": csrf},
    ).json()
    account_id = created["account"]["id"]

    response = authenticated_admin_client.post(
        f"/admin/api/tokens/{account_id}/refresh",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert "refresh token" in body["error"]
    assert body["account"]["name"] == "Access Only"
    assert body["account"]["token_type"] == "access token"
    assert body["account"]["token_healthy"] is True
    assert body["summary"]["healthy"] == 1

    listing = authenticated_admin_client.get("/admin/api/tokens").json()
    assert listing["accounts"][0]["token_healthy"] is True
