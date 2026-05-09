import os
import time

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Config
from .kimi import KimiAPIError
from .core.keys import get_key as _get_key, init_key_store
from .core.logs import RequestLog, log_request
from .core.auth import init_auth
from .core.token_manager import init_token_manager

from .api.deps import SERVER_NAME, _json_error
from .api.routes import router as api_router
from .dashboard.routes import create_dashboard_router


def create_app() -> FastAPI:
    app = FastAPI(title=SERVER_NAME, version="1.2.0")

    # ---- Static files ----
    _static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

    # ---- Request logging middleware ----
    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)

        start = time.time()
        request.state.request_model = "unknown"
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000

        auth = request.headers.get("authorization", "")
        key_name = "anonymous"
        if auth.startswith("Bearer "):
            k = _get_key(auth[7:].strip())
            if k:
                key_name = k.name

        log_request(RequestLog(
            timestamp=start,
            api_key_name=key_name,
            model=getattr(request.state, "request_model", "unknown"),
            status="success" if response.status_code < 400 else "error",
            status_code=response.status_code,
            duration_ms=round(duration_ms, 1),
        ))
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

    raw_token = Config.KIMI_TOKEN
    if not raw_token:
        raise ValueError("KIMI_TOKEN environment variable is required")

    init_token_manager(raw_token)
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
