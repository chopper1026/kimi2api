from typing import Any, Dict, Optional

from ..config import Config
from ..kimi.model_catalog import KimiModelCatalog, KimiModelSpec, get_model_catalog

SERVER_NAME = "Kimi2API"


class ModelResolutionError(ValueError):
    pass


def _model_to_dict(model: KimiModelSpec, created: int) -> Dict[str, Any]:
    return {
        "id": model.id,
        "object": "model",
        "created": created,
        "owned_by": "moonshot",
        "display_name": model.display_name,
        "description": model.description,
        "scenario": model.scenario,
        "thinking": model.thinking,
        "kimi_plus_id": model.kimi_plus_id,
        "agent_mode": model.agent_mode,
    }


def _requested_model(payload: Dict[str, Any], catalog: KimiModelCatalog) -> str:
    request_model = payload.get("model")
    if isinstance(request_model, str) and request_model.strip():
        return request_model.strip().lower()
    if Config.DEFAULT_MODEL.strip():
        return Config.DEFAULT_MODEL.strip().lower()
    return catalog.default_model_id


def _explicit_thinking(payload: Dict[str, Any]) -> Optional[bool]:
    if "enable_thinking" in payload and payload.get("enable_thinking") is not None:
        return bool(payload.get("enable_thinking"))
    if "reasoning" in payload and payload.get("reasoning") is not None:
        return bool(payload.get("reasoning"))
    return None


def _tools_enable_web_search(payload: Dict[str, Any]) -> bool:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return False

    for tool in tools:
        if not isinstance(tool, dict):
            continue
        tool_type = tool.get("type")
        if not isinstance(tool_type, str):
            continue
        normalized = tool_type.strip().lower()
        if normalized == "web_search" or normalized.startswith("web_search_preview"):
            return True
    return False


def _extract_web_search_enabled(payload: Dict[str, Any]) -> bool:
    if (
        payload.get("enable_web_search")
        or payload.get("web_search")
        or payload.get("search")
    ):
        return True

    if "web_search_options" in payload:
        value = payload.get("web_search_options")
        if value is not None and value is not False:
            return True

    return _tools_enable_web_search(payload)


def _extract_features(model: KimiModelSpec, payload: Dict[str, Any]) -> Dict[str, Any]:
    requested_thinking = _explicit_thinking(payload)
    if requested_thinking is not None and requested_thinking != model.thinking:
        raise ModelResolutionError(
            "`enable_thinking`/`reasoning` conflicts with the selected model"
        )

    enable_web_search = model.force_web_search or _extract_web_search_enabled(payload)
    if enable_web_search and not model.supports_web_search:
        raise ModelResolutionError(
            f"Model `{model.id}` does not support web search; "
            "use `kimi-k2.6` or `kimi-k2.6-thinking` instead"
        )

    return {
        "model": model.base_model_id,
        "request_model": model.id,
        "model_spec": model,
        "enable_thinking": model.thinking,
        "enable_web_search": enable_web_search,
    }


async def _resolve_model(payload: Dict[str, Any]) -> Dict[str, Any]:
    catalog = await get_model_catalog()
    requested_model = _requested_model(payload, catalog)
    model = catalog.by_id(requested_model)
    if model is None:
        raise ModelResolutionError(f"Model `{requested_model}` is not available")
    return _extract_features(model, payload)
