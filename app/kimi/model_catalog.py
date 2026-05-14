import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..config import Config
from ..core.kimi_account_pool import get_account_pool
from ..core.token_manager import get_token_manager
from .protocol import KimiAPIError
from .transport import (
    build_kimi_headers,
    classify_upstream_status,
    get_shared_transport,
    load_or_create_client_identity,
    process_session_id,
    retry_after_seconds,
)

KIMI_AVAILABLE_MODELS_PATH = (
    "/apiv2/kimi.gateway.config.v1.ConfigService/GetAvailableModels"
)
MODEL_CATALOG_CACHE_SECONDS = 300


@dataclass(frozen=True)
class KimiModelSpec:
    id: str
    display_name: str
    scenario: str
    thinking: bool = False
    supports_web_search: bool = False
    base_model_id: str = ""
    force_web_search: bool = False
    kimi_plus_id: str = ""
    agent_mode: str = ""
    description: str = ""
    input_placeholder: str = ""

    def __post_init__(self) -> None:
        if self.scenario == "SCENARIO_K2D5" and not self.supports_web_search:
            object.__setattr__(self, "supports_web_search", True)
        if not self.base_model_id:
            object.__setattr__(self, "base_model_id", self.id)


@dataclass(frozen=True)
class KimiModelCatalog:
    models: List[KimiModelSpec]
    default_model_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "models", _with_search_aliases(self.models))

    def by_id(self, model_id: str) -> Optional[KimiModelSpec]:
        normalized = model_id.strip().lower()
        for model in self.models:
            if model.id == normalized:
                return model
        return None

    def default_model(self) -> KimiModelSpec:
        model = self.by_id(self.default_model_id)
        if model is not None:
            return model
        if not self.models:
            raise KimiAPIError("Kimi model catalog is empty")
        return self.models[0]


_catalog_cache: Optional[Tuple[str, float, KimiModelCatalog]] = None


def _raw_value(source: Dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in source:
            return source[name]
    return None


def _model_version_slug(display_name: str, scenario: str) -> str:
    match = re.search(r"\bK\s*([0-9]+(?:\.[0-9]+)?)\b", display_name, re.IGNORECASE)
    if match:
        return "k" + match.group(1)
    if scenario == "SCENARIO_K2":
        return "k2"
    if scenario == "SCENARIO_K2D5":
        return "k2.6"
    return scenario.lower().replace("scenario_", "").replace("_", "-")


def _model_suffix(
    *,
    scenario: str,
    display_name: str,
    thinking: bool,
    kimi_plus_id: str,
    agent_mode: str,
) -> str:
    normalized_name = display_name.lower()
    if agent_mode == "TYPE_ULTRA" or "swarm" in normalized_name:
        return "agent-swarm"
    if scenario == "SCENARIO_OK_COMPUTER" or kimi_plus_id or "agent" in normalized_name:
        return "agent"
    if thinking:
        return "thinking"
    return ""


def _model_id(raw_model: Dict[str, Any]) -> str:
    scenario = str(_raw_value(raw_model, "scenario") or "")
    display_name = str(_raw_value(raw_model, "displayName", "display_name") or scenario)
    thinking = bool(_raw_value(raw_model, "thinking"))
    kimi_plus_id = str(_raw_value(raw_model, "kimiPlusId", "kimi_plus_id") or "")
    agent_mode = str(_raw_value(raw_model, "agentMode", "agent_mode") or "")
    version = _model_version_slug(display_name, scenario)
    suffix = _model_suffix(
        scenario=scenario,
        display_name=display_name,
        thinking=thinking,
        kimi_plus_id=kimi_plus_id,
        agent_mode=agent_mode,
    )
    return f"kimi-{version}" + (f"-{suffix}" if suffix else "")


def _model_spec(raw_model: Dict[str, Any]) -> KimiModelSpec:
    scenario = str(_raw_value(raw_model, "scenario") or "")
    display_name = str(_raw_value(raw_model, "displayName", "display_name") or scenario)
    return KimiModelSpec(
        id=_model_id(raw_model),
        display_name=display_name,
        scenario=scenario,
        thinking=bool(_raw_value(raw_model, "thinking")),
        supports_web_search=scenario == "SCENARIO_K2D5",
        kimi_plus_id=str(_raw_value(raw_model, "kimiPlusId", "kimi_plus_id") or ""),
        agent_mode=str(_raw_value(raw_model, "agentMode", "agent_mode") or ""),
        description=str(_raw_value(raw_model, "description") or ""),
        input_placeholder=str(
            _raw_value(raw_model, "inputPlaceholder", "input_placeholder") or ""
        ),
    )


def _dedupe_models(models: Iterable[KimiModelSpec]) -> List[KimiModelSpec]:
    deduped: Dict[str, KimiModelSpec] = {}
    for model in models:
        if model.id and model.id not in deduped:
            deduped[model.id] = model
    return list(deduped.values())


def _search_alias_id(model_id: str) -> str:
    return f"{model_id}-search"


def _search_alias(model: KimiModelSpec) -> KimiModelSpec:
    return KimiModelSpec(
        id=_search_alias_id(model.id),
        display_name=f"{model.display_name} Search",
        scenario=model.scenario,
        thinking=model.thinking,
        supports_web_search=True,
        base_model_id=model.id,
        force_web_search=True,
        kimi_plus_id=model.kimi_plus_id,
        agent_mode=model.agent_mode,
        description=(
            f"{model.description} with web search"
            if model.description
            else "Web search enabled"
        ),
        input_placeholder=model.input_placeholder,
    )


def _with_search_aliases(models: List[KimiModelSpec]) -> List[KimiModelSpec]:
    result = list(models)
    existing_ids = {model.id for model in result}
    for model in models:
        if (
            not model.supports_web_search
            or model.force_web_search
            or model.id.endswith("-search")
        ):
            continue
        alias_id = _search_alias_id(model.id)
        if alias_id in existing_ids:
            continue
        result.append(_search_alias(model))
        existing_ids.add(alias_id)
    return result


def _default_model_id(
    models: List[KimiModelSpec],
    default_scenario: Dict[str, Any],
) -> str:
    scenario = str(_raw_value(default_scenario, "scenario") or "")
    has_thinking = "thinking" in default_scenario
    thinking = bool(_raw_value(default_scenario, "thinking"))
    for model in models:
        if model.scenario != scenario:
            continue
        if has_thinking and model.thinking != thinking:
            continue
        return model.id
    if models:
        return models[0].id
    raise KimiAPIError("Kimi model catalog is empty")


def parse_model_catalog(data: Dict[str, Any]) -> KimiModelCatalog:
    raw_models = data.get("availableModels") or data.get("available_models") or []
    if not isinstance(raw_models, list):
        raise KimiAPIError("Kimi model catalog response is invalid")
    models = _dedupe_models(
        _model_spec(raw_model)
        for raw_model in raw_models
        if isinstance(raw_model, dict)
    )
    default_scenario = data.get("defaultScenario") or data.get("default_scenario") or {}
    if not isinstance(default_scenario, dict):
        default_scenario = {}
    return KimiModelCatalog(
        models=models,
        default_model_id=_default_model_id(models, default_scenario),
    )


async def _optional_access_token() -> Optional[str]:
    pool = get_account_pool(required=False)
    if pool is not None and pool.configured:
        try:
            async with pool.acquire() as runtime:
                return await runtime.token_manager.get_access_token()
        except Exception:
            return None
    try:
        return await get_token_manager().get_access_token()
    except RuntimeError:
        return None


async def fetch_model_catalog(base_url: Optional[str] = None) -> KimiModelCatalog:
    resolved_base_url = (base_url or Config.KIMI_API_BASE).rstrip("/")
    token = await _optional_access_token()
    identity = load_or_create_client_identity()
    headers = build_kimi_headers(
        base_url=resolved_base_url,
        token=token,
        device_id=identity.device_id,
        session_id=process_session_id(),
        extra={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )

    transport = get_shared_transport(base_url=resolved_base_url, timeout=15.0)
    response = await transport.request(
        "POST",
        KIMI_AVAILABLE_MODELS_PATH,
        json={},
        headers=headers,
    )
    if response.status_code != 200:
        raise KimiAPIError(
            f"failed to fetch Kimi model catalog: {response.status_code}",
            upstream_status_code=response.status_code,
            upstream_error_type=classify_upstream_status(response.status_code),
            retry_after=retry_after_seconds(response.headers),
        )
    return parse_model_catalog(response.json())


async def get_model_catalog(
    *, force_refresh: bool = False, base_url: Optional[str] = None
) -> KimiModelCatalog:
    global _catalog_cache

    resolved_base_url = (base_url or Config.KIMI_API_BASE).rstrip("/")
    now = time.time()
    if not force_refresh and _catalog_cache is not None:
        cache_base_url, expires_at, catalog = _catalog_cache
        if cache_base_url == resolved_base_url and now < expires_at:
            return catalog

    catalog = await fetch_model_catalog(resolved_base_url)
    _catalog_cache = (
        resolved_base_url,
        now + MODEL_CATALOG_CACHE_SECONDS,
        catalog,
    )
    return catalog


def clear_model_catalog_cache() -> None:
    global _catalog_cache
    _catalog_cache = None
