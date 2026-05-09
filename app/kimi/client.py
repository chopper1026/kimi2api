import asyncio
import json
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Union

import httpx

from ..config import Config as _Config
from ..core.token_manager import get_token_manager
from .protocol import (
    KIMI_CHAT_PATH,
    KIMI_RESEARCH_USAGE_PATH,
    KIMI_SCENARIO,
    KIMI_SUBSCRIPTION_PATH,
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionUsage,
    ConversationContext,
    KimiAPIError,
    Message,
    _encode_connect_request,
    _format_messages,
    generate_device_id,
    generate_session_id,
)


class _ChatNamespace:
    def __init__(self, client: "Kimi2API"):
        self.completions = ChatCompletions(client)


class ChatCompletions:
    def __init__(self, client: "Kimi2API"):
        self._client = client

    async def create(
        self,
        model: str = "kimi-k2.5",
        messages: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        stream: bool = False,
        stop: Optional[Union[str, List[str]]] = None,
        presence_penalty: float = 0.0,
        frequency_penalty: float = 0.0,
        user: Optional[str] = None,
        **kwargs: Any,
    ) -> Union[ChatCompletion, AsyncIterator[ChatCompletionChunk]]:
        del temperature, max_tokens, top_p, stop, presence_penalty, frequency_penalty, user

        raw_messages = messages or []
        parsed_messages = [
            Message(
                role=message.get("role", "user"),
                content=message.get("content", ""),
                name=message.get("name"),
                tool_call_id=message.get("tool_call_id"),
                tool_calls=message.get("tool_calls"),
            )
            for message in raw_messages
        ]
        if not parsed_messages:
            raise ValueError("messages must not be empty")

        request_conversation_id = kwargs.get("conversation_id") or str(uuid.uuid4())
        context = self._client._conversation_contexts.setdefault(
            request_conversation_id,
            ConversationContext(request_conversation_id=request_conversation_id),
        )

        request_body = self._client._build_chat_payload(
            model=model,
            messages=parsed_messages,
            context=context,
            enable_thinking=bool(kwargs.get("enable_thinking", False)),
            enable_web_search=bool(kwargs.get("enable_web_search", False)),
        )

        if stream:
            return self._client._stream_chat(
                request_body=request_body,
                model=model,
                context=context,
            )
        return await self._client._sync_chat(
            request_body=request_body,
            model=model,
            context=context,
        )


class Kimi2API:
    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 3,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ):
        del kwargs

        try:
            self._token_manager = get_token_manager()
        except RuntimeError as exc:
            raise KimiAPIError("Kimi token is not configured") from exc
        self._base_url = (base_url or _Config.KIMI_API_BASE).rstrip("/")
        self._timeout = timeout or _Config.TIMEOUT
        self._max_retries = max_retries
        self._device_id = generate_device_id()
        self._session_id = generate_session_id()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=True,
        )
        self._conversation_contexts: Dict[str, ConversationContext] = {}
        self.chat = _ChatNamespace(self)

    async def _get_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        from .protocol import FAKE_HEADERS

        token = await self._token_manager.get_access_token()
        headers = {
            **FAKE_HEADERS,
            "Origin": self._base_url,
            "X-Msh-Device-Id": self._device_id,
            "X-Msh-Session-Id": self._session_id,
            "Connect-Protocol-Version": "1",
            "Authorization": f"Bearer {token}",
        }
        if extra:
            headers.update(extra)
        return headers

    async def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        retryable_status_codes: Optional[List[int]] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        retryable_status_codes = retryable_status_codes or [408, 429, 500, 502, 503, 504]
        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.request(method, url, **kwargs)
                if response.status_code not in retryable_status_codes:
                    return response
                last_error = KimiAPIError(
                    f"request failed with retryable status {response.status_code}"
                )
                if attempt == self._max_retries:
                    return response
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                last_error = exc
                if attempt == self._max_retries:
                    break

            await asyncio.sleep(min(0.5 * attempt, 2.0))

        if last_error is None:
            raise KimiAPIError("request failed without a detailed error")
        raise KimiAPIError(f"request failed after {self._max_retries} attempts: {last_error}")

    async def validate_token(self) -> bool:
        try:
            data = await self.get_subscription()
            return bool(data and data.get("subscription"))
        except Exception:
            return False

    async def get_subscription(self) -> Optional[Dict[str, Any]]:
        try:
            headers = await self._get_headers()
            response = await self._request_with_retries(
                "POST",
                f"{self._base_url}{KIMI_SUBSCRIPTION_PATH}",
                json={},
                headers=headers,
                timeout=15.0,
            )
            if response.status_code != 200:
                return None
            return response.json()
        except Exception:
            return None

    async def get_research_usage(self) -> Optional[Dict[str, Any]]:
        try:
            headers = await self._get_headers()
            response = await self._request_with_retries(
                "GET",
                f"{self._base_url}{KIMI_RESEARCH_USAGE_PATH}",
                headers=headers,
                timeout=15.0,
            )
            if response.status_code != 200:
                return None
            return response.json()
        except Exception:
            return None

    def _build_chat_payload(
        self,
        model: str,
        messages: List[Message],
        context: ConversationContext,
        enable_thinking: bool,
        enable_web_search: bool,
    ) -> Dict[str, Any]:
        content = _format_messages(messages)
        if not content:
            raise ValueError("messages content must not be empty")

        message: Dict[str, Any] = {
            "role": "user",
            "blocks": [
                {
                    "message_id": "",
                    "text": {"content": content},
                }
            ],
            "scenario": KIMI_SCENARIO,
        }
        if context.last_assistant_message_id:
            message["parent_id"] = context.last_assistant_message_id

        payload: Dict[str, Any] = {
            "scenario": KIMI_SCENARIO,
            "tools": (
                [{"type": "TOOL_TYPE_SEARCH", "search": {}}]
                if enable_web_search
                else []
            ),
            "message": message,
            "options": {
                "thinking": enable_thinking,
            },
        }
        if context.remote_chat_id:
            payload["chat_id"] = context.remote_chat_id
        return payload

    async def _raise_for_response(self, response: httpx.Response) -> None:
        if response.status_code == 200:
            return
        body = (await response.aread()).decode("utf-8", errors="ignore")[:100]
        raise KimiAPIError(
            f"upstream error {response.status_code}: {body or '<empty>'}"
        )

    def _update_context_from_event(
        self, context: ConversationContext, event: Dict[str, Any]
    ) -> None:
        if event.get("chat", {}).get("id"):
            context.remote_chat_id = event["chat"]["id"]
        if (
            event.get("message", {}).get("role") == "assistant"
            and event.get("message", {}).get("id")
        ):
            context.last_assistant_message_id = event["message"]["id"]

    def _extract_explicit_phase(self, event: Dict[str, Any]) -> Optional[str]:
        from .protocol import THINKING_STAGE_NAME

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

    def _extract_phase(
        self, event: Dict[str, Any], current_phase: Optional[str]
    ) -> Optional[str]:
        return self._extract_explicit_phase(event) or current_phase

    def _extract_delta(
        self, event: Dict[str, Any], current_phase: Optional[str]
    ) -> Dict[str, Optional[str]]:
        if event.get("heartbeat"):
            return {"phase": current_phase, "content": None, "reasoning_content": None}

        explicit_phase = self._extract_explicit_phase(event)
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
            return {"phase": phase if explicit_phase else "answer", "content": content, "reasoning_content": None}

        content = event.get("block", {}).get("text", {}).get("content")
        if explicit_phase == "thinking":
            return {"phase": phase, "content": None, "reasoning_content": content}
        if content is not None:
            return {"phase": phase if explicit_phase else "answer", "content": content, "reasoning_content": None}
        return {"phase": phase, "content": None, "reasoning_content": None}

    async def _iter_grpc_events(
        self, response: httpx.Response, context: ConversationContext
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
                    raise KimiAPIError(error.get("message") or json.dumps(error, ensure_ascii=False))

                self._update_context_from_event(context, event)
                yield event

            if offset:
                del buffer[:offset]

    async def _sync_chat(
        self,
        request_body: Dict[str, Any],
        model: str,
        context: ConversationContext,
    ) -> ChatCompletion:
        content = _encode_connect_request(request_body)
        reasoning_parts: List[str] = []
        content_parts: List[str] = []
        created = int(time.time())
        current_phase: Optional[str] = None

        last_error: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 1):
            reasoning_parts.clear()
            content_parts.clear()
            current_phase = None
            try:
                headers = await self._get_headers({"Content-Type": "application/connect+json"})
                async with self._client.stream(
                    "POST",
                    f"{self._base_url}{KIMI_CHAT_PATH}",
                    content=content,
                    headers=headers,
                    timeout=self._timeout,
                ) as response:
                    if response.status_code == 401:
                        await self._token_manager.invalidate_and_retry()
                        headers = await self._get_headers({"Content-Type": "application/connect+json"})
                        async with self._client.stream(
                            "POST",
                            f"{self._base_url}{KIMI_CHAT_PATH}",
                            content=content,
                            headers=headers,
                            timeout=self._timeout,
                        ) as response2:
                            await self._raise_for_response(response2)
                            async for event in self._iter_grpc_events(response2, context):
                                delta = self._extract_delta(event, current_phase)
                                current_phase = delta["phase"]
                                if delta["reasoning_content"]:
                                    reasoning_parts.append(delta["reasoning_content"])
                                if delta["content"]:
                                    content_parts.append(delta["content"])
                                if "done" in event:
                                    break
                        break

                    await self._raise_for_response(response)

                    async for event in self._iter_grpc_events(response, context):
                        delta = self._extract_delta(event, current_phase)
                        current_phase = delta["phase"]
                        if delta["reasoning_content"]:
                            reasoning_parts.append(delta["reasoning_content"])
                        if delta["content"]:
                            content_parts.append(delta["content"])
                        if "done" in event:
                            break
                break
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError, KimiAPIError) as exc:
                last_error = exc
                if attempt == self._max_retries:
                    raise KimiAPIError(
                        f"chat completion failed after {self._max_retries} attempts: {exc}"
                    ) from exc
                await asyncio.sleep(min(0.5 * attempt, 2.0))

        if last_error and not content_parts and not reasoning_parts:
            raise KimiAPIError(str(last_error))

        final_id = context.remote_chat_id or context.request_conversation_id
        message = ChatCompletionMessage(
            role="assistant",
            content="".join(content_parts).strip() or None,
            reasoning_content="".join(reasoning_parts).strip() or None,
        )
        return ChatCompletion(
            id=final_id,
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

    def _stream_chat(
        self,
        request_body: Dict[str, Any],
        model: str,
        context: ConversationContext,
    ) -> AsyncIterator[ChatCompletionChunk]:
        content = _encode_connect_request(request_body)

        async def generator() -> AsyncIterator[ChatCompletionChunk]:
            created = int(time.time())
            sent_role = False
            sent_stop = False
            current_phase: Optional[str] = None

            headers = await self._get_headers({"Content-Type": "application/connect+json"})
            async with self._client.stream(
                "POST",
                f"{self._base_url}{KIMI_CHAT_PATH}",
                content=content,
                headers=headers,
                timeout=self._timeout,
            ) as response:
                if response.status_code == 401:
                    await self._token_manager.invalidate_and_retry()
                    headers = await self._get_headers({"Content-Type": "application/connect+json"})
                    async with self._client.stream(
                        "POST",
                        f"{self._base_url}{KIMI_CHAT_PATH}",
                        content=content,
                        headers=headers,
                        timeout=self._timeout,
                    ) as response:
                        async for event in self._iter_grpc_events(response, context):
                            chunk_id = context.remote_chat_id or context.request_conversation_id
                            if not sent_role:
                                sent_role = True
                                yield ChatCompletionChunk(
                                    id=chunk_id,
                                    created=created,
                                    model=model,
                                    choices=[{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                                )

                            delta = self._extract_delta(event, current_phase)
                            current_phase = delta["phase"]

                            if delta["reasoning_content"]:
                                yield ChatCompletionChunk(
                                    id=chunk_id,
                                    created=created,
                                    model=model,
                                    choices=[
                                        {
                                            "index": 0,
                                            "delta": {"reasoning_content": delta["reasoning_content"]},
                                            "finish_reason": None,
                                        }
                                    ],
                                )

                            if delta["content"]:
                                yield ChatCompletionChunk(
                                    id=chunk_id,
                                    created=created,
                                    model=model,
                                    choices=[
                                        {
                                            "index": 0,
                                            "delta": {"content": delta["content"]},
                                            "finish_reason": None,
                                        }
                                    ],
                                )

                            if "done" in event:
                                sent_stop = True
                                yield ChatCompletionChunk(
                                    id=chunk_id,
                                    created=created,
                                    model=model,
                                    choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}],
                                )
                                break
                        if not sent_stop:
                            chunk_id = context.remote_chat_id or context.request_conversation_id
                            yield ChatCompletionChunk(
                                id=chunk_id,
                                created=created,
                                model=model,
                                choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}],
                            )
                        return

                await self._raise_for_response(response)

                async for event in self._iter_grpc_events(response, context):
                    chunk_id = context.remote_chat_id or context.request_conversation_id
                    if not sent_role:
                        sent_role = True
                        yield ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=model,
                            choices=[{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                        )

                    delta = self._extract_delta(event, current_phase)
                    current_phase = delta["phase"]

                    if delta["reasoning_content"]:
                        yield ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=model,
                            choices=[
                                {
                                    "index": 0,
                                    "delta": {"reasoning_content": delta["reasoning_content"]},
                                    "finish_reason": None,
                                }
                            ],
                        )

                    if delta["content"]:
                        yield ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=model,
                            choices=[
                                {
                                    "index": 0,
                                    "delta": {"content": delta["content"]},
                                    "finish_reason": None,
                                }
                            ],
                        )

                    if "done" in event:
                        sent_stop = True
                        yield ChatCompletionChunk(
                            id=chunk_id,
                            created=created,
                            model=model,
                            choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}],
                        )
                        break

            if not sent_stop:
                chunk_id = context.remote_chat_id or context.request_conversation_id
                yield ChatCompletionChunk(
                    id=chunk_id,
                    created=created,
                    model=model,
                    choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}],
                )

        return generator()

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "Kimi2API":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


def create_client(
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    max_retries: int = 3,
    base_url: Optional[str] = None,
) -> Kimi2API:
    del api_key
    return Kimi2API(
        timeout=timeout,
        max_retries=max_retries,
        base_url=base_url,
    )
