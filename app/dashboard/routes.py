import json
from html import escape

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

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
from .templates import render_html, render_page, render_template
from . import view_models
from .view_models import dashboard_stats, key_list, log_detail, log_page, token_info


def set_start_time(t: float) -> None:
    view_models.set_start_time(t)


def _is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request", "").lower() == "true"


def create_dashboard_router() -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["admin"])

    @router.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if not is_dashboard_enabled():
            return HTMLResponse("<h1>Dashboard disabled: set ADMIN_PASSWORD</h1>", status_code=503)
        if verify_session(request):
            return RedirectResponse("/admin/dashboard", status_code=302)
        ctx = {"request": request, "authenticated": False, "error": None}
        return render_html("admin.html", **ctx)

    @router.post("/login", response_class=HTMLResponse)
    async def login_submit(request: Request, password: str = Form(...)):
        if not is_dashboard_enabled():
            return HTMLResponse("<h1>Dashboard disabled</h1>", status_code=503)

        client_ip = request.client.host if request.client else "unknown"

        if not check_login_rate_limit(client_ip):
            ctx = {"request": request, "authenticated": False, "error": "登录尝试过多，请15分钟后再试"}
            resp = render_html("admin.html", **ctx)
            resp.status_code = 429
            return resp

        if verify_password(password):
            clear_login_rate_limit(client_ip)
            response = RedirectResponse("/admin/dashboard", status_code=302)
            create_session(response)
            return response

        record_failed_login(client_ip)
        ctx = {"request": request, "authenticated": False, "error": "密码错误"}
        resp = render_html("admin.html", **ctx)
        resp.status_code = 401
        return resp

    @router.post("/logout", response_class=HTMLResponse)
    async def logout(request: Request, csrf_token: str = Form("")):
        if not verify_csrf(request, csrf_token):
            return HTMLResponse("Forbidden", status_code=403)
        response = RedirectResponse("/admin/login", status_code=302)
        destroy_session(response)
        return response

    @router.get("/", response_class=HTMLResponse)
    async def dashboard_home(request: Request):
        if verify_session(request):
            return RedirectResponse("/admin/dashboard", status_code=302)
        return RedirectResponse("/admin/login", status_code=302)

    @router.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_index(request: Request):
        if not verify_session(request):
            return RedirectResponse("/admin/login", status_code=302)

        tab_content = render_template(
            "partials/dashboard.html",
            request=request,
            **dashboard_stats(),
        )

        if _is_htmx(request):
            return HTMLResponse(tab_content)

        return render_page(
            request,
            "admin.html",
            {
                "active_tab": "dashboard",
                "tab_content": tab_content,
            },
            csrf_token=get_csrf_token(request) or "",
        )

    @router.get("/api/stats", response_class=HTMLResponse)
    async def stats_partial(request: Request):
        if not verify_session(request):
            return HTMLResponse("", status_code=401)

        return render_template(
            "partials/_stats_inner.html",
            request=request,
            **dashboard_stats(),
        )

    @router.get("/token", response_class=HTMLResponse)
    async def token_panel(request: Request):
        if not verify_session(request):
            return RedirectResponse("/admin/login", status_code=302)
        content = render_template(
            "partials/token.html",
            request=request,
            **token_info(),
            subscription=None,
            token_message=None,
            token_error=None,
            show_token_editor=False,
        )
        if _is_htmx(request):
            return HTMLResponse(content)
        return render_page(
            request,
            "admin.html",
            {
                "active_tab": "token",
                "tab_content": content,
            },
            csrf_token=get_csrf_token(request) or "",
        )

    @router.get("/token/edit", response_class=HTMLResponse)
    async def token_edit(request: Request):
        if not verify_session(request):
            return HTMLResponse("", status_code=401)
        return render_template("partials/token_editor.html", request=request)

    @router.get("/token/editor-empty", response_class=HTMLResponse)
    async def token_editor_empty(request: Request):
        if not verify_session(request):
            return HTMLResponse("", status_code=401)
        return HTMLResponse("")

    @router.post("/token", response_class=HTMLResponse)
    async def token_save(request: Request, raw_token: str = Form(...)):
        if not verify_session(request):
            return HTMLResponse("", status_code=401)
        if not verify_csrf(request):
            return HTMLResponse("Forbidden", status_code=403)

        token = raw_token.strip()
        token_error = None
        token_message = None
        if not token:
            token_error = "Token 不能为空"
        else:
            try:
                save_kimi_token(token)
                await replace_token_manager(token)
                token_message = "Token 已保存"
            except Exception as exc:
                token_error = f"Token 保存失败: {exc}"

        return render_template(
            "partials/token.html",
            request=request,
            **token_info(),
            subscription=None,
            token_message=token_message,
            token_error=token_error,
            show_token_editor=bool(token_error),
        )

    @router.post("/token/refresh", response_class=HTMLResponse)
    async def token_refresh(request: Request):
        if not verify_session(request):
            return HTMLResponse("", status_code=401)
        if not verify_csrf(request):
            return HTMLResponse("Forbidden", status_code=403)
        try:
            mgr = get_token_manager()
            await mgr.invalidate_and_retry()
            token_error = None
        except RuntimeError:
            token_error = "请先保存 Token"
        ti = token_info()
        return render_template(
            "partials/token.html",
            request=request,
            **ti,
            subscription=None,
            token_message=None,
            token_error=token_error,
            show_token_editor=False,
        )

    @router.get("/token/validate", response_class=HTMLResponse)
    async def token_validate(request: Request):
        if not verify_session(request):
            return HTMLResponse("", status_code=401)
        from ..kimi import Kimi2API
        try:
            async with Kimi2API() as client:
                valid = await client.validate_token()
                sub = await client.get_subscription()
        except Exception as exc:
            valid = False
            sub = {"error": str(exc)}
        sub_str = json.dumps(sub, indent=2, ensure_ascii=False) if sub else "无法获取"
        status_text = "有效" if valid else "无效"
        color = "text-green-400" if valid else "text-red-400"
        return HTMLResponse(
            f'<div class="mt-3 p-4 bg-gray-900 border border-gray-800 rounded-xl">'
            f'<p class="font-medium {color}">Token 验证结果: {status_text}</p>'
            '<pre class="mt-2 text-xs text-gray-400 overflow-auto max-h-48">'
            f"{escape(sub_str)}</pre>"
            f'</div>'
        )

    @router.get("/keys", response_class=HTMLResponse)
    async def keys_panel(request: Request):
        if not verify_session(request):
            return RedirectResponse("/admin/login", status_code=302)
        content = render_template(
            "partials/keys.html",
            request=request, keys=key_list(), new_key=None,
        )
        if _is_htmx(request):
            return HTMLResponse(content)
        return render_page(
            request,
            "admin.html",
            {
                "active_tab": "keys",
                "tab_content": content,
            },
            csrf_token=get_csrf_token(request) or "",
        )

    @router.post("/keys", response_class=HTMLResponse)
    async def keys_create(request: Request):
        if not verify_session(request):
            return HTMLResponse("", status_code=401)
        if not verify_csrf(request):
            return HTMLResponse("Forbidden", status_code=403)
        body = await request.body()
        name = None
        if body:
            try:
                data = json.loads(body)
                name = data.get("answer") or data.get("name") or None
            except Exception:
                pass
        new = create_key(name)
        return render_template(
            "partials/keys.html",
            request=request, keys=key_list(), new_key=new.key,
        )

    @router.delete("/keys/{key:path}", response_class=HTMLResponse)
    async def keys_delete(request: Request, key: str):
        if not verify_session(request):
            return HTMLResponse("", status_code=401)
        if not verify_csrf(request):
            return HTMLResponse("Forbidden", status_code=403)
        delete_key(key)
        return render_template(
            "partials/keys.html",
            request=request, keys=key_list(), new_key=None,
        )

    @router.get("/logs", response_class=HTMLResponse)
    async def logs_panel(request: Request):
        if not verify_session(request):
            return RedirectResponse("/admin/login", status_code=302)
        filters = {
            "q": request.query_params.get("q", ""),
            "status": request.query_params.get("status", ""),
            "model": request.query_params.get("model", ""),
            "api_key_name": request.query_params.get("api_key_name", ""),
            "path": request.query_params.get("path", ""),
            "stream": request.query_params.get("stream", ""),
            "page": request.query_params.get("page", "1"),
        }
        page_data = log_page(filters)
        content = render_template(
            "partials/logs.html",
            request=request,
            logs=page_data["logs"],
            pagination=page_data["pagination"],
            filters=filters,
        )
        if _is_htmx(request):
            return HTMLResponse(content)
        return render_page(
            request,
            "admin.html",
            {
                "active_tab": "logs",
                "tab_content": content,
            },
            csrf_token=get_csrf_token(request) or "",
        )

    @router.get("/logs/{request_id}", response_class=HTMLResponse)
    async def log_detail_panel(request: Request, request_id: str):
        if not verify_session(request):
            return RedirectResponse("/admin/login", status_code=302)
        detail = log_detail(request_id, str(request.base_url))
        if detail is None:
            return HTMLResponse("Not found", status_code=404)
        content = render_template(
            "partials/log_detail.html",
            request=request, log=detail,
        )
        if _is_htmx(request):
            return HTMLResponse(content)
        return render_page(
            request,
            "admin.html",
            {
                "active_tab": "logs",
                "tab_content": content,
            },
            csrf_token=get_csrf_token(request) or "",
        )

    return router
