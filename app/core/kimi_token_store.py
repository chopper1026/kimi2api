import logging
import os
import time
from typing import Optional

from ..config import Config
from .storage import atomic_write_json, data_path, read_json

logger = logging.getLogger("kimi2api.kimi_token_store")

TOKEN_FILE_NAME = "kimi_token.json"


def _token_file() -> str:
    return data_path(TOKEN_FILE_NAME)


def _normalize_token(raw_token: str) -> str:
    return raw_token.strip()


def load_saved_kimi_token() -> Optional[str]:
    token_file = _token_file()
    if not os.path.exists(token_file):
        return None

    try:
        data = read_json(token_file)
    except Exception as exc:
        logger.warning("Failed to load Kimi token file: %s", exc)
        return None

    if not isinstance(data, dict):
        logger.warning("Failed to load Kimi token file: invalid format")
        return None

    token = _normalize_token(str(data.get("token") or ""))
    return token or None


def load_configured_kimi_token() -> Optional[str]:
    saved_token = load_saved_kimi_token()
    if saved_token:
        return saved_token

    env_token = _normalize_token(Config.KIMI_TOKEN)
    return env_token or None


def save_kimi_token(raw_token: str) -> None:
    token = _normalize_token(raw_token)
    if not token:
        raise ValueError("Kimi token must not be empty")

    token_file = _token_file()
    atomic_write_json(
        token_file,
        {
            "token": token,
            "updated_at": time.time(),
        },
        mode=0o600,
    )
