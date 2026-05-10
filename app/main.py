import logging
import os
import json
import time
import uuid
from typing import Any, AsyncIterator, Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import Config
from .kimi import KimiAPIError
from .core.keys import get_key as _get_key, init_key_store
from .core.logs import RequestLog, log_request
from .core.auth import init_auth
from .core.kimi_token_store import load_configured_kimi_token
from .core.token_manager import init_token_manager

from .api.errors import _json_error
from .api.models import SERVER_NAME
from .api.routes import router as api_router
from .dashboard.routes import create_dashboard_router

logger = logging.getLogger("kimi2api.main")


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


def create_app() -> FastAPI:
    app = FastAPI(
        title=SERVER_NAME,
        version="1.2.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # ---- Static files ----
    _static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

    @app.get("/favicon.ico", include_in_schema=False)
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
    async def handle_kimi_error(_: Request, exc: KimiAPIError) -> JSONResponse:
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
    app.include_router(create_dashboard_router())

    return app


def main() -> None:
    """Application entrypoint: load config, initialize subsystems, run uvicorn."""
    from dotenv import load_dotenv
    load_dotenv()

    Config.load()

    raw_token = load_configured_kimi_token()
    if raw_token:
        init_token_manager(raw_token)
    else:
        logger.warning("Kimi token is not configured; set it in /admin/token")

    init_key_store()
    init_auth()

    from .dashboard.routes import set_start_time
    set_start_time(time.time())

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
