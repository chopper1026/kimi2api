import json
import logging
import os
import time
from typing import Optional

from ..config import Config

logger = logging.getLogger("kimi2api.kimi_token_store")

TOKEN_FILE_NAME = "kimi_token.json"


def _token_file() -> str:
    return os.path.join(Config.DATA_DIR, TOKEN_FILE_NAME)


def _ensure_data_dir() -> None:
    os.makedirs(Config.DATA_DIR, exist_ok=True)


def _normalize_token(raw_token: str) -> str:
    return raw_token.strip()


def load_saved_kimi_token() -> Optional[str]:
    token_file = _token_file()
    if not os.path.exists(token_file):
        return None

    try:
        with open(token_file, "r", encoding="utf-8") as f:
            data = json.load(f)
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

    _ensure_data_dir()
    token_file = _token_file()
    tmp = token_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(
            {
                "token": token,
                "updated_at": time.time(),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    os.replace(tmp, token_file)
    os.chmod(token_file, 0o600)
