import asyncio
import random
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, AsyncIterator, Dict, Optional, Tuple

import httpx

from ..config import Config
from ..core.storage import atomic_write_json, data_path, read_json
from .protocol import FAKE_HEADERS, generate_device_id, generate_session_id

IDENTITY_FILE_NAME = "kimi_client_identity.json"
RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504]
_shared_transports: Dict[Tuple[str, float, int], "KimiTransport"] = {}


@dataclass(frozen=True)
class KimiClientIdentity:
    device_id: str
    created_at: float


class KimiRateLimiter:
    def __init__(self, max_concurrency: int, min_interval_seconds: float):
        self._semaphore = asyncio.Semaphore(max(int(max_concurrency), 1))
        self._min_interval_seconds = max(float(min_interval_seconds), 0.0)
        self._lock = asyncio.Lock()
        self._next_request_at = 0.0

    async def _wait_for_turn(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = max(self._next_request_at - now, 0.0)
            if delay > 0:
                await asyncio.sleep(delay)
                now = time.monotonic()
            self._next_request_at = max(now, self._next_request_at) + self._min_interval_seconds

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        await self._semaphore.acquire()
        try:
            await self._wait_for_turn()
            yield
        finally:
            self._semaphore.release()


_rate_limiter: Optional[KimiRateLimiter] = None
_rate_limiter_settings: Optional[Tuple[int, float]] = None
_process_session_id = generate_session_id()


def process_session_id() -> str:
    return _process_session_id


def get_rate_limiter() -> KimiRateLimiter:
    global _rate_limiter, _rate_limiter_settings

    settings = (
        max(int(Config.KIMI_MAX_CONCURRENCY), 1),
        max(float(Config.KIMI_MIN_REQUEST_INTERVAL), 0.0),
    )
    if _rate_limiter is None or _rate_limiter_settings != settings:
        _rate_limiter = KimiRateLimiter(*settings)
        _rate_limiter_settings = settings
    return _rate_limiter


def _identity_file() -> str:
    return data_path(IDENTITY_FILE_NAME)


def _is_valid_device_id(value: Any) -> bool:
    return isinstance(value, str) and value.isdigit() and len(value) >= 16


def _new_identity() -> KimiClientIdentity:
    return KimiClientIdentity(
        device_id=generate_device_id(),
        created_at=time.time(),
    )


def load_or_create_client_identity() -> KimiClientIdentity:
    path = _identity_file()
    try:
        data = read_json(path)
        if isinstance(data, dict) and _is_valid_device_id(data.get("device_id")):
            return KimiClientIdentity(
                device_id=str(data["device_id"]),
                created_at=float(data.get("created_at") or 0.0),
            )
    except FileNotFoundError:
        pass
    except Exception:
        pass

    identity = _new_identity()
    atomic_write_json(path, asdict(identity), mode=0o600)
    return identity


def build_kimi_headers(
    *,
    base_url: str,
    token: Optional[str] = None,
    device_id: Optional[str] = None,
    session_id: Optional[str] = None,
    extra: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    headers = {
        **FAKE_HEADERS,
        "Accept-Language": Config.KIMI_ACCEPT_LANGUAGE,
        "Origin": base_url.rstrip("/"),
        "R-Timezone": Config.TIMEZONE,
        "X-Msh-Platform": "web",
    }
    if device_id:
        headers["X-Msh-Device-Id"] = device_id
    if session_id:
        headers["X-Msh-Session-Id"] = session_id
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra:
        headers.update(extra)
    return headers


def retry_after_seconds(headers: httpx.Headers) -> Optional[float]:
    value = headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0.0)
    except Exception:
        return None


def retry_backoff_seconds(attempt: int) -> float:
    return min(0.5 * attempt, 2.0) + random.uniform(0.0, 0.2)


def classify_upstream_status(status_code: int) -> str:
    if status_code == 401:
        return "unauthorized"
    if status_code == 403:
        return "forbidden"
    if status_code == 429:
        return "rate_limited"
    if 500 <= status_code <= 599:
        return "server_error"
    if status_code > 0:
        return "upstream_error"
    return ""


class KimiTransport:
    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 3,
        http_transport: Optional[httpx.AsyncBaseTransport] = None,
        rate_limiter: Optional[KimiRateLimiter] = None,
    ):
        self.base_url = (base_url or Config.KIMI_API_BASE).rstrip("/")
        self.timeout = timeout or Config.TIMEOUT
        self.max_retries = max(int(max_retries), 1)
        self._rate_limiter = rate_limiter or get_rate_limiter()
        self._closed = False
        client_kwargs: Dict[str, Any] = {
            "timeout": httpx.Timeout(self.timeout),
            "follow_redirects": True,
        }
        if http_transport is not None:
            client_kwargs["transport"] = http_transport
        self._client = httpx.AsyncClient(**client_kwargs)

    def _url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        return f"{self.base_url}{path_or_url}"

    @property
    def is_closed(self) -> bool:
        return self._closed or self._client.is_closed

    async def request(
        self,
        method: str,
        path_or_url: str,
        *,
        retryable_status_codes: Optional[list] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        retryable_status_codes = retryable_status_codes or RETRYABLE_STATUS_CODES
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                async with self._rate_limiter.slot():
                    response = await self._client.request(
                        method,
                        self._url(path_or_url),
                        **kwargs,
                    )
                if response.status_code not in retryable_status_codes:
                    return response
                if attempt == self.max_retries:
                    return response
                await response.aread()
                delay = retry_after_seconds(response.headers)
                if delay is None:
                    delay = retry_backoff_seconds(attempt)
                await asyncio.sleep(delay)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                await asyncio.sleep(retry_backoff_seconds(attempt))

        if last_error is None:
            raise RuntimeError("Kimi request failed without a detailed error")
        raise last_error

    @asynccontextmanager
    async def stream(
        self,
        method: str,
        path_or_url: str,
        **kwargs: Any,
    ) -> AsyncIterator[httpx.Response]:
        async with self._rate_limiter.slot():
            async with self._client.stream(
                method,
                self._url(path_or_url),
                **kwargs,
            ) as response:
                yield response

    async def close(self) -> None:
        if self.is_closed:
            return
        await self._client.aclose()
        self._closed = True

    async def __aenter__(self) -> "KimiTransport":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


def get_shared_transport(
    *,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
    max_retries: int = 3,
) -> KimiTransport:
    resolved_base_url = (base_url or Config.KIMI_API_BASE).rstrip("/")
    resolved_timeout = float(timeout or Config.TIMEOUT)
    resolved_retries = max(int(max_retries), 1)
    key = (resolved_base_url, resolved_timeout, resolved_retries)
    transport = _shared_transports.get(key)
    if transport is None or transport.is_closed:
        transport = KimiTransport(
            base_url=resolved_base_url,
            timeout=resolved_timeout,
            max_retries=resolved_retries,
        )
        _shared_transports[key] = transport
    return transport


async def close_shared_transports() -> None:
    transports = list(_shared_transports.values())
    _shared_transports.clear()
    for transport in transports:
        await transport.close()
