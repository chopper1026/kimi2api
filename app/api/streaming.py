import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import Request

from ..kimi import Kimi2API, KimiAPIError, ChatCompletionChunk
from ..kimi.model_catalog import KimiModelSpec

logger = logging.getLogger("kimi2api.api")


def _stream_error_chunk(message: str, error_type: str = "api_error") -> str:
    payload = {
        "error": {
            "message": message,
            "type": error_type,
            "param": None,
            "code": error_type,
        }
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _mark_stream_error(request: Optional[Request], message: str = "") -> None:
    if request is not None:
        request.state.stream_error = True
        request.state.stream_error_message = message


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
    request: Optional[Request] = None,
    model: str,
    model_spec: KimiModelSpec,
    response_model: str,
    messages: List[Dict[str, Any]],
    conversation_id: Optional[str],
    enable_web_search: bool,
) -> AsyncIterator[str]:
    client: Optional[Kimi2API] = None
    try:
        client = Kimi2API()
        stream = await client.chat.completions.create(
            model=model,
            model_spec=model_spec,
            messages=messages,
            stream=True,
            conversation_id=conversation_id,
            enable_web_search=enable_web_search,
        )
        async for chunk in _stream_chat_chunks(stream, response_model):
            yield chunk
    except KimiAPIError as exc:
        _mark_stream_error(request, str(exc))
        logger.warning("Streaming chat request failed: %s", exc)
        yield _stream_error_chunk(str(exc))
        yield "data: [DONE]\n\n"
    except Exception:
        _mark_stream_error(request, "Streaming request failed")
        logger.exception("Unexpected streaming chat request failure")
        yield _stream_error_chunk("Streaming request failed")
        yield "data: [DONE]\n\n"
    finally:
        if client is not None:
            await client.close()


async def _create_streaming_responses_response(
    *,
    request: Optional[Request] = None,
    model: str,
    model_spec: KimiModelSpec,
    response_model: str,
    messages: List[Dict[str, Any]],
    conversation_id: Optional[str],
    enable_web_search: bool,
) -> AsyncIterator[str]:
    client: Optional[Kimi2API] = None
    try:
        client = Kimi2API()
        stream = await client.chat.completions.create(
            model=model,
            model_spec=model_spec,
            messages=messages,
            stream=True,
            conversation_id=conversation_id,
            enable_web_search=enable_web_search,
        )
        async for chunk in _stream_responses_chunks(stream):
            yield chunk
    except KimiAPIError as exc:
        _mark_stream_error(request, str(exc))
        logger.warning("Streaming responses request failed: %s", exc)
        yield _stream_error_chunk(str(exc))
        yield "data: [DONE]\n\n"
    except Exception:
        _mark_stream_error(request, "Streaming request failed")
        logger.exception("Unexpected streaming responses request failure")
        yield _stream_error_chunk("Streaming request failed")
        yield "data: [DONE]\n\n"
    finally:
        if client is not None:
            await client.close()
