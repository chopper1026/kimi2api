import os
import json
import time
import uuid
from typing import Any, AsyncIterator, Dict, Optional
from urllib.parse import unquote

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .bootstrap import initialize_runtime, load_runtime_config, shutdown_runtime
from .config import Config
from .kimi import KimiAPIError
from .core.keys import get_key as _get_key
from .core.logs import RequestLog, log_request

from .api.errors import _json_error
from .api.models import SERVER_NAME
from .api.routes import router as api_router
from .dashboard.api_routes import create_api_router as create_dashboard_api_router


def _request_api_key_name(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return "anonymous"

    api_key = _get_key(auth[7:].strip())
    if api_key:
        return api_key.name
    return "anonymous"


def _is_event_stream_response(response: Any) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    return content_type.startswith("text/event-stream")


def _body_to_text(body: bytes) -> str:
    return body.decode("utf-8", errors="replace") if body else ""


def _query_params(request: Request) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in request.query_params.multi_items():
        existing = result.get(key)
        if existing is None:
            result[key] = value
        elif isinstance(existing, list):
            existing.append(value)
        else:
            result[key] = [existing, value]
    return result


def _safe_spa_file_path(dist_dir: str, requested_path: str) -> Optional[str]:
    root = os.path.realpath(dist_dir)
    decoded_path = unquote(requested_path).lstrip("/")
    if "\x00" in decoded_path:
        return None
    candidate = os.path.realpath(os.path.join(root, decoded_path))
    if candidate == root or not candidate.startswith(root + os.sep):
        return None
    if not os.path.isfile(candidate):
        return None
    return candidate


def _request_with_body(request: Request, body: bytes) -> Request:
    sent = False

    async def receive() -> Dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(request.scope, receive)


def _chunk_to_bytes(chunk: Any) -> bytes:
    if isinstance(chunk, bytes):
        return chunk
    return str(chunk).encode("utf-8")


def _capture_limit() -> int:
    return max(int(getattr(Config, "REQUEST_LOG_BODY_LIMIT", 1048576)), 0) + 1


def _append_capture(buffer: bytearray, chunk: Any) -> None:
    limit = _capture_limit()
    if len(buffer) >= limit:
        return
    data = _chunk_to_bytes(chunk)
    buffer.extend(data[: limit - len(buffer)])


def _extract_error_message(
    *,
    status_code: int,
    body: bytes,
    fallback: Optional[str] = None,
) -> str:
    if fallback:
        return fallback
    if status_code < 400:
        return ""
    text = _body_to_text(body).strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except Exception:
        return text[:500]
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        detail = data.get("detail")
        if isinstance(detail, dict) and detail.get("message"):
            return str(detail["message"])
        if isinstance(detail, str):
            return detail
    return text[:500]


def _response_header(response_headers: Dict[str, str], name: str) -> str:
    normalized = name.lower()
    for key, value in response_headers.items():
        if key.lower() == normalized:
            return value
    return ""


def _parse_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _parse_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _upstream_log_metadata(
    request: Request,
    response_headers: Dict[str, str],
) -> Dict[str, Any]:
    status_code = _parse_int(getattr(request.state, "upstream_status_code", 0))
    if not status_code:
        status_code = _parse_int(
            _response_header(response_headers, "X-Kimi-Upstream-Status")
        )

    error_type = str(getattr(request.state, "upstream_error_type", "") or "")
    if not error_type:
        error_type = _response_header(response_headers, "X-Kimi-Upstream-Error-Type")

    retry_after = _parse_float(getattr(request.state, "upstream_retry_after", 0.0))
    if not retry_after:
        retry_after = _parse_float(
            _response_header(response_headers, "X-Kimi-Upstream-Retry-After")
        )

    return {
        "upstream_status_code": status_code,
        "upstream_error_type": error_type,
        "upstream_retry_after": retry_after,
    }


def _log_v1_request(
    *,
    request: Request,
    start: float,
    status_code: int,
    is_stream: bool,
    request_body: bytes,
    response_headers: Dict[str, str],
    response_body: bytes,
    error_message: Optional[str] = None,
) -> None:
    duration_ms = (time.time() - start) * 1000
    stream_error_message = getattr(request.state, "stream_error_message", "")
    status = "success" if status_code < 400 else "error"
    if getattr(request.state, "stream_error", False):
        status = "error"
    message = _extract_error_message(
        status_code=status_code,
        body=response_body,
        fallback=error_message or stream_error_message,
    )
    upstream_metadata = _upstream_log_metadata(request, response_headers)

    log_request(RequestLog(
        timestamp=start,
        request_id=getattr(request.state, "request_id", ""),
        method=request.method,
        path=request.url.path,
        query_params=_query_params(request),
        client_ip=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", ""),
        api_key_name=_request_api_key_name(request),
        model=getattr(request.state, "request_model", "unknown"),
        status=status,
        status_code=status_code,
        duration_ms=round(duration_ms, 1),
        is_stream=is_stream,
        request_headers=dict(request.headers),
        request_body=_body_to_text(request_body),
        response_headers=response_headers,
        response_body=_body_to_text(response_body),
        raw_stream_body=_body_to_text(response_body) if is_stream else "",
        error_message=message,
        kimi_account_id=str(getattr(request.state, "kimi_account_id", "") or ""),
        kimi_account_name=str(getattr(request.state, "kimi_account_name", "") or ""),
        **upstream_metadata,
    ))


def _wrap_streaming_log(
    *,
    request: Request,
    response: Any,
    start: float,
    request_body: bytes,
) -> None:
    original_iterator = response.body_iterator
    captured = bytearray()

    async def logging_iterator() -> AsyncIterator[Any]:
        try:
            async for chunk in original_iterator:
                _append_capture(captured, chunk)
                yield chunk
        except BaseException:
            request.state.stream_error = True
            request.state.stream_error_message = "Streaming response failed"
            raise
        finally:
            _log_v1_request(
                request=request,
                start=start,
                status_code=response.status_code,
                is_stream=True,
                request_body=request_body,
                response_headers=dict(response.headers),
                response_body=bytes(captured),
            )

    response.body_iterator = logging_iterator()


def create_app(initialize: bool = True, static_dir: Optional[str] = None) -> FastAPI:
    if initialize:
        load_runtime_config()
        initialize_runtime()

    app = FastAPI(
        title=SERVER_NAME,
        version="1.2.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # ---- Static files ----
    _static_dir = static_dir or os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

    @app.get("/favicon.ico", include_in_schema=False)
    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(
            os.path.join(_static_dir, "favicon.svg"),
            media_type="image/svg+xml",
        )

    # ---- Request logging middleware ----
    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)

        start = time.time()
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        request.state.request_model = "unknown"
        request.state.stream_error = False
        request.state.stream_error_message = ""
        request.state.upstream_status_code = 0
        request.state.upstream_error_type = ""
        request.state.upstream_retry_after = 0.0
        request.state.kimi_account_id = ""
        request.state.kimi_account_name = ""
        request_body = await request.body()
        request = _request_with_body(request, request_body)

        try:
            response = await call_next(request)
        except Exception as exc:
            _log_v1_request(
                request=request,
                start=start,
                status_code=500,
                is_stream=False,
                request_body=request_body,
                response_headers={},
                response_body=b"",
                error_message=str(exc),
            )
            raise

        response.headers["X-Request-ID"] = request_id

        if _is_event_stream_response(response):
            _wrap_streaming_log(
                request=request,
                response=response,
                start=start,
                request_body=request_body,
            )
            return response

        response_body = bytearray()
        async for chunk in response.body_iterator:
            response_body.extend(_chunk_to_bytes(chunk))

        _log_v1_request(
            request=request,
            start=start,
            status_code=response.status_code,
            is_stream=False,
            request_body=request_body,
            response_headers=dict(response.headers),
            response_body=bytes(response_body),
        )
        return Response(
            content=bytes(response_body),
            status_code=response.status_code,
            headers=dict(response.headers),
            background=response.background,
        )

    # ---- Admin no-cache middleware ----
    @app.middleware("http")
    async def admin_no_cache(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # ---- Exception handlers ----
    @app.exception_handler(KimiAPIError)
    async def handle_kimi_error(request: Request, exc: KimiAPIError) -> JSONResponse:
        request.state.upstream_status_code = exc.upstream_status_code
        request.state.upstream_error_type = exc.upstream_error_type
        request.state.upstream_retry_after = exc.retry_after or 0.0
        return _json_error(str(exc), "api_error", status.HTTP_502_BAD_GATEWAY)

    @app.exception_handler(HTTPException)
    async def handle_http_error(_: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            return _json_error(
                exc.detail.get("message", "Request failed"),
                exc.detail.get("type", "invalid_request_error"),
                exc.status_code,
            )
        return _json_error(str(exc.detail), "invalid_request_error", exc.status_code)

    # ---- Include routers ----
    app.include_router(api_router)
    app.include_router(create_dashboard_api_router())

    # ---- SPA static files & fallback ----
    _dist_dir = os.path.join(_static_dir, "dist")
    _assets_dir = os.path.join(_dist_dir, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="spa-assets")

    def spa_fallback_response(path: str):
        if path == "api" or path.startswith("api/"):
            return JSONResponse({"error": "Not found"}, status_code=404)
        file_path = _safe_spa_file_path(_dist_dir, path)
        if file_path is not None:
            return FileResponse(file_path)
        index_path = os.path.join(_dist_dir, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
        return HTMLResponse(
            "Dashboard not built. Run: cd web && npm run build",
            status_code=503,
        )

    @app.get("/admin", include_in_schema=False)
    async def spa_root():
        return spa_fallback_response("")

    @app.get("/admin/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str):
        return spa_fallback_response(path)

    if initialize:
        async def shutdown_runtime_event() -> None:
            await shutdown_runtime()

        app.router.add_event_handler("shutdown", shutdown_runtime_event)

    return app


def main() -> None:
    """Application entrypoint: load server config and run uvicorn."""
    load_runtime_config()

    host = Config.HOST
    port = Config.PORT
    reload_enabled = Config.RELOAD

    uvicorn.run(
        "app.main:create_app",
        host=host,
        port=port,
        reload=reload_enabled,
        factory=True,
    )


if __name__ == "__main__":
    main()
