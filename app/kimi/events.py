import json
from typing import Any, AsyncIterator, Dict, Optional

from .protocol import ConversationContext, KimiAPIError, THINKING_STAGE_NAME


def update_context_from_event(
    context: ConversationContext,
    event: Dict[str, Any],
) -> None:
    if event.get("chat", {}).get("id"):
        context.remote_chat_id = event["chat"]["id"]
    if (
        event.get("message", {}).get("role") == "assistant"
        and event.get("message", {}).get("id")
    ):
        context.last_assistant_message_id = event["message"]["id"]


def extract_explicit_phase(event: Dict[str, Any]) -> Optional[str]:
    stages = event.get("block", {}).get("multiStage", {}).get("stages", [])
    if stages:
        first_stage = stages[0]
        if first_stage.get("name") == THINKING_STAGE_NAME:
            return "answer" if first_stage.get("status") == "completed" else "thinking"

    flags = event.get("block", {}).get("text", {}).get("flags")
    if flags == "thinking":
        return "thinking"
    if flags == "answer":
        return "answer"
    return None


def extract_delta(
    event: Dict[str, Any],
    current_phase: Optional[str],
) -> Dict[str, Optional[str]]:
    if event.get("heartbeat"):
        return {"phase": current_phase, "content": None, "reasoning_content": None}

    explicit_phase = extract_explicit_phase(event)
    phase = explicit_phase or current_phase
    mask = event.get("mask", "")

    if "block.think" in mask:
        return {
            "phase": phase or "thinking",
            "content": None,
            "reasoning_content": event.get("block", {}).get("think", {}).get("content"),
        }

    if "block.text" in mask:
        content = event.get("block", {}).get("text", {}).get("content")
        if explicit_phase == "thinking":
            return {"phase": phase, "content": None, "reasoning_content": content}
        return {
            "phase": phase if explicit_phase else "answer",
            "content": content,
            "reasoning_content": None,
        }

    content = event.get("block", {}).get("text", {}).get("content")
    if explicit_phase == "thinking":
        return {"phase": phase, "content": None, "reasoning_content": content}
    if content is not None:
        return {
            "phase": phase if explicit_phase else "answer",
            "content": content,
            "reasoning_content": None,
        }
    return {"phase": phase, "content": None, "reasoning_content": None}


async def iter_grpc_events(
    response: Any,
    context: ConversationContext,
) -> AsyncIterator[Dict[str, Any]]:
    buffer = bytearray()
    async for chunk in response.aiter_bytes():
        buffer.extend(chunk)
        offset = 0

        while offset + 5 <= len(buffer):
            flag = buffer[offset]
            length = int.from_bytes(buffer[offset + 1 : offset + 5], "big")
            frame_end = offset + 5 + length
            if frame_end > len(buffer):
                break

            payload = bytes(buffer[offset + 5 : frame_end])
            offset = frame_end

            if flag & 0x80:
                continue

            text = payload.decode("utf-8", errors="ignore").strip()
            if not text:
                continue

            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                continue

            if event.get("error"):
                error = event["error"]
                raise KimiAPIError(
                    error.get("message") or json.dumps(error, ensure_ascii=False)
                )

            update_context_from_event(context, event)
            yield event

        if offset:
            del buffer[:offset]
