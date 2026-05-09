import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..core.keys import list_keys, total_request_count
from ..core.logs import get_recent_logs
from ..core.token_manager import get_token_manager

_START_TIME: float = 0.0


def set_start_time(t: float) -> None:
    global _START_TIME
    _START_TIME = t


def fmt_time(ts: float) -> str:
    if ts == 0:
        return "-"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def fmt_duration(seconds: float) -> str:
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    if days > 0:
        return f"{days}天 {hours}小时"
    minutes = int((seconds % 3600) // 60)
    return f"{hours}小时 {minutes}分钟"


def token_info() -> Dict[str, Any]:
    try:
        mgr = get_token_manager()
    except RuntimeError:
        return {
            "token_type": "未配置",
            "token_expires": "-",
            "token_preview": "-",
            "token_healthy": False,
            "token_status": "未配置",
        }

    state = mgr.get_state()
    now = time.time()

    if state.expires_at > 0:
        remaining = state.expires_at - now
        expires_str = fmt_time(state.expires_at)
        healthy = remaining > 300
        if remaining > 0:
            if remaining > 86400:
                token_status = f"{int(remaining // 86400)}天后过期"
            elif remaining > 3600:
                token_status = f"{int(remaining // 3600)}小时后过期"
            else:
                token_status = f"{int(remaining // 60)}分钟后过期"
        else:
            token_status = "已过期"
            healthy = False
    else:
        expires_str = "未知"
        token_status = "有效"
        healthy = True

    token = state.access_token
    if len(token) > 4:
        preview = token[:4] + "****"
    else:
        preview = "****"

    return {
        "token_type": state.token_type.upper(),
        "token_expires": expires_str,
        "token_preview": preview,
        "token_healthy": healthy,
        "token_status": token_status,
    }


def key_list() -> List[Dict[str, Any]]:
    result = []
    for k in list_keys():
        result.append({
            "key": k.key,
            "key_preview": k.key[:10] + "..." + k.key[-4:],
            "name": k.name,
            "created_at_str": fmt_time(k.created_at),
            "last_used_str": fmt_time(k.last_used) if k.last_used > 0 else "从未使用",
            "request_count": k.request_count,
        })
    return result


def log_list() -> List[Dict[str, Any]]:
    result = []
    for log in get_recent_logs(200):
        result.append({
            "time_str": datetime.fromtimestamp(
                log.timestamp,
                tz=timezone.utc,
            ).strftime("%m-%d %H:%M:%S"),
            "api_key_name": log.api_key_name,
            "model": log.model,
            "status": log.status,
            "status_code": log.status_code,
            "duration_ms": log.duration_ms,
            "is_stream": log.is_stream,
        })
    return result


def dashboard_stats() -> Dict[str, Any]:
    ti = token_info()
    keys = list_keys()
    return {
        "uptime": fmt_duration(time.time() - _START_TIME),
        "token_healthy": ti["token_healthy"],
        "token_status": ti["token_status"],
        "token_type": ti["token_type"],
        "token_expires": ti["token_expires"],
        "key_count": len(keys),
        "total_requests": total_request_count(),
        "log_count": len(get_recent_logs(200)),
    }
