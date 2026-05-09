import hmac
import logging
import os
import time
from typing import Dict, Optional, Tuple

from fastapi import Request, Response
from itsdangerous import SignatureExpired, URLSafeTimedSerializer

from ..config import Config
from .storage import atomic_write_text, data_path, ensure_data_dir, read_text

logger = logging.getLogger("kimi2api.auth")

COOKIE_NAME = "kimi2api_session"
MAX_AGE = 86400  # 24 hours
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW = 900  # 15 minutes

_admin_password: Optional[str] = None
_serializer: Optional[URLSafeTimedSerializer] = None
_login_attempts: Dict[str, Tuple[int, float]] = {}


def _get_or_create_session_secret() -> str:
    if Config.SESSION_SECRET:
        return Config.SESSION_SECRET

    secret_file = data_path(".session_secret")
    ensure_data_dir()

    if os.path.exists(secret_file):
        secret = read_text(secret_file).strip()
        if secret:
            return secret

    secret = os.urandom(32).hex()
    atomic_write_text(secret_file, secret, mode=0o600)
    return secret


def init_auth() -> None:
    global _admin_password, _serializer
    _admin_password = Config.ADMIN_PASSWORD
    secret = _get_or_create_session_secret()
    _serializer = URLSafeTimedSerializer(secret)
    if not _admin_password:
        logger.warning("ADMIN_PASSWORD not set, dashboard will be disabled")
    else:
        logger.info("Admin auth initialized")


def is_dashboard_enabled() -> bool:
    return bool(_admin_password)


def _get_serializer() -> URLSafeTimedSerializer:
    if _serializer is None:
        raise RuntimeError("Auth not initialized. Call init_auth() first.")
    return _serializer


def create_session(response: Response) -> Response:
    s = _get_serializer()
    csrf_token = os.urandom(16).hex()
    token = s.dumps({"role": "admin", "csrf": csrf_token})
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=MAX_AGE,
        httponly=True,
        secure=Config.SECURE_COOKIES,
        samesite="lax",
    )
    return response


def get_csrf_token(request: Request) -> Optional[str]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        s = _get_serializer()
        data = s.loads(token, max_age=MAX_AGE)
        if isinstance(data, dict) and data.get("role") == "admin":
            return data.get("csrf")
    except Exception:
        pass
    return None


def verify_csrf(request: Request) -> bool:
    expected = get_csrf_token(request)
    if not expected:
        return False
    provided = request.headers.get("x-csrf-token") or ""
    if not provided:
        return False
    return hmac.compare_digest(expected, provided)


def verify_session(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    try:
        s = _get_serializer()
        data = s.loads(token, max_age=MAX_AGE)
        return isinstance(data, dict) and data.get("role") == "admin"
    except SignatureExpired:
        return False
    except Exception:
        return False


def destroy_session(response: Response) -> Response:
    response.delete_cookie(COOKIE_NAME)
    return response


def check_login_rate_limit(client_ip: str) -> bool:
    now = time.time()
    count, window_start = _login_attempts.get(client_ip, (0, now))
    if now - window_start > LOGIN_WINDOW:
        _login_attempts[client_ip] = (0, now)
        return True
    if count >= LOGIN_MAX_ATTEMPTS:
        return False
    return True


def record_failed_login(client_ip: str) -> None:
    now = time.time()
    count, window_start = _login_attempts.get(client_ip, (0, now))
    _login_attempts[client_ip] = (count + 1, window_start)


def clear_login_rate_limit(client_ip: str) -> None:
    _login_attempts.pop(client_ip, None)


def verify_password(password: str) -> bool:
    if not _admin_password:
        return False
    return hmac.compare_digest(password, _admin_password)
