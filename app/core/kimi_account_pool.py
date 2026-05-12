import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional, Set

from ..config import Config
from ..kimi.protocol import KimiAPIError
from ..kimi.transport import KimiRateLimiter, KimiTransport, process_session_id
from .kimi_account_store import (
    KimiAccountConfig,
    load_kimi_accounts,
    update_kimi_account_access_cache,
)
from .token_display import token_preview, token_type_label
from .token_manager import TokenManager

DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 60.0
DEFAULT_TRANSIENT_COOLDOWN_SECONDS = 30.0


@dataclass
class KimiAccountRuntime:
    account: KimiAccountConfig
    token_manager: TokenManager
    transport: KimiTransport
    session_id: str
    in_flight: int = 0
    cooldown_until: float = 0.0
    unhealthy_error: str = ""

    @property
    def account_id(self) -> str:
        return self.account.id

    @property
    def account_name(self) -> str:
        return self.account.name

    @property
    def enabled(self) -> bool:
        return self.account.enabled

    def is_cooling_down(self, now: Optional[float] = None) -> bool:
        return self.cooldown_until > (now if now is not None else time.time())

    def has_capacity(self) -> bool:
        return self.in_flight < self.account.max_concurrency

    def is_selectable(self, now: Optional[float] = None) -> bool:
        return (
            self.enabled
            and not self.unhealthy_error
            and not self.is_cooling_down(now)
            and self.has_capacity()
        )

    async def close(self) -> None:
        await self.transport.close()


class KimiAccountPool:
    def __init__(
        self,
        accounts: List[KimiAccountConfig],
        *,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 3,
    ):
        self._base_url = (base_url or Config.KIMI_API_BASE).rstrip("/")
        self._timeout = timeout or Config.TIMEOUT
        self._max_retries = max(int(max_retries), 1)
        self._selection_lock = asyncio.Lock()
        self._rr_cursor = 0
        self._runtimes: List[KimiAccountRuntime] = [
            self._build_runtime(account)
            for account in accounts
        ]

    def _build_runtime(self, account: KimiAccountConfig) -> KimiAccountRuntime:
        rate_limiter = KimiRateLimiter(
            max_concurrency=account.max_concurrency,
            min_interval_seconds=account.min_interval_seconds,
        )
        transport = KimiTransport(
            base_url=self._base_url,
            timeout=self._timeout,
            max_retries=self._max_retries,
            rate_limiter=rate_limiter,
        )
        token_manager = TokenManager(
            account.raw_token,
            base_url=self._base_url,
            cached_access_token=account.cached_access_token,
            cached_access_expires_at=account.cached_access_expires_at,
            device_id=account.device_id,
            session_id=process_session_id(),
            transport=transport,
            on_token_refreshed=lambda state, account=account: update_kimi_account_access_cache(
                account.id,
                state.access_token,
                state.expires_at,
                expected_raw_token=account.raw_token,
            ),
        )
        return KimiAccountRuntime(
            account=account,
            token_manager=token_manager,
            transport=transport,
            session_id=process_session_id(),
        )

    @property
    def configured(self) -> bool:
        return bool(self._runtimes)

    def account_count(self) -> int:
        return len(self._runtimes)

    def _runtime_by_id(self, account_id: str) -> Optional[KimiAccountRuntime]:
        return next((runtime for runtime in self._runtimes if runtime.account_id == account_id), None)

    def _available_runtimes(
        self,
        *,
        exclude: Optional[Set[str]] = None,
        now: Optional[float] = None,
    ) -> List[KimiAccountRuntime]:
        excluded = exclude or set()
        current = time.time() if now is None else now
        return [
            runtime
            for runtime in self._runtimes
            if runtime.account_id not in excluded and runtime.is_selectable(current)
        ]

    async def _select_runtime(
        self,
        *,
        account_id: Optional[str] = None,
        exclude: Optional[Set[str]] = None,
        require_selectable: bool = True,
    ) -> KimiAccountRuntime:
        async with self._selection_lock:
            if account_id:
                runtime = self._runtime_by_id(account_id)
                if runtime is None:
                    raise KimiAPIError(
                        f"Kimi account `{account_id}` was not found",
                        upstream_error_type="no_available_account",
                    )
                if require_selectable and not runtime.is_selectable():
                    raise KimiAPIError(
                        f"Kimi account `{runtime.account_name}` is not available",
                        upstream_error_type="no_available_account",
                    )
                runtime.in_flight += 1
                return runtime

            candidates = self._available_runtimes(exclude=exclude)
            if not candidates:
                raise KimiAPIError(
                    "No available Kimi accounts",
                    upstream_error_type="no_available_account",
                )

            min_in_flight = min(runtime.in_flight for runtime in candidates)
            ordered = self._runtimes[self._rr_cursor:] + self._runtimes[:self._rr_cursor]
            tied_ids = {
                runtime.account_id
                for runtime in candidates
                if runtime.in_flight == min_in_flight
            }
            selected = next(runtime for runtime in ordered if runtime.account_id in tied_ids)
            selected.in_flight += 1
            selected_index = self._runtimes.index(selected)
            self._rr_cursor = (selected_index + 1) % max(len(self._runtimes), 1)
            return selected

    @asynccontextmanager
    async def acquire(
        self,
        *,
        account_id: Optional[str] = None,
        exclude: Optional[Set[str]] = None,
        require_selectable: bool = True,
    ) -> AsyncIterator[KimiAccountRuntime]:
        runtime = await self._select_runtime(
            account_id=account_id,
            exclude=exclude,
            require_selectable=require_selectable,
        )
        try:
            yield runtime
        finally:
            async with self._selection_lock:
                runtime.in_flight = max(runtime.in_flight - 1, 0)

    def record_success(self, runtime: KimiAccountRuntime) -> None:
        runtime.cooldown_until = 0.0
        runtime.unhealthy_error = ""

    def record_failure(self, runtime: KimiAccountRuntime, exc: Exception) -> None:
        now = time.time()
        if isinstance(exc, KimiAPIError):
            error_type = exc.upstream_error_type
            status_code = int(exc.upstream_status_code or 0)
            if error_type == "token_refresh_failed" or status_code in {401, 403}:
                runtime.unhealthy_error = str(exc)
                runtime.cooldown_until = 0.0
                return
            if status_code == 429 or error_type == "rate_limited":
                runtime.cooldown_until = now + (
                    exc.retry_after
                    if exc.retry_after is not None
                    else DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS
                )
                return
            if 500 <= status_code <= 599 or error_type in {
                "server_error",
                "network_error",
                "stream_interrupted",
            }:
                runtime.cooldown_until = now + DEFAULT_TRANSIENT_COOLDOWN_SECONDS
                return
        runtime.cooldown_until = now + DEFAULT_TRANSIENT_COOLDOWN_SECONDS

    def account_infos(self) -> List[Dict[str, Any]]:
        return [_account_info(runtime) for runtime in self._runtimes]

    def summary(self) -> Dict[str, int]:
        infos = self.account_infos()
        return {
            "total": len(infos),
            "enabled": sum(1 for item in infos if item["enabled"]),
            "healthy": sum(1 for item in infos if item["token_healthy"]),
            "unhealthy": sum(1 for item in infos if not item["token_healthy"]),
            "in_flight": sum(int(item["in_flight"]) for item in infos),
        }

    async def close(self) -> None:
        for runtime in self._runtimes:
            await runtime.close()


def _account_info(runtime: KimiAccountRuntime) -> Dict[str, Any]:
    state = runtime.token_manager.get_state()
    now = time.time()
    healthy = runtime.enabled and not runtime.unhealthy_error

    if runtime.is_cooling_down(now):
        remaining = max(runtime.cooldown_until - now, 0.0)
        token_status = f"冷却中 {int(remaining)}s"
        healthy = False
    elif runtime.unhealthy_error:
        token_status = "异常，需刷新或验证"
        healthy = False
    elif not runtime.enabled:
        token_status = "已禁用"
        healthy = False
    elif state.expires_at > 0:
        remaining = state.expires_at - now
        healthy = healthy and remaining > 300
        if remaining > 86400:
            token_status = f"{int(remaining // 86400)}天后过期"
        elif remaining > 3600:
            token_status = f"{int(remaining // 3600)}小时后过期"
        elif remaining > 0:
            token_status = f"{int(remaining // 60)}分钟后过期"
        else:
            token_status = "已过期"
            healthy = False
    else:
        token_status = "有效"

    token_expires = "未知"
    if state.expires_at > 0:
        from ..dashboard.view_models import fmt_time

        token_expires = fmt_time(state.expires_at)

    return {
        "id": runtime.account_id,
        "name": runtime.account_name,
        "enabled": runtime.enabled,
        "token_type": token_type_label(state.token_type),
        "token_expires": token_expires,
        "token_preview": token_preview(runtime.account.raw_token),
        "token_healthy": healthy,
        "token_status": token_status,
        "in_flight": runtime.in_flight,
        "max_concurrency": runtime.account.max_concurrency,
        "min_interval_seconds": runtime.account.min_interval_seconds,
    }


_pool: Optional[KimiAccountPool] = None


def init_account_pool(
    accounts: Optional[List[KimiAccountConfig]] = None,
    *,
    base_url: Optional[str] = None,
) -> KimiAccountPool:
    global _pool
    _pool = KimiAccountPool(
        load_kimi_accounts() if accounts is None else accounts,
        base_url=base_url,
    )
    return _pool


async def replace_account_pool(
    accounts: Optional[List[KimiAccountConfig]] = None,
    *,
    base_url: Optional[str] = None,
) -> KimiAccountPool:
    global _pool
    old_pool = _pool
    _pool = KimiAccountPool(
        load_kimi_accounts() if accounts is None else accounts,
        base_url=base_url,
    )
    if old_pool is not None:
        await old_pool.close()
    return _pool


async def close_account_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_account_pool(*, required: bool = True) -> Optional[KimiAccountPool]:
    if _pool is None and required:
        raise RuntimeError("Kimi account pool is not initialized")
    return _pool
