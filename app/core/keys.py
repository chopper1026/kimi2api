import json
import logging
import os
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import List, Optional

from ..config import Config

logger = logging.getLogger("kimi2api.keys")


@dataclass
class ApiKey:
    key: str
    name: str
    created_at: float
    last_used: float = 0.0
    request_count: int = 0


_key_store: OrderedDict[str, ApiKey] = OrderedDict()


def _key_file() -> str:
    return os.path.join(Config.DATA_DIR, "api_keys.json")


def _ensure_data_dir() -> None:
    os.makedirs(Config.DATA_DIR, exist_ok=True)


def _load_keys_from_file() -> None:
    kf = _key_file()
    if not os.path.exists(kf):
        return
    try:
        with open(kf, "r", encoding="utf-8") as f:
            items = json.load(f)
        for item in items:
            k = ApiKey(**item)
            _key_store[k.key] = k
        logger.info("Loaded %d keys from %s", len(items), kf)
    except Exception as exc:
        logger.warning("Failed to load keys file: %s", exc)


def _save_keys_to_file() -> None:
    _ensure_data_dir()
    kf = _key_file()
    items = [asdict(k) for k in _key_store.values()]
    tmp = kf + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, kf)


def init_key_store() -> None:
    _ensure_data_dir()
    env_key = Config.OPENAI_API_KEY
    if env_key:
        existing = _key_store.get(env_key)
        if not existing:
            _key_store[env_key] = ApiKey(
                key=env_key,
                name="Default (env)",
                created_at=time.time(),
            )
            logger.info("Migrated OPENAI_API_KEY into key store")
    _load_keys_from_file()
    if env_key and env_key not in _key_store:
        _key_store[env_key] = ApiKey(
            key=env_key,
            name="Default (env)",
            created_at=time.time(),
        )
    logger.info("Key store initialized with %d keys", len(_key_store))


def list_keys() -> List[ApiKey]:
    return list(_key_store.values())


def get_key(key: str) -> Optional[ApiKey]:
    return _key_store.get(key)


def create_key(name: Optional[str] = None) -> ApiKey:
    raw = os.urandom(16).hex()
    key_str = f"sk-{raw}"
    if not name:
        name = f"Key {len(_key_store) + 1}"
    name = name.strip()[:64]
    api_key = ApiKey(
        key=key_str,
        name=name,
        created_at=time.time(),
    )
    _key_store[key_str] = api_key
    _save_keys_to_file()
    logger.info("Created API key: %s", name)
    return api_key


def delete_key(key: str) -> bool:
    if key in _key_store:
        del _key_store[key]
        _save_keys_to_file()
        logger.info("Deleted API key: %s...%s", key[:6], key[-4:])
        return True
    return False


def touch_key(key: str) -> None:
    k = _key_store.get(key)
    if k:
        k.last_used = time.time()
        k.request_count += 1


def validate_api_key(authorization: Optional[str]) -> Optional[ApiKey]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    k = _key_store.get(token)
    if k:
        touch_key(token)
    return k


def total_request_count() -> int:
    return sum(k.request_count for k in _key_store.values())


def total_key_count() -> int:
    return len(_key_store)
