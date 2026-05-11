from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..core.auth import (
    check_login_rate_limit,
    clear_login_rate_limit,
    create_session,
    destroy_session,
    get_csrf_token,
    is_dashboard_enabled,
    record_failed_login,
    verify_csrf,
    verify_password,
    verify_session,
)
from ..core.keys import create_key, delete_key
from ..core.kimi_token_store import save_kimi_token
from ..core.token_manager import get_token_manager, replace_token_manager
from .view_models import dashboard_stats, key_list, log_detail, log_page, token_info


def create_api_router() -> APIRouter:
    router = APIRouter(prefix="/admin/api", tags=["admin-api"])

    @router.get("/session")
    async def session_info(request: Request):
        if not is_dashboard_enabled():
            return JSONResponse({"enabled": False}, status_code=503)
        if not verify_session(request):
            return JSONResponse({"authenticated": False}, status_code=401)
        return JSONResponse({
            "authenticated": True,
            "csrf_token": get_csrf_token(request) or "",
        })

    @router.post("/login")
    async def login(request: Request):
        if not is_dashboard_enabled():
            return JSONResponse({"success": False, "error": "Dashboard 已禁用"}, status_code=503)

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"success": False, "error": "无效请求"}, status_code=400)

        password = body.get("password", "")
        client_ip = request.client.host if request.client else "unknown"

        if not check_login_rate_limit(client_ip):
            return JSONResponse(
                {"success": False, "error": "登录尝试过多，请15分钟后再试"},
                status_code=429,
            )

        if verify_password(password):
            clear_login_rate_limit(client_ip)
            response = JSONResponse({"success": True})
            create_session(response)
            return response

        record_failed_login(client_ip)
        return JSONResponse({"success": False, "error": "密码错误"}, status_code=401)

    @router.post("/logout")
    async def logout(request: Request):
        if not verify_csrf(request):
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        response = JSONResponse({"success": True})
        destroy_session(response)
        return response

    @router.get("/stats")
    async def stats(request: Request):
        if not verify_session(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return JSONResponse(dashboard_stats())

    @router.get("/token")
    async def token_get(request: Request):
        if not verify_session(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return JSONResponse(token_info())

    @router.post("/token")
    async def token_save(request: Request):
        if not verify_session(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not verify_csrf(request):
            return JSONResponse({"error": "Forbidden"}, status_code=403)

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"success": False, "error": "无效请求"}, status_code=400)

        raw_token = (body.get("raw_token") or "").strip()
        if not raw_token:
            return JSONResponse(
                {"success": False, "error": "Token 不能为空", "token": token_info()},
                status_code=400,
            )

        try:
            save_kimi_token(raw_token)
            await replace_token_manager(raw_token)
            return JSONResponse({"success": True, "message": "Token 已保存", "token": token_info()})
        except Exception as exc:
            return JSONResponse(
                {"success": False, "error": f"Token 保存失败: {exc}", "token": token_info()},
                status_code=500,
            )

    @router.post("/token/refresh")
    async def token_refresh(request: Request):
        if not verify_session(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not verify_csrf(request):
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        try:
            mgr = get_token_manager()
            await mgr.invalidate_and_retry()
            return JSONResponse({"success": True, "token": token_info()})
        except RuntimeError:
            return JSONResponse(
                {"success": False, "error": "请先保存 Token", "token": token_info()},
                status_code=400,
            )
        except Exception as exc:
            return JSONResponse(
                {"success": False, "error": str(exc), "token": token_info()},
                status_code=502,
            )

    @router.get("/token/validate")
    async def token_validate(request: Request):
        if not verify_session(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        from ..kimi import Kimi2API
        try:
            async with Kimi2API() as client:
                valid = await client.validate_token()
                sub = await client.get_subscription()
        except Exception as exc:
            valid = False
            sub = {"error": str(exc)}
        return JSONResponse({"valid": valid, "subscription": sub})

    @router.get("/keys")
    async def keys_get(request: Request):
        if not verify_session(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return JSONResponse({"keys": key_list()})

    @router.post("/keys")
    async def keys_create(request: Request):
        if not verify_session(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not verify_csrf(request):
            return JSONResponse({"error": "Forbidden"}, status_code=403)

        name = None
        try:
            body = await request.json()
            name = body.get("name") or None
        except Exception:
            pass

        new = create_key(name)
        return JSONResponse({"keys": key_list(), "new_key": new.key})

    @router.delete("/keys/{key:path}")
    async def keys_delete(request: Request, key: str):
        if not verify_session(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not verify_csrf(request):
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        delete_key(key)
        return JSONResponse({"keys": key_list(), "deleted": True})

    @router.get("/logs")
    async def logs_list(request: Request):
        if not verify_session(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        filters = {
            "q": request.query_params.get("q", ""),
            "status": request.query_params.get("status", ""),
            "model": request.query_params.get("model", ""),
            "api_key_name": request.query_params.get("api_key_name", ""),
            "path": request.query_params.get("path", ""),
            "stream": request.query_params.get("stream", ""),
            "page": request.query_params.get("page", "1"),
        }
        return JSONResponse(log_page(filters))

    @router.get("/logs/{request_id}")
    async def log_detail_get(request: Request, request_id: str):
        if not verify_session(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        detail = log_detail(request_id, str(request.base_url))
        if detail is None:
            return JSONResponse({"error": "Not found"}, status_code=404)
        return JSONResponse(detail)

    return router
