import time
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python 3.8 compatibility
    from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..config import Config
from ..core.keys import list_keys, total_request_count
from ..core.logs import RequestLog, count_logs, get_log, get_recent_logs, search_logs
from ..core.token_manager import get_token_manager

_START_TIME: float = 0.0
LOGS_PAGE_SIZE = 20


def set_start_time(t: float) -> None:
    global _START_TIME
    _START_TIME = t


def _display_timezone() -> Tuple[ZoneInfo, str]:
    try:
        return ZoneInfo(Config.TIMEZONE), Config.TIMEZONE
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Shanghai"), "Asia/Shanghai"


def _local_datetime(ts: float) -> datetime:
    timezone, _ = _display_timezone()
    return datetime.fromtimestamp(ts, tz=timezone)


def fmt_time(ts: float) -> str:
    if ts == 0:
        return "-"
    timezone, _ = _display_timezone()
    dt = datetime.fromtimestamp(ts, tz=timezone)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def fmt_duration(seconds: float) -> str:
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    if days > 0:
        return f"{days}天 {hours}小时"
    minutes = int((seconds % 3600) // 60)
    return f"{hours}小时 {minutes}分钟"


def fmt_request_duration(duration_ms: float) -> str:
    if duration_ms < 1000:
        return f"{duration_ms:.1f}ms"
    seconds = duration_ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remaining_seconds = seconds % 60
    return f"{minutes}m {remaining_seconds:.1f}s"


def _fmt_retry_after(seconds: float) -> str:
    if seconds <= 0:
        return ""
    return f"{seconds:.1f}s"


def _upstream_summary(log: RequestLog) -> str:
    parts = []
    if log.upstream_status_code:
        parts.append(f"Kimi {log.upstream_status_code}")
    if log.upstream_error_type:
        parts.append(log.upstream_error_type)
    retry_after = _fmt_retry_after(log.upstream_retry_after)
    if retry_after:
        parts.append(f"Retry-After: {retry_after}")
    return " / ".join(parts)


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
        "page": source.get("page", "1").strip(),
    }


def _positive_int(value: Any, default: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 1)


def _log_query_params(query: Dict[str, str], page: int) -> str:
    params = {
        key: value
        for key, value in query.items()
        if key != "page" and value
    }
    if page > 1:
        params["page"] = str(page)
    return f"?{urlencode(params)}" if params else ""


def _serialize_logs(entries: List[RequestLog]) -> List[Dict[str, Any]]:
    result = []
    for log in entries:
        result.append({
            "request_id": log.request_id,
            "request_id_short": log.request_id[:8],
            "time_str": _local_datetime(log.timestamp).strftime("%m-%d %H:%M:%S"),
            "api_key_name": log.api_key_name,
            "model": log.model,
            "method": log.method,
            "path": log.path,
            "status": log.status,
            "status_code": log.status_code,
            "duration_ms": log.duration_ms,
            "duration_display": fmt_request_duration(log.duration_ms),
            "is_stream": log.is_stream,
            "error_message": log.error_message,
            "upstream_status_code": log.upstream_status_code,
            "upstream_error_type": log.upstream_error_type,
            "upstream_retry_after": log.upstream_retry_after,
            "upstream_summary": _upstream_summary(log),
        })
    return result


def log_page(filters: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    query = _log_filters(filters)
    requested_page = _positive_int(query["page"])
    total = count_logs(
        q=query["q"],
        status=query["status"],
        model=query["model"],
        api_key_name=query["api_key_name"],
        path=query["path"],
        stream=query["stream"],
    )
    page_count = max((total + LOGS_PAGE_SIZE - 1) // LOGS_PAGE_SIZE, 1)
    page = min(requested_page, page_count)
    offset = (page - 1) * LOGS_PAGE_SIZE
    entries = search_logs(
        q=query["q"],
        status=query["status"],
        model=query["model"],
        api_key_name=query["api_key_name"],
        path=query["path"],
        stream=query["stream"],
        limit=LOGS_PAGE_SIZE,
        offset=offset,
    )
    start_index = offset + 1 if total else 0
    end_index = offset + len(entries) if total else 0

    return {
        "logs": _serialize_logs(entries),
        "pagination": {
            "total": total,
            "page": page,
            "page_count": page_count,
            "page_size": LOGS_PAGE_SIZE,
            "start_index": start_index,
            "end_index": end_index,
            "has_prev": page > 1,
            "has_next": page < page_count,
            "prev_url": _log_query_params(query, page - 1),
            "next_url": _log_query_params(query, page + 1),
            "first_url": _log_query_params(query, 1),
            "last_url": _log_query_params(query, page_count),
        },
    }


def log_list(filters: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    return log_page(filters)["logs"]


def _pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _format_body(body: str) -> str:
    if not body:
        return ""
    try:
        return _pretty_json(json.loads(body))
    except Exception:
        return body


def _json_body_view(body: str) -> Dict[str, Any]:
    if not body:
        return {"is_json": False, "parsed": None, "text": ""}
    try:
        return {"is_json": True, "parsed": json.loads(body), "text": ""}
    except Exception:
        return {"is_json": False, "parsed": None, "text": body}


def _request_url(base_url: str, log: RequestLog) -> str:
    url = f"{base_url.rstrip('/')}{log.path}"
    if log.query_params:
        url = f"{url}?{urlencode(log.query_params, doseq=True)}"
    return url


def log_detail(request_id: str, base_url: str) -> Optional[Dict[str, Any]]:
    log = get_log(request_id)
    if log is None:
        return None
    request_body = _json_body_view(log.request_body)

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
        "duration_display": fmt_request_duration(log.duration_ms),
        "is_stream": log.is_stream,
        "error_message": log.error_message,
        "upstream_status_code": log.upstream_status_code,
        "upstream_error_type": log.upstream_error_type,
        "upstream_retry_after": log.upstream_retry_after,
        "upstream_summary": _upstream_summary(log),
        "request_headers": _pretty_json(log.request_headers),
        "request_body": _format_body(request_body["text"]),
        "request_body_is_json": request_body["is_json"],
        "request_body_json": request_body["parsed"],
        "request_body_truncated": log.request_body_truncated,
        "response_headers": _pretty_json(log.response_headers),
        "raw_stream_body": log.raw_stream_body,
        "parsed_response_text": log.parsed_response_text,
        "parsed_reasoning_content": log.parsed_reasoning_content,
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
