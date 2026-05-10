import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..config import Config
from .storage import data_path, ensure_data_dir

logger = logging.getLogger("kimi2api.logs")

BUFFER_SIZE = 1000
LOG_DB_NAME = "request_logs.sqlite3"
REDACTED = "[redacted]"
TRUNCATED_SUFFIX = "\n...[truncated]"
SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "set_cookie",
    "x-csrf-token",
    "x_csrf_token",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "password",
    "secret",
}


@dataclass
class RequestLog:
    timestamp: float
    api_key_name: str
    model: str
    status: str
    status_code: int
    duration_ms: float
    is_stream: bool = False
    request_id: str = ""
    method: str = ""
    path: str = ""
    query_params: Dict[str, Any] = field(default_factory=dict)
    client_ip: str = ""
    user_agent: str = ""
    request_headers: Dict[str, str] = field(default_factory=dict)
    request_body: str = ""
    request_body_truncated: bool = False
    response_headers: Dict[str, str] = field(default_factory=dict)
    response_body: str = ""
    response_body_truncated: bool = False
    raw_stream_body: str = ""
    parsed_response_text: str = ""
    parsed_reasoning_content: str = ""
    error_message: str = ""


def _db_path() -> str:
    return data_path(LOG_DB_NAME)


def _connect() -> sqlite3.Connection:
    ensure_data_dir()
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            timestamp REAL NOT NULL,
            method TEXT NOT NULL,
            path TEXT NOT NULL,
            query_params TEXT NOT NULL,
            client_ip TEXT NOT NULL,
            user_agent TEXT NOT NULL,
            api_key_name TEXT NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            duration_ms REAL NOT NULL,
            is_stream INTEGER NOT NULL,
            request_headers TEXT NOT NULL,
            request_body TEXT NOT NULL,
            request_body_truncated INTEGER NOT NULL,
            response_headers TEXT NOT NULL,
            response_body TEXT NOT NULL,
            response_body_truncated INTEGER NOT NULL,
            raw_stream_body TEXT NOT NULL,
            parsed_response_text TEXT NOT NULL,
            parsed_reasoning_content TEXT NOT NULL,
            error_message TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_request_logs_timestamp ON request_logs(timestamp DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_request_logs_status ON request_logs(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_request_logs_model ON request_logs(model)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_request_logs_path ON request_logs(path)")
    conn.commit()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _is_sensitive_name(name: str) -> bool:
    lower = name.lower().replace("-", "_")
    return lower in SENSITIVE_KEYS or any(part in lower for part in ("token", "secret", "password"))


def _redact_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_sensitive_name(str(key)) else _redact_json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_json_value(item) for item in value]
    return value


def _redact_json_text(text: str) -> str:
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except Exception:
        return text
    return _json_dumps(_redact_json_value(parsed))


def _limit_text(text: str, limit: int) -> Tuple[str, bool]:
    if limit < 0:
        limit = 0
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text, False
    truncated = raw[:limit].decode("utf-8", errors="ignore")
    return f"{truncated}{TRUNCATED_SUFFIX}", True


def _sanitize_body(value: str, limit: int) -> Tuple[str, bool]:
    return _limit_text(_redact_json_text(value or ""), limit)


def _sanitize_headers(headers: Dict[str, Any]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for key, value in (headers or {}).items():
        normalized = str(key).lower()
        if _is_sensitive_name(normalized):
            result[normalized] = REDACTED
        else:
            result[normalized] = str(value)
    return result


def _parse_stream_body(raw_body: str) -> Tuple[str, str]:
    content_parts: List[str] = []
    reasoning_parts: List[str] = []

    for line in raw_body.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            data = json.loads(payload)
        except Exception:
            continue

        if isinstance(data, dict) and isinstance(data.get("choices"), list) and data["choices"]:
            delta = data["choices"][0].get("delta", {})
            if isinstance(delta, dict):
                if delta.get("content"):
                    content_parts.append(str(delta["content"]))
                if delta.get("reasoning_content"):
                    reasoning_parts.append(str(delta["reasoning_content"]))
            continue

        if isinstance(data, dict):
            event_type = data.get("type")
            delta = data.get("delta")
            if event_type == "response.output_text.delta" and delta:
                content_parts.append(str(delta))
            elif event_type == "response.reasoning.delta" and delta:
                reasoning_parts.append(str(delta))

    return "".join(content_parts), "".join(reasoning_parts)


def _prepare_entry(entry: RequestLog) -> RequestLog:
    limit = int(getattr(Config, "REQUEST_LOG_BODY_LIMIT_BYTES", 1048576))
    request_body, request_truncated = _sanitize_body(entry.request_body, limit)
    raw_stream_body = entry.raw_stream_body or (entry.response_body if entry.is_stream else "")

    parsed_text = entry.parsed_response_text
    parsed_reasoning = entry.parsed_reasoning_content
    if entry.is_stream and raw_stream_body and not (parsed_text or parsed_reasoning):
        parsed_text, parsed_reasoning = _parse_stream_body(raw_stream_body)

    return replace(
        entry,
        request_id=entry.request_id or uuid.uuid4().hex,
        request_headers=_sanitize_headers(entry.request_headers),
        response_headers=_sanitize_headers(entry.response_headers),
        request_body=request_body,
        request_body_truncated=request_truncated,
        response_body="",
        response_body_truncated=False,
        raw_stream_body="",
        parsed_response_text=parsed_text,
        parsed_reasoning_content=parsed_reasoning,
    )


def _retention_limit() -> int:
    value = int(getattr(Config, "REQUEST_LOG_RETENTION", BUFFER_SIZE))
    return max(value, 1)


def _trim_logs(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        DELETE FROM request_logs
        WHERE id NOT IN (
            SELECT id FROM request_logs
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
        )
        """,
        (_retention_limit(),),
    )


def log_request(entry: RequestLog) -> None:
    entry = _prepare_entry(entry)
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO request_logs (
                    request_id, timestamp, method, path, query_params, client_ip, user_agent,
                    api_key_name, model, status, status_code, duration_ms, is_stream,
                    request_headers, request_body, request_body_truncated,
                    response_headers, response_body, response_body_truncated,
                    raw_stream_body, parsed_response_text, parsed_reasoning_content,
                    error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.request_id,
                    entry.timestamp,
                    entry.method,
                    entry.path,
                    _json_dumps(entry.query_params),
                    entry.client_ip,
                    entry.user_agent,
                    entry.api_key_name,
                    entry.model,
                    entry.status,
                    entry.status_code,
                    round(entry.duration_ms, 1),
                    1 if entry.is_stream else 0,
                    _json_dumps(entry.request_headers),
                    entry.request_body,
                    1 if entry.request_body_truncated else 0,
                    _json_dumps(entry.response_headers),
                    entry.response_body,
                    1 if entry.response_body_truncated else 0,
                    entry.raw_stream_body,
                    entry.parsed_response_text,
                    entry.parsed_reasoning_content,
                    entry.error_message,
                ),
            )
            _trim_logs(conn)
            conn.commit()
    except Exception as exc:
        logger.warning("Failed to write request log: %s", exc)


def _row_to_entry(row: sqlite3.Row) -> RequestLog:
    return RequestLog(
        request_id=row["request_id"],
        timestamp=row["timestamp"],
        method=row["method"],
        path=row["path"],
        query_params=_json_loads(row["query_params"], {}),
        client_ip=row["client_ip"],
        user_agent=row["user_agent"],
        api_key_name=row["api_key_name"],
        model=row["model"],
        status=row["status"],
        status_code=row["status_code"],
        duration_ms=row["duration_ms"],
        is_stream=bool(row["is_stream"]),
        request_headers=_json_loads(row["request_headers"], {}),
        request_body=row["request_body"],
        request_body_truncated=bool(row["request_body_truncated"]),
        response_headers=_json_loads(row["response_headers"], {}),
        response_body=row["response_body"],
        response_body_truncated=bool(row["response_body_truncated"]),
        raw_stream_body=row["raw_stream_body"],
        parsed_response_text=row["parsed_response_text"],
        parsed_reasoning_content=row["parsed_reasoning_content"],
        error_message=row["error_message"],
    )


def _add_like_filter(where: List[str], params: List[Any], columns: Iterable[str], value: str) -> None:
    if not value:
        return
    pattern = f"%{value}%"
    clauses = [f"{column} LIKE ?" for column in columns]
    where.append("(" + " OR ".join(clauses) + ")")
    params.extend([pattern] * len(clauses))


def search_logs(
    *,
    q: str = "",
    status: str = "",
    model: str = "",
    api_key_name: str = "",
    path: str = "",
    stream: str = "",
    limit: int = 200,
) -> List[RequestLog]:
    where: List[str] = []
    params: List[Any] = []

    _add_like_filter(
        where,
        params,
        (
            "request_id",
            "path",
            "model",
            "api_key_name",
            "status",
            "client_ip",
            "user_agent",
            "request_body",
            "parsed_response_text",
            "parsed_reasoning_content",
            "error_message",
        ),
        q.strip(),
    )
    _add_like_filter(where, params, ("status",), status.strip())
    _add_like_filter(where, params, ("model",), model.strip())
    _add_like_filter(where, params, ("api_key_name",), api_key_name.strip())
    _add_like_filter(where, params, ("path",), path.strip())

    stream_value = stream.strip().lower()
    if stream_value in {"true", "1", "yes", "stream"}:
        where.append("is_stream = 1")
    elif stream_value in {"false", "0", "no", "normal"}:
        where.append("is_stream = 0")

    sql = "SELECT * FROM request_logs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY timestamp DESC, id DESC LIMIT ?"
    params.append(max(int(limit), 1))

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_entry(row) for row in rows]


def get_recent_logs(limit: int = 100) -> List[RequestLog]:
    return search_logs(limit=limit)


def get_log(request_id: str) -> Optional[RequestLog]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM request_logs WHERE request_id = ?",
            (request_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_entry(row)


def total_log_count() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM request_logs").fetchone()
    return int(row["count"])


def clear_logs() -> None:
    path = _db_path()
    if os.path.exists(path):
        os.remove(path)
