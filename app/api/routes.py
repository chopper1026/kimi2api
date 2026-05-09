import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from ..kimi import Kimi2API

from .deps import (
    DEFAULT_MODELS,
    _chat_completion_to_dict,
    _chat_to_responses_api_dict,
    _create_streaming_chat_response,
    _create_streaming_responses_response,
    _extract_conversation_id,
    _extract_features,
    _json_error,
    _normalize_messages,
    _resolve_model,
    _response_api_to_chat_request,
    verify_api_key,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@router.get("/v1/models", dependencies=[Depends(verify_api_key)])
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


@router.get("/v1/models/{model_id}", dependencies=[Depends(verify_api_key)])
async def retrieve_model(model_id: str) -> Dict[str, Any]:
    now = int(time.time())
    return {
        "id": model_id,
        "object": "model",
        "created": now,
        "owned_by": "moonshot",
    }


# ---------------------------------------------------------------------------
# Chat completions
# ---------------------------------------------------------------------------

@router.post(
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
    request.state.request_model = features["request_model"]
    conversation_id = _extract_conversation_id(payload)
    stream = bool(payload.get("stream", False))

    if stream:
        return StreamingResponse(
            _create_streaming_chat_response(
                request=request,
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


# ---------------------------------------------------------------------------
# Completions (legacy)
# ---------------------------------------------------------------------------

@router.post("/v1/completions", dependencies=[Depends(verify_api_key)])
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
    request.state.request_model = features["request_model"]
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


# ---------------------------------------------------------------------------
# Responses API
# ---------------------------------------------------------------------------

@router.post(
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
    request.state.request_model = features["request_model"]
    conversation_id = _extract_conversation_id(payload)
    stream = bool(payload.get("stream", False))

    if stream:
        return StreamingResponse(
            _create_streaming_responses_response(
                request=request,
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


# ---------------------------------------------------------------------------
# Unsupported endpoints catch-all
# ---------------------------------------------------------------------------

@router.api_route(
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
