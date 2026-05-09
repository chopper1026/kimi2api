import os
from typing import Any, Dict

import jinja2
from fastapi import Request
from fastapi.responses import HTMLResponse

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(_TEMPLATES_DIR),
    autoescape=True,
)


def render_template(template_name: str, **context: Any) -> str:
    return _env.get_template(template_name).render(**context)


def render_html(template_name: str, **context: Any) -> HTMLResponse:
    return HTMLResponse(render_template(template_name, **context))


def render_page(
    request: Request,
    template_name: str,
    context: Dict[str, Any],
    *,
    csrf_token: str,
) -> HTMLResponse:
    ctx = {
        "request": request,
        "authenticated": True,
        "version": "1.2.0",
        "active_tab": context.get("active_tab", "dashboard"),
        "csrf_token": csrf_token,
    }
    ctx.update(context)
    return render_html(template_name, **ctx)
