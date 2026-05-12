import asyncio
import logging
import time
from dataclasses import dataclass, replace
from typing import Callable, Optional

from ..config import Config
from ..kimi.protocol import KimiAPIError, detect_token_type, parse_jwt
from ..kimi.transport import (
    build_kimi_headers,
    get_shared_transport,
    load_or_create_client_identity,
    process_session_id,
    retry_after_seconds,
)
from ..kimi.transport import KimiTransport

logger = logging.getLogger("kimi2api.token_manager")

KIMI_REFRESH_PATH = "/api/auth/token/refresh"
REFRESH_BUFFER_SECONDS = 300


@dataclass
class TokenState:
    access_token: str
    refresh_token: Optional[str]
    expires_at: float
    token_type: str


TokenRefreshCallback = Callable[[TokenState], None]


class TokenManager:
    def __init__(
        self,
        raw_token: str,
        base_url: Optional[str] = None,
        *,
        cached_access_token: str = "",
        cached_access_expires_at: float = 0.0,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
        transport: Optional[KimiTransport] = None,
        on_token_refreshed: Optional[TokenRefreshCallback] = None,
    ):
        self._base_url = (base_url or Config.KIMI_API_BASE).rstrip("/")
        self._lock = asyncio.Lock()
        self._transport = transport or get_shared_transport(base_url=self._base_url, timeout=30.0)
        self._device_id = device_id or load_or_create_client_identity().device_id
        self._session_id = session_id or process_session_id()
        self._on_token_refreshed = on_token_refreshed
        self._state = self._initialize(
            raw_token,
            cached_access_token=cached_access_token,
            cached_access_expires_at=cached_access_expires_at,
        )
        self._last_refresh_error: Optional[KimiAPIError] = None

    def _initialize(
        self,
        raw_token: str,
        *,
        cached_access_token: str = "",
        cached_access_expires_at: float = 0.0,
    ) -> TokenState:
        token_type = detect_token_type(raw_token)
        if token_type == "jwt":
            payload = parse_jwt(raw_token)
            expires_at = payload.get("exp", 0.0) if payload else 0.0
            return TokenState(
                access_token=raw_token,
                refresh_token=None,
                expires_at=expires_at,
                token_type="jwt",
            )
        cached_token = cached_access_token.strip()
        if cached_token and detect_token_type(cached_token) == "jwt":
            payload = parse_jwt(cached_token)
            parsed_expires_at = payload.get("exp", 0.0) if payload else 0.0
            try:
                fallback_expires_at = float(cached_access_expires_at or 0.0)
            except (TypeError, ValueError):
                fallback_expires_at = 0.0
            expires_at = float(parsed_expires_at or fallback_expires_at)
            if expires_at > 0:
                return TokenState(
                    access_token=cached_token,
                    refresh_token=raw_token,
                    expires_at=expires_at,
                    token_type="jwt",
                )
        return TokenState(
            access_token=raw_token,
            refresh_token=raw_token,
            expires_at=0.0,
            token_type="refresh",
        )

    def _needs_refresh(self) -> bool:
        if self._state.token_type == "refresh":
            return True
        if self._state.expires_at == 0.0:
            return False
        return time.time() > (self._state.expires_at - REFRESH_BUFFER_SECONDS)

    async def get_access_token(self) -> str:
        async with self._lock:
            if self._needs_refresh():
                refreshed = await self._do_refresh()
                if not refreshed:
                    raise self._refresh_error()
            return self._state.access_token

    def get_state(self) -> TokenState:
        return replace(self._state)

    def _refresh_error(self) -> KimiAPIError:
        return self._last_refresh_error or KimiAPIError(
            "Kimi token refresh failed",
            upstream_error_type="token_refresh_failed",
        )

    async def _do_refresh(self) -> bool:
        refresh_token = self._state.refresh_token
        if not refresh_token:
            logger.warning("No refresh token available, skipping refresh")
            self._last_refresh_error = KimiAPIError(
                "No refresh token available",
                upstream_error_type="token_refresh_failed",
            )
            return False
        try:
            headers = {
                **build_kimi_headers(
                    base_url=self._base_url,
                    token=refresh_token,
                    device_id=self._device_id,
                    session_id=self._session_id,
                ),
            }
            response = await self._transport.request(
                "GET",
                KIMI_REFRESH_PATH,
                headers=headers,
            )
            if response.status_code == 200:
                data = response.json()
                new_access = data.get("access_token") or data.get("token")
                if new_access:
                    payload = parse_jwt(new_access)
                    expires_at = payload.get("exp", 0.0) if payload else 0.0
                    self._state = TokenState(
                        access_token=new_access,
                        refresh_token=refresh_token,
                        expires_at=expires_at,
                        token_type="jwt",
                    )
                    logger.info(
                        "Token refreshed successfully, expires_at=%.0f",
                        expires_at,
                    )
                    self._notify_token_refreshed()
                    self._last_refresh_error = None
                    return True
                self._last_refresh_error = KimiAPIError(
                    "Kimi token refresh response did not include an access token",
                    upstream_status_code=response.status_code,
                    upstream_error_type="token_refresh_failed",
                    retry_after=retry_after_seconds(response.headers),
                )
                logger.warning("Token refresh response did not include an access token")
                return False
            body = response.text[:200]
            self._last_refresh_error = KimiAPIError(
                f"Kimi token refresh failed with status {response.status_code}: "
                f"{body or '<empty>'}",
                upstream_status_code=response.status_code,
                upstream_error_type="token_refresh_failed",
                retry_after=retry_after_seconds(response.headers),
            )
            logger.warning(
                "Token refresh failed with status %d: %s",
                response.status_code,
                body,
            )
            return False
        except Exception as exc:
            if isinstance(exc, KimiAPIError):
                self._last_refresh_error = exc
            else:
                self._last_refresh_error = KimiAPIError(
                    f"Kimi token refresh error: {exc}",
                    upstream_error_type="token_refresh_failed",
                )
            logger.warning("Token refresh error: %s", exc)
            return False

    def _notify_token_refreshed(self) -> None:
        if self._on_token_refreshed is None:
            return
        try:
            self._on_token_refreshed(replace(self._state))
        except Exception as exc:
            logger.warning("Failed to persist refreshed Kimi access token cache: %s", exc)

    async def invalidate_and_retry(self) -> str:
        async with self._lock:
            refreshed = await self._do_refresh()
            if not refreshed:
                raise self._refresh_error()
            return self._state.access_token

    async def close(self) -> None:
        return None


_manager: Optional[TokenManager] = None


def init_token_manager(raw_token: str, base_url: Optional[str] = None) -> TokenManager:
    global _manager
    _manager = TokenManager(raw_token, base_url)
    return _manager


async def replace_token_manager(raw_token: str, base_url: Optional[str] = None) -> TokenManager:
    global _manager
    old_manager = _manager
    _manager = TokenManager(raw_token, base_url)
    if old_manager is not None:
        await old_manager.close()
    return _manager


async def close_token_manager() -> None:
    global _manager
    if _manager is not None:
        await _manager.close()
        _manager = None


def get_token_manager() -> TokenManager:
    if _manager is None:
        raise RuntimeError(
            "TokenManager not initialized. Call init_token_manager() first."
        )
    return _manager
