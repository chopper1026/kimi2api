import uuid
from typing import Any, Dict, List, Optional, Union

from ..kimi import ChatCompletion


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
