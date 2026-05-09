import json
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from ..config import Config
from ..kimi import Kimi2API, KimiAPIError, ChatCompletion, ChatCompletionChunk
from ..core.keys import validate_api_key as _validate_api_key
from ..core.keys import get_key as _get_key
from ..core.logs import RequestLog, log_request

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# JSON error helper
# ---------------------------------------------------------------------------

def _json_error(message: str, error_type: str, code: int) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={
            "error": {
                "message": message,
                "type": error_type,
                "param": None,
                "code": error_type,
            }
        },
    )


# ---------------------------------------------------------------------------
# Message normalization
# ---------------------------------------------------------------------------

def _normalize_messages(
    messages: Optional[List[Dict[str, Any]]] = None,
    prompt: Optional[Union[str, List[str]]] = None,
) -> List[Dict[str, Any]]:
    if messages:
        return messages
    if prompt is None:
        return []
    if isinstance(prompt, list):
        prompt = "\n".join(str(item) for item in prompt)
    return [{"role": "user", "content": str(prompt)}]


# ---------------------------------------------------------------------------
# Model alias parsing
# ---------------------------------------------------------------------------

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
    suffixes: List[str] = []
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


# ---------------------------------------------------------------------------
# Conversation & feature extraction
# ---------------------------------------------------------------------------

def _extract_conversation_id(payload: Dict[str, Any]) -> Optional[str]:
    for key in ("conversation_id", "conversationId", "session_id", "sessionId"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        for key in ("conversation_id", "conversationId", "session_id", "sessionId"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return None


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


# ---------------------------------------------------------------------------
# Response conversion helpers
# ---------------------------------------------------------------------------

def _chat_completion_to_dict(response: ChatCompletion) -> Dict[str, Any]:
    choices: List[Dict[str, Any]] = []
    for choice in response.choices:
        message: Dict[str, Any] = {
            "role": choice.message.role,
            "content": choice.message.content,
        }
        if choice.message.reasoning_content:
            message["reasoning_content"] = choice.message.reasoning_content

        choices.append(
            {
                "index": choice.index,
                "message": message,
                "finish_reason": choice.finish_reason,
            }
        )

    return {
        "id": response.id,
        "object": response.object,
        "created": response.created,
        "model": response.model,
        "choices": choices,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        },
        "system_fingerprint": "fp_kimi2api",
    }


def _response_api_to_chat_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("messages"):
        return payload

    input_value = payload.get("input")
    messages: List[Dict[str, Any]] = []

    if isinstance(input_value, str):
        messages.append({"role": "user", "content": input_value})
    elif isinstance(input_value, list):
        for item in input_value:
            if isinstance(item, str):
                messages.append({"role": "user", "content": item})
                continue

            if not isinstance(item, dict):
                continue

            role = item.get("role", "user")
            content = item.get("content")

            if isinstance(content, list):
                text_parts: List[str] = []
                for part in content:
                    if isinstance(part, dict):
                        part_type = part.get("type")
                        if part_type in {"input_text", "text"}:
                            text_parts.append(str(part.get("text", "")))
                    elif isinstance(part, str):
                        text_parts.append(part)
                content = "\n".join(part for part in text_parts if part)

            messages.append({"role": role, "content": content or ""})

    payload = {**payload}
    payload["messages"] = messages
    return payload


def _chat_to_responses_api_dict(response: Dict[str, Any]) -> Dict[str, Any]:
    choice = response["choices"][0]
    message = choice["message"]
    text = message.get("content") or ""
    output_text = [{"type": "output_text", "text": text, "annotations": []}]
    if message.get("reasoning_content"):
        output_text.insert(
            0,
            {
                "type": "reasoning",
                "summary": [],
                "content": message["reasoning_content"],
            },
        )

    return {
        "id": response["id"],
        "object": "response",
        "created_at": response["created"],
        "model": response["model"],
        "output": [
            {
                "id": f"msg_{uuid.uuid4().hex}",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": output_text,
            }
        ],
        "output_text": text,
        "usage": response["usage"],
    }


# ---------------------------------------------------------------------------
# Streaming helpers
# ---------------------------------------------------------------------------

async def _stream_chat_chunks(
    stream: AsyncIterator[ChatCompletionChunk],
    response_model: str,
) -> AsyncIterator[str]:
    async for chunk in stream:
        payload = {
            "id": chunk.id,
            "object": chunk.object,
            "created": chunk.created,
            "model": response_model,
            "choices": chunk.choices,
            "system_fingerprint": "fp_kimi2api",
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


async def _stream_responses_chunks(
    stream: AsyncIterator[ChatCompletionChunk],
) -> AsyncIterator[str]:
    async for chunk in stream:
        delta = chunk.choices[0].get("delta", {})
        event: Dict[str, Any] = {
            "type": "response.output_text.delta",
            "sequence_number": 0,
            "item_id": f"msg_{chunk.id}",
            "output_index": 0,
            "content_index": 0,
            "delta": delta.get("content", ""),
        }

        if delta.get("reasoning_content"):
            event = {
                "type": "response.reasoning.delta",
                "sequence_number": 0,
                "item_id": f"msg_{chunk.id}",
                "output_index": 0,
                "content_index": 0,
                "delta": delta["reasoning_content"],
            }
        elif delta.get("role"):
            continue
        elif chunk.choices[0].get("finish_reason"):
            event = {"type": "response.completed", "response": {"id": chunk.id}}

        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


async def _create_streaming_chat_response(
    *,
    model: str,
    response_model: str,
    messages: List[Dict[str, Any]],
    conversation_id: Optional[str],
    enable_thinking: bool,
    enable_web_search: bool,
) -> AsyncIterator[str]:
    client = Kimi2API()
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            conversation_id=conversation_id,
            enable_thinking=enable_thinking,
            enable_web_search=enable_web_search,
        )
        async for chunk in _stream_chat_chunks(stream, response_model):
            yield chunk
    finally:
        await client.close()


async def _create_streaming_responses_response(
    *,
    model: str,
    response_model: str,
    messages: List[Dict[str, Any]],
    conversation_id: Optional[str],
    enable_thinking: bool,
    enable_web_search: bool,
) -> AsyncIterator[str]:
    client = Kimi2API()
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            conversation_id=conversation_id,
            enable_thinking=enable_thinking,
            enable_web_search=enable_web_search,
        )
        async for chunk in _stream_responses_chunks(stream):
            yield chunk
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Dependency: verify_api_key
# ---------------------------------------------------------------------------

async def verify_api_key(
    authorization: Optional[str] = Header(default=None),
) -> None:
    api_key = _validate_api_key(authorization)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Invalid API key" if authorization else "Missing bearer token",
                "type": "invalid_request_error",
            },
        )
