import time
from typing import List, Optional

from .protocol import (
    ChatCompletion,
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionMessage,
    ChatCompletionUsage,
)


def build_chat_completion(
    *,
    completion_id: str,
    created: int,
    model: str,
    content_parts: List[str],
    reasoning_parts: List[str],
) -> ChatCompletion:
    message = ChatCompletionMessage(
        role="assistant",
        content="".join(content_parts).strip() or None,
        reasoning_content="".join(reasoning_parts).strip() or None,
    )
    return ChatCompletion(
        id=completion_id,
        created=created,
        model=model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=message,
                finish_reason="stop",
            )
        ],
        usage=ChatCompletionUsage(
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        ),
    )


def role_chunk(*, chunk_id: str, created: int, model: str) -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id=chunk_id,
        created=created,
        model=model,
        choices=[{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    )


def content_chunk(
    *,
    chunk_id: str,
    created: int,
    model: str,
    content: str,
) -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id=chunk_id,
        created=created,
        model=model,
        choices=[{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    )


def reasoning_chunk(
    *,
    chunk_id: str,
    created: int,
    model: str,
    reasoning_content: str,
) -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id=chunk_id,
        created=created,
        model=model,
        choices=[
            {
                "index": 0,
                "delta": {"reasoning_content": reasoning_content},
                "finish_reason": None,
            }
        ],
    )


def stop_chunk(*, chunk_id: str, created: int, model: str) -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id=chunk_id,
        created=created,
        model=model,
        choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}],
    )


def new_created_timestamp(created: Optional[int] = None) -> int:
    return created or int(time.time())
