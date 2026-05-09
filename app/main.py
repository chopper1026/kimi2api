import logging
import os
import time
from typing import Any, AsyncIterator

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Config
from .kimi import KimiAPIError
from .core.keys import get_key as _get_key, init_key_store
from .core.logs import RequestLog, log_request
from .core.auth import init_auth
from .core.kimi_token_store import load_configured_kimi_token
from .core.token_manager import init_token_manager

from .api.deps import SERVER_NAME, _json_error
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


def _log_v1_request(
    *,
    request: Request,
    response: Any,
    start: float,
    is_stream: bool,
) -> None:
    duration_ms = (time.time() - start) * 1000
    status = "success" if response.status_code < 400 else "error"
    if getattr(request.state, "stream_error", False):
        status = "error"

    log_request(RequestLog(
        timestamp=start,
        api_key_name=_request_api_key_name(request),
        model=getattr(request.state, "request_model", "unknown"),
        status=status,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 1),
        is_stream=is_stream,
    ))


def _wrap_streaming_log(
    *,
    request: Request,
    response: Any,
    start: float,
) -> None:
    original_iterator = response.body_iterator

    async def logging_iterator() -> AsyncIterator[Any]:
        try:
            async for chunk in original_iterator:
                yield chunk
        except BaseException:
            request.state.stream_error = True
            raise
        finally:
            _log_v1_request(
                request=request,
                response=response,
                start=start,
                is_stream=True,
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
        request.state.request_model = "unknown"
        request.state.stream_error = False
        response = await call_next(request)

        if _is_event_stream_response(response):
            _wrap_streaming_log(request=request, response=response, start=start)
            return response

        _log_v1_request(
            request=request,
            response=response,
            start=start,
            is_stream=False,
        )
        return response

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
