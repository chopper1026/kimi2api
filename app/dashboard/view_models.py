import time
import shlex
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from ..core.keys import list_keys, total_request_count
from ..core.logs import RequestLog, get_log, get_recent_logs, search_logs
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


def _log_filters(filters: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    source = filters or {}
    return {
        "q": source.get("q", "").strip(),
        "status": source.get("status", "").strip(),
        "model": source.get("model", "").strip(),
        "api_key_name": source.get("api_key_name", "").strip(),
        "path": source.get("path", "").strip(),
        "stream": source.get("stream", "").strip(),
    }


def log_list(filters: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    result = []
    query = _log_filters(filters)
    entries = search_logs(
        q=query["q"],
        status=query["status"],
        model=query["model"],
        api_key_name=query["api_key_name"],
        path=query["path"],
        stream=query["stream"],
        limit=200,
    )
    for log in entries:
        result.append({
            "request_id": log.request_id,
            "request_id_short": log.request_id[:8],
            "time_str": datetime.fromtimestamp(
                log.timestamp,
                tz=timezone.utc,
            ).strftime("%m-%d %H:%M:%S"),
            "api_key_name": log.api_key_name,
            "model": log.model,
            "method": log.method,
            "path": log.path,
            "status": log.status,
            "status_code": log.status_code,
            "duration_ms": log.duration_ms,
            "is_stream": log.is_stream,
            "error_message": log.error_message,
        })
    return result


def _pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _format_body(body: str) -> str:
    if not body:
        return ""
    try:
        return _pretty_json(json.loads(body))
    except Exception:
        return body


def _request_url(base_url: str, log: RequestLog) -> str:
    url = f"{base_url.rstrip('/')}{log.path}"
    if log.query_params:
        url = f"{url}?{urlencode(log.query_params, doseq=True)}"
    return url


def _curl_command(base_url: str, log: RequestLog) -> str:
    url = _request_url(base_url, log)
    lines = [
        "curl",
        "-X",
        log.method or "GET",
        shlex.quote(url),
        "-H",
        shlex.quote("Authorization: Bearer <API_KEY>"),
    ]
    content_type = log.request_headers.get("content-type")
    if content_type:
        lines.extend(["-H", shlex.quote(f"Content-Type: {content_type}")])
    if log.request_body:
        lines.extend(["--data-raw", shlex.quote(log.request_body)])
    return " \\\n  ".join(lines)


def log_detail(request_id: str, base_url: str) -> Optional[Dict[str, Any]]:
    log = get_log(request_id)
    if log is None:
        return None

    return {
        "request_id": log.request_id,
        "time_str": fmt_time(log.timestamp),
        "method": log.method,
        "path": log.path,
        "url": _request_url(base_url, log),
        "query_params": _pretty_json(log.query_params),
        "client_ip": log.client_ip,
        "user_agent": log.user_agent,
        "api_key_name": log.api_key_name,
        "model": log.model,
        "status": log.status,
        "status_code": log.status_code,
        "duration_ms": log.duration_ms,
        "is_stream": log.is_stream,
        "error_message": log.error_message,
        "request_headers": _pretty_json(log.request_headers),
        "request_body": _format_body(log.request_body),
        "request_body_truncated": log.request_body_truncated,
        "response_headers": _pretty_json(log.response_headers),
        "response_body": _format_body(log.response_body),
        "response_body_truncated": log.response_body_truncated,
        "raw_stream_body": log.raw_stream_body,
        "parsed_response_text": log.parsed_response_text,
        "parsed_reasoning_content": log.parsed_reasoning_content,
        "curl": _curl_command(base_url, log),
    }


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
