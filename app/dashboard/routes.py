import json
import os
import time
from datetime import datetime, timezone
from html import escape
from typing import Any, Dict, List

from fastapi import APIRouter, Form, Request, Response
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
from ..core.keys import create_key, delete_key, get_key, list_keys, total_request_count
from ..core.logs import get_recent_logs
from ..core.kimi_token_store import save_kimi_token
from ..core.token_manager import get_token_manager, replace_token_manager

import jinja2
import os as _os

_START_TIME: float = 0.0


def set_start_time(t: float) -> None:
    global _START_TIME
    _START_TIME = t

_TEMPLATES_DIR = _os.path.join(_os.path.dirname(__file__), "templates")
_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(_TEMPLATES_DIR),
    autoescape=True,
)


def _render_html(template_name: str, **context) -> HTMLResponse:
    tmpl = _env.get_template(template_name)
    html = tmpl.render(**context)
    return HTMLResponse(html)


def _fmt_time(ts: float) -> str:
    if ts == 0:
        return "-"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _fmt_duration(seconds: float) -> str:
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    if days > 0:
        return f"{days}天 {hours}小时"
    minutes = int((seconds % 3600) // 60)
    return f"{hours}小时 {minutes}分钟"


def _render(request: Request, template_name: str, context: Dict[str, Any]) -> HTMLResponse:
    ctx = {
        "request": request,
        "authenticated": True,
        "version": "1.2.0",
        "active_tab": context.get("active_tab", "dashboard"),
        "csrf_token": get_csrf_token(request) or "",
    }
    ctx.update(context)
    return _render_html(template_name, **ctx)


def _token_info() -> Dict[str, Any]:
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

    state = mgr._state
    now = time.time()

    if state.expires_at > 0:
        remaining = state.expires_at - now
        expires_str = _fmt_time(state.expires_at)
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


def _key_list() -> List[Dict[str, Any]]:
    now = time.time()
    result = []
    for k in list_keys():
        result.append({
            "key": k.key,
            "key_preview": k.key[:10] + "..." + k.key[-4:],
            "name": k.name,
            "created_at_str": _fmt_time(k.created_at),
            "last_used_str": _fmt_time(k.last_used) if k.last_used > 0 else "从未使用",
            "request_count": k.request_count,
        })
    return result


def _log_list() -> List[Dict[str, Any]]:
    result = []
    for log in get_recent_logs(200):
        result.append({
            "time_str": datetime.fromtimestamp(log.timestamp, tz=timezone.utc).strftime("%m-%d %H:%M:%S"),
            "api_key_name": log.api_key_name,
            "model": log.model,
            "status": log.status,
            "status_code": log.status_code,
            "duration_ms": log.duration_ms,
            "is_stream": log.is_stream,
        })
    return result


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
        return _render_html("admin.html", **ctx)

    @router.post("/login", response_class=HTMLResponse)
    async def login_submit(request: Request, password: str = Form(...)):
        if not is_dashboard_enabled():
            return HTMLResponse("<h1>Dashboard disabled</h1>", status_code=503)

        client_ip = request.client.host if request.client else "unknown"

        if not check_login_rate_limit(client_ip):
            ctx = {"request": request, "authenticated": False, "error": "登录尝试过多，请15分钟后再试"}
            resp = _render_html("admin.html", **ctx)
            resp.status_code = 429
            return resp

        if verify_password(password):
            clear_login_rate_limit(client_ip)
            response = RedirectResponse("/admin/dashboard", status_code=302)
            create_session(response)
            return response

        record_failed_login(client_ip)
        ctx = {"request": request, "authenticated": False, "error": "密码错误"}
        resp = _render_html("admin.html", **ctx)
        resp.status_code = 401
        return resp

    @router.post("/logout", response_class=HTMLResponse)
    async def logout(request: Request):
        if not verify_csrf(request):
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

        uptime = _fmt_duration(time.time() - _START_TIME)
        ti = _token_info()
        keys = list_keys()

        tab_content = _env.get_template("partials/dashboard.html").render(
            request=request,
            uptime=uptime,
            token_healthy=ti["token_healthy"],
            token_status=ti["token_status"],
            token_type=ti["token_type"],
            token_expires=ti["token_expires"],
            key_count=len(keys),
            total_requests=total_request_count(),
            log_count=len(get_recent_logs(200)),
        )

        if _is_htmx(request):
            return HTMLResponse(tab_content)

        return _render(request, "admin.html", {
            "active_tab": "dashboard",
            "tab_content": tab_content,
        })

    @router.get("/api/stats", response_class=HTMLResponse)
    async def stats_partial(request: Request):
        if not verify_session(request):
            return HTMLResponse("", status_code=401)

        uptime = _fmt_duration(time.time() - _START_TIME)
        ti = _token_info()

        return _env.get_template("partials/_stats_inner.html").render(
            request=request,
            uptime=uptime,
            token_healthy=ti["token_healthy"],
            token_status=ti["token_status"],
            token_type=ti["token_type"],
            token_expires=ti["token_expires"],
            key_count=len(list_keys()),
            total_requests=total_request_count(),
            log_count=len(get_recent_logs(200)),
        )

    @router.get("/token", response_class=HTMLResponse)
    async def token_panel(request: Request):
        if not verify_session(request):
            return RedirectResponse("/admin/login", status_code=302)
        content = _env.get_template("partials/token.html").render(
            request=request,
            **_token_info(),
            subscription=None,
            token_message=None,
            token_error=None,
            show_token_editor=False,
        )
        if _is_htmx(request):
            return HTMLResponse(content)
        return _render(request, "admin.html", {
            "active_tab": "token",
            "tab_content": content,
        })

    @router.get("/token/edit", response_class=HTMLResponse)
    async def token_edit(request: Request):
        if not verify_session(request):
            return HTMLResponse("", status_code=401)
        return _env.get_template("partials/token_editor.html").render(request=request)

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

        return _env.get_template("partials/token.html").render(
            request=request,
            **_token_info(),
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
        ti = _token_info()
        return _env.get_template("partials/token.html").render(
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
        content = _env.get_template("partials/keys.html").render(
            request=request, keys=_key_list(), new_key=None,
        )
        if _is_htmx(request):
            return HTMLResponse(content)
        return _render(request, "admin.html", {
            "active_tab": "keys",
            "tab_content": content,
        })

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
        return _env.get_template("partials/keys.html").render(
            request=request, keys=_key_list(), new_key=new.key,
        )

    @router.delete("/keys/{key:path}", response_class=HTMLResponse)
    async def keys_delete(request: Request, key: str):
        if not verify_session(request):
            return HTMLResponse("", status_code=401)
        if not verify_csrf(request):
            return HTMLResponse("Forbidden", status_code=403)
        delete_key(key)
        return _env.get_template("partials/keys.html").render(
            request=request, keys=_key_list(), new_key=None,
        )

    @router.get("/logs", response_class=HTMLResponse)
    async def logs_panel(request: Request):
        if not verify_session(request):
            return RedirectResponse("/admin/login", status_code=302)
        content = _env.get_template("partials/logs.html").render(
            request=request, logs=_log_list(),
        )
        if _is_htmx(request):
            return HTMLResponse(content)
        return _render(request, "admin.html", {
            "active_tab": "logs",
            "tab_content": content,
        })

    return router
