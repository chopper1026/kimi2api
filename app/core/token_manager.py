import asyncio
import logging
import time
from dataclasses import dataclass, replace
from typing import Optional

import httpx

from ..config import Config
from ..kimi.protocol import FAKE_HEADERS, detect_token_type, parse_jwt

logger = logging.getLogger("kimi2api.token_manager")

KIMI_REFRESH_PATH = "/api/auth/token/refresh"
REFRESH_BUFFER_SECONDS = 300


@dataclass
class TokenState:
    access_token: str
    refresh_token: Optional[str]
    expires_at: float
    token_type: str


class TokenManager:
    def __init__(self, raw_token: str, base_url: Optional[str] = None):
        self._base_url = (base_url or Config.KIMI_API_BASE).rstrip("/")
        self._lock = asyncio.Lock()
        self._http = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        self._state = self._initialize(raw_token)

    def _initialize(self, raw_token: str) -> TokenState:
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
                await self._do_refresh()
            return self._state.access_token

    def get_state(self) -> TokenState:
        return replace(self._state)

    async def _do_refresh(self) -> None:
        refresh_token = self._state.refresh_token
        if not refresh_token:
            logger.warning("No refresh token available, skipping refresh")
            return
        try:
            headers = {
                **FAKE_HEADERS,
                "Origin": self._base_url,
                "Authorization": f"Bearer {refresh_token}",
            }
            response = await self._http.get(
                f"{self._base_url}{KIMI_REFRESH_PATH}",
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
                    return
            logger.warning(
                "Token refresh failed with status %d: %s",
                response.status_code,
                response.text[:200],
            )
        except Exception as exc:
            logger.warning("Token refresh error: %s", exc)

    async def invalidate_and_retry(self) -> str:
        async with self._lock:
            await self._do_refresh()
            return self._state.access_token

    async def close(self) -> None:
        await self._http.aclose()


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


def get_token_manager() -> TokenManager:
    if _manager is None:
        raise RuntimeError(
            "TokenManager not initialized. Call init_token_manager() first."
        )
    return _manager
