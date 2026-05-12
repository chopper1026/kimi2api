import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, List, Optional

from ..config import Config
from ..kimi.protocol import generate_device_id
from .storage import atomic_write_json, data_path, read_json

logger = logging.getLogger("kimi2api.kimi_account_store")

ACCOUNTS_FILE_NAME = "kimi_accounts.json"
LEGACY_TOKEN_FILE_NAME = "kimi_token.json"


@dataclass(frozen=True)
class KimiAccountConfig:
    id: str
    name: str
    raw_token: str
    enabled: bool
    max_concurrency: int
    min_interval_seconds: float
    device_id: str
    created_at: float
    updated_at: float
    cached_access_token: str = ""
    cached_access_expires_at: float = 0.0
    cached_access_updated_at: float = 0.0


def _accounts_file() -> str:
    return data_path(ACCOUNTS_FILE_NAME)


def kimi_accounts_file_exists() -> bool:
    return os.path.exists(_accounts_file())


def _legacy_token_file() -> str:
    return data_path(LEGACY_TOKEN_FILE_NAME)


def _normalize_token(raw_token: str) -> str:
    return raw_token.strip()


def _default_max_concurrency(value: Any = None) -> int:
    source = Config.KIMI_MAX_CONCURRENCY if value is None else value
    try:
        return max(int(source), 1)
    except (TypeError, ValueError):
        return max(int(Config.KIMI_MAX_CONCURRENCY), 1)


def _default_min_interval(value: Any = None) -> float:
    source = Config.KIMI_MIN_REQUEST_INTERVAL if value is None else value
    try:
        return max(float(source), 0.0)
    except (TypeError, ValueError):
        return max(float(Config.KIMI_MIN_REQUEST_INTERVAL), 0.0)


def _float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _valid_device_id(value: Any) -> bool:
    return isinstance(value, str) and value.isdigit() and len(value) >= 16


def _account_from_dict(data: Dict[str, Any], index: int) -> Optional[KimiAccountConfig]:
    raw_token = _normalize_token(str(data.get("raw_token") or data.get("token") or ""))
    if not raw_token:
        return None

    now = time.time()
    account_id = str(data.get("id") or uuid.uuid4().hex)
    name = str(data.get("name") or f"Kimi {index + 1}").strip() or f"Kimi {index + 1}"
    device_id = str(data.get("device_id") or "")
    if not _valid_device_id(device_id):
        device_id = generate_device_id()

    created_at = data.get("created_at")
    updated_at = data.get("updated_at")
    try:
        created_ts = float(created_at if created_at is not None else now)
    except (TypeError, ValueError):
        created_ts = now
    try:
        updated_ts = float(updated_at if updated_at is not None else created_ts)
    except (TypeError, ValueError):
        updated_ts = created_ts

    return KimiAccountConfig(
        id=account_id,
        name=name,
        raw_token=raw_token,
        enabled=bool(data.get("enabled", True)),
        max_concurrency=_default_max_concurrency(data.get("max_concurrency")),
        min_interval_seconds=_default_min_interval(data.get("min_interval_seconds")),
        device_id=device_id,
        created_at=created_ts,
        updated_at=updated_ts,
        cached_access_token=_normalize_token(str(data.get("cached_access_token") or "")),
        cached_access_expires_at=_float_value(data.get("cached_access_expires_at"), 0.0),
        cached_access_updated_at=_float_value(data.get("cached_access_updated_at"), 0.0),
    )


def new_kimi_account(
    raw_token: str,
    *,
    name: Optional[str] = None,
    enabled: bool = True,
    max_concurrency: Optional[int] = None,
    min_interval_seconds: Optional[float] = None,
    device_id: Optional[str] = None,
    now: Optional[float] = None,
) -> KimiAccountConfig:
    token = _normalize_token(raw_token)
    if not token:
        raise ValueError("Kimi token must not be empty")

    created = float(now if now is not None else time.time())
    resolved_device_id = device_id or generate_device_id()
    if not _valid_device_id(resolved_device_id):
        resolved_device_id = generate_device_id()

    return KimiAccountConfig(
        id=uuid.uuid4().hex,
        name=(name or "Kimi 1").strip() or "Kimi 1",
        raw_token=token,
        enabled=bool(enabled),
        max_concurrency=_default_max_concurrency(max_concurrency),
        min_interval_seconds=_default_min_interval(min_interval_seconds),
        device_id=resolved_device_id,
        created_at=created,
        updated_at=created,
    )


def _read_accounts_file() -> Optional[List[KimiAccountConfig]]:
    path = _accounts_file()
    if not os.path.exists(path):
        return None

    try:
        data = read_json(path)
    except Exception as exc:
        logger.warning("Failed to load Kimi accounts file: %s", exc)
        return []

    raw_accounts = data.get("accounts") if isinstance(data, dict) else data
    if not isinstance(raw_accounts, list):
        logger.warning("Failed to load Kimi accounts file: invalid format")
        return []

    accounts: List[KimiAccountConfig] = []
    for index, item in enumerate(raw_accounts):
        if not isinstance(item, dict):
            continue
        account = _account_from_dict(item, index)
        if account is not None:
            accounts.append(account)
    return accounts


def _load_legacy_token() -> Optional[str]:
    path = _legacy_token_file()
    if not os.path.exists(path):
        return None
    try:
        data = read_json(path)
    except Exception as exc:
        logger.warning("Failed to load legacy Kimi token file: %s", exc)
        return None
    if not isinstance(data, dict):
        return None
    token = _normalize_token(str(data.get("token") or ""))
    return token or None


def _initial_accounts_from_legacy_sources() -> List[KimiAccountConfig]:
    token = _load_legacy_token()
    if token is None:
        token = _normalize_token(Config.KIMI_TOKEN)
    if not token:
        return []
    return [new_kimi_account(token, name="Kimi 1")]


def save_kimi_accounts(accounts: List[KimiAccountConfig]) -> None:
    atomic_write_json(
        _accounts_file(),
        {
            "version": 1,
            "accounts": [asdict(account) for account in accounts],
            "updated_at": time.time(),
        },
        mode=0o600,
    )


def load_kimi_accounts() -> List[KimiAccountConfig]:
    accounts = _read_accounts_file()
    if accounts is not None:
        return accounts

    accounts = _initial_accounts_from_legacy_sources()
    if accounts:
        save_kimi_accounts(accounts)
    return accounts


def get_kimi_account(account_id: str) -> Optional[KimiAccountConfig]:
    return next((account for account in load_kimi_accounts() if account.id == account_id), None)


def add_kimi_account(
    raw_token: str,
    *,
    name: Optional[str] = None,
    enabled: bool = True,
    max_concurrency: Optional[int] = None,
    min_interval_seconds: Optional[float] = None,
) -> KimiAccountConfig:
    accounts = load_kimi_accounts()
    account = new_kimi_account(
        raw_token,
        name=name or f"Kimi {len(accounts) + 1}",
        enabled=enabled,
        max_concurrency=max_concurrency,
        min_interval_seconds=min_interval_seconds,
    )
    accounts.append(account)
    save_kimi_accounts(accounts)
    return account


def update_kimi_account(account_id: str, **changes: Any) -> Optional[KimiAccountConfig]:
    accounts = load_kimi_accounts()
    updated: Optional[KimiAccountConfig] = None
    result: List[KimiAccountConfig] = []
    for account in accounts:
        if account.id != account_id:
            result.append(account)
            continue

        values: Dict[str, Any] = {}
        if "name" in changes:
            name = str(changes["name"] or "").strip()
            if name:
                values["name"] = name
        if "raw_token" in changes:
            raw_token = _normalize_token(str(changes["raw_token"] or ""))
            if raw_token:
                values["raw_token"] = raw_token
                values["cached_access_token"] = ""
                values["cached_access_expires_at"] = 0.0
                values["cached_access_updated_at"] = 0.0
        if "enabled" in changes:
            values["enabled"] = bool(changes["enabled"])
        if "max_concurrency" in changes:
            values["max_concurrency"] = _default_max_concurrency(changes["max_concurrency"])
        if "min_interval_seconds" in changes:
            values["min_interval_seconds"] = _default_min_interval(changes["min_interval_seconds"])
        if "device_id" in changes and _valid_device_id(changes["device_id"]):
            values["device_id"] = str(changes["device_id"])

        updated = replace(account, **values, updated_at=time.time())
        result.append(updated)

    if updated is None:
        return None
    save_kimi_accounts(result)
    return updated


def update_kimi_account_access_cache(
    account_id: str,
    access_token: str,
    expires_at: float,
    *,
    expected_raw_token: Optional[str] = None,
) -> bool:
    token = _normalize_token(access_token)
    if not token:
        return False

    accounts = load_kimi_accounts()
    updated = False
    result: List[KimiAccountConfig] = []
    for account in accounts:
        if account.id != account_id:
            result.append(account)
            continue
        if expected_raw_token is not None and account.raw_token != expected_raw_token:
            result.append(account)
            continue
        result.append(
            replace(
                account,
                cached_access_token=token,
                cached_access_expires_at=_float_value(expires_at, 0.0),
                cached_access_updated_at=time.time(),
            )
        )
        updated = True

    if updated:
        save_kimi_accounts(result)
    return updated


def clear_kimi_account_access_cache(account_id: str) -> bool:
    accounts = load_kimi_accounts()
    updated = False
    result: List[KimiAccountConfig] = []
    for account in accounts:
        if account.id != account_id:
            result.append(account)
            continue
        result.append(
            replace(
                account,
                cached_access_token="",
                cached_access_expires_at=0.0,
                cached_access_updated_at=0.0,
            )
        )
        updated = True

    if updated:
        save_kimi_accounts(result)
    return updated


def delete_kimi_account(account_id: str) -> bool:
    accounts = load_kimi_accounts()
    remaining = [account for account in accounts if account.id != account_id]
    if len(remaining) == len(accounts):
        return False
    save_kimi_accounts(remaining)
    return True
