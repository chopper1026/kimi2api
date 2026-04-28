import json
import os
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .client import ChatCompletion, ChatCompletionChunk, Kimi2API, KimiAPIError

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
    raw_model = request_model or os.getenv("MODEL", DEFAULT_BASE_MODEL)
    return _parse_model_alias(raw_model)


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


def create_app() -> FastAPI:
    app = FastAPI(title=SERVER_NAME, version="1.2.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    async def verify_api_key(
        authorization: Optional[str] = Header(default=None),
    ) -> None:
        expected_api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
        if not expected_api_key:
            return

        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "message": "Missing bearer token",
                    "type": "invalid_request_error",
                },
            )

        token = authorization[len("Bearer ") :].strip()
        if token != expected_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "message": "Invalid API key",
                    "type": "invalid_request_error",
                },
            )

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

    @app.get("/")
    async def root() -> Dict[str, Any]:
        return {
            "object": "service",
            "name": SERVER_NAME,
            "version": app.version,
            "endpoints": ["/v1/models", "/v1/chat/completions", "/v1/completions", "/v1/responses"],
        }

    @app.get("/healthz")
    async def healthz() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/models", dependencies=[Depends(verify_api_key)])
    async def list_models() -> Dict[str, Any]:
        now = int(time.time())
        return {
            "object": "list",
            "data": [
                {
                    "id": model_id,
                    "object": "model",
                    "created": now,
                    "owned_by": "moonshot",
                }
                for model_id in DEFAULT_MODELS
            ],
        }

    @app.get("/v1/models/{model_id}", dependencies=[Depends(verify_api_key)])
    async def retrieve_model(model_id: str) -> Dict[str, Any]:
        now = int(time.time())
        return {
            "id": model_id,
            "object": "model",
            "created": now,
            "owned_by": "moonshot",
        }

    @app.post(
        "/v1/chat/completions",
        dependencies=[Depends(verify_api_key)],
        response_model=None,
    )
    async def create_chat_completion(request: Request) -> Any:
        payload = await request.json()
        messages = _normalize_messages(payload.get("messages"))
        if not messages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "`messages` is required", "type": "invalid_request_error"},
            )

        model_info = _resolve_model(payload.get("model"))
        features = _extract_features(model_info, payload)
        conversation_id = _extract_conversation_id(payload)
        stream = bool(payload.get("stream", False))

        if stream:
            return StreamingResponse(
                _create_streaming_chat_response(
                    model=features["model"],
                    response_model=features["request_model"],
                    messages=messages,
                    conversation_id=conversation_id,
                    enable_thinking=features["enable_thinking"],
                    enable_web_search=features["enable_web_search"],
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        async with Kimi2API() as client:
            result = await client.chat.completions.create(
                model=features["model"],
                messages=messages,
                stream=False,
                conversation_id=conversation_id,
                enable_thinking=features["enable_thinking"],
                enable_web_search=features["enable_web_search"],
            )
            result.model = features["request_model"]
            return _chat_completion_to_dict(result)

    @app.post("/v1/completions", dependencies=[Depends(verify_api_key)])
    async def create_completion(request: Request) -> Dict[str, Any]:
        payload = await request.json()
        messages = _normalize_messages(prompt=payload.get("prompt"))
        if not messages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "`prompt` is required", "type": "invalid_request_error"},
            )

        model_info = _resolve_model(payload.get("model"))
        features = _extract_features(model_info, payload)
        conversation_id = _extract_conversation_id(payload)

        async with Kimi2API() as client:
            result = await client.chat.completions.create(
                model=features["model"],
                messages=messages,
                conversation_id=conversation_id,
                enable_thinking=features["enable_thinking"],
                enable_web_search=features["enable_web_search"],
            )
        result.model = features["request_model"]

        text = result.choices[0].message.content or ""
        return {
            "id": result.id,
            "object": "text_completion",
            "created": result.created,
            "model": result.model,
            "choices": [
                {
                    "text": text,
                    "index": 0,
                    "logprobs": None,
                    "finish_reason": result.choices[0].finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "total_tokens": result.usage.total_tokens,
            },
        }

    @app.post(
        "/v1/responses",
        dependencies=[Depends(verify_api_key)],
        response_model=None,
    )
    async def create_response(request: Request) -> Any:
        payload = _response_api_to_chat_request(await request.json())
        messages = _normalize_messages(payload.get("messages"))
        if not messages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "`input` or `messages` is required", "type": "invalid_request_error"},
            )

        model_info = _resolve_model(payload.get("model"))
        features = _extract_features(model_info, payload)
        conversation_id = _extract_conversation_id(payload)
        stream = bool(payload.get("stream", False))

        if stream:
            return StreamingResponse(
                _create_streaming_responses_response(
                    model=features["model"],
                    response_model=features["request_model"],
                    messages=messages,
                    conversation_id=conversation_id,
                    enable_thinking=features["enable_thinking"],
                    enable_web_search=features["enable_web_search"],
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        async with Kimi2API() as client:
            result = await client.chat.completions.create(
                model=features["model"],
                messages=messages,
                stream=False,
                conversation_id=conversation_id,
                enable_thinking=features["enable_thinking"],
                enable_web_search=features["enable_web_search"],
            )
            result.model = features["request_model"]
            return _chat_to_responses_api_dict(_chat_completion_to_dict(result))

    @app.api_route(
        "/v1/{unsupported_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        dependencies=[Depends(verify_api_key)],
    )
    async def unsupported_endpoint(unsupported_path: str) -> JSONResponse:
        return _json_error(
            f"Endpoint /v1/{unsupported_path} is not implemented for Kimi backend",
            "unsupported_endpoint",
            status.HTTP_501_NOT_IMPLEMENTED,
        )

    return app
