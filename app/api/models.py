from typing import Any, Dict, Optional

from ..config import Config

SERVER_NAME = "Kimi2API"
DEFAULT_BASE_MODEL = "kimi-k2.5"
BASE_MODELS = ["kimi-k2.5", "kimi-k2"]
DEFAULT_MODELS = [
    "kimi-k2.5",
    "kimi-k2.5-thinking",
    "kimi-k2.5-search",
    "kimi-k2.5-thinking-search",
    "kimi-2.6-fast",
    "kimi-2.6-thinking",
    "kimi-2.6-search",
    "kimi-2.6-thinking-search",
    "kimi-k2",
    "kimi-k2-thinking",
    "kimi-k2-search",
    "kimi-k2-thinking-search",
    "kimi-thinking",
    "kimi-search",
    "kimi-thinking-search",
]


def _parse_model_alias(model: str) -> Dict[str, Any]:
    normalized_model = (model or DEFAULT_BASE_MODEL).strip().lower()
    enable_thinking = False
    enable_web_search = False

    alias_map = {
        "kimi-thinking": (DEFAULT_BASE_MODEL, True, False),
        "kimi-search": (DEFAULT_BASE_MODEL, False, True),
        "kimi-thinking-search": (DEFAULT_BASE_MODEL, True, True),
        "kimi-search-thinking": (DEFAULT_BASE_MODEL, True, True),
        "kimi-2.6-fast": ("kimi-2.6-fast", False, False),
        "kimi-2.6-thinking": ("kimi-2.6-thinking", True, False),
        "kimi-2.6-search": ("kimi-2.6-search", False, True),
        "kimi-2.6-thinking-search": ("kimi-2.6-thinking-search", True, True),
        "kimi-2.6-search-thinking": ("kimi-2.6-thinking-search", True, True),
    }
    if normalized_model in alias_map:
        base_model, enable_thinking, enable_web_search = alias_map[normalized_model]
        return {
            "request_model": normalized_model,
            "base_model": base_model,
            "enable_thinking": enable_thinking,
            "enable_web_search": enable_web_search,
        }

    model_parts = [part for part in normalized_model.split("-") if part]
    feature_parts = {"thinking", "think", "reasoning", "search"}
    suffixes = []
    while model_parts and model_parts[-1] in feature_parts:
        suffixes.append(model_parts.pop())

    base_model = "-".join(model_parts) if model_parts else DEFAULT_BASE_MODEL
    if base_model not in BASE_MODELS:
        base_model = normalized_model
        suffixes = []

    for suffix in suffixes:
        if suffix in {"thinking", "think", "reasoning"}:
            enable_thinking = True
        if suffix == "search":
            enable_web_search = True

    return {
        "request_model": normalized_model,
        "base_model": base_model,
        "enable_thinking": enable_thinking,
        "enable_web_search": enable_web_search,
    }


def _resolve_model(request_model: Optional[str]) -> Dict[str, Any]:
    raw_model = request_model or Config.DEFAULT_MODEL
    return _parse_model_alias(raw_model)


def _extract_features(model_info: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    enable_thinking = bool(payload.get("enable_thinking") or payload.get("reasoning"))
    enable_web_search = bool(
        payload.get("enable_web_search")
        or payload.get("web_search")
        or payload.get("search")
    )

    if model_info.get("enable_thinking"):
        enable_thinking = True
    if model_info.get("enable_web_search"):
        enable_web_search = True

    return {
        "model": model_info["base_model"],
        "request_model": model_info["request_model"],
        "enable_thinking": enable_thinking,
        "enable_web_search": enable_web_search,
    }
