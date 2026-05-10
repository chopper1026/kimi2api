import asyncio
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Union

import httpx

from ..config import Config as _Config
from ..core.token_manager import get_token_manager
from .chunks import (
    build_chat_completion,
    content_chunk,
    reasoning_chunk,
    role_chunk,
    stop_chunk,
)
from .events import (
    extract_delta,
    extract_explicit_phase,
    iter_grpc_events,
    update_context_from_event,
)
from .model_catalog import KimiModelSpec
from .protocol import (
    KIMI_CHAT_PATH,
    KIMI_RESEARCH_USAGE_PATH,
    KIMI_SUBSCRIPTION_PATH,
    ChatCompletion,
    ChatCompletionChunk,
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
            model_spec=kwargs.get("model_spec") or KimiModelSpec(
                id=model,
                display_name=model,
                scenario=kwargs.get("scenario", "SCENARIO_K2D5"),
                thinking=bool(kwargs.get("enable_thinking", False)),
            ),
            messages=parsed_messages,
            context=context,
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
        model_spec: KimiModelSpec,
        messages: List[Any],
        context: ConversationContext,
        enable_web_search: bool,
    ) -> Dict[str, Any]:
        parsed_messages = [
            message
            if isinstance(message, Message)
            else Message(
                role=message.get("role", "user"),
                content=message.get("content", ""),
                name=message.get("name"),
                tool_call_id=message.get("tool_call_id"),
                tool_calls=message.get("tool_calls"),
            )
            for message in messages
        ]
        content = _format_messages(parsed_messages)
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
            "scenario": model_spec.scenario,
        }
        if context.last_assistant_message_id:
            message["parent_id"] = context.last_assistant_message_id

        payload: Dict[str, Any] = {
            "scenario": model_spec.scenario,
            "tools": (
                [{"type": "TOOL_TYPE_SEARCH", "search": {}}]
                if enable_web_search
                else []
            ),
            "message": message,
            "options": {
                "thinking": model_spec.thinking,
            },
        }
        if model_spec.kimi_plus_id:
            payload["kimiplusId"] = model_spec.kimi_plus_id
        if model_spec.agent_mode:
            payload["agentMode"] = model_spec.agent_mode
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
        update_context_from_event(context, event)

    def _extract_explicit_phase(self, event: Dict[str, Any]) -> Optional[str]:
        return extract_explicit_phase(event)

    def _extract_phase(
        self, event: Dict[str, Any], current_phase: Optional[str]
    ) -> Optional[str]:
        return self._extract_explicit_phase(event) or current_phase

    def _extract_delta(
        self, event: Dict[str, Any], current_phase: Optional[str]
    ) -> Dict[str, Optional[str]]:
        return extract_delta(event, current_phase)

    async def _iter_grpc_events(
        self, response: httpx.Response, context: ConversationContext
    ) -> AsyncIterator[Dict[str, Any]]:
        async for event in iter_grpc_events(response, context):
            yield event

    async def _iter_chat_events(
        self,
        content: bytes,
        context: ConversationContext,
    ) -> AsyncIterator[Dict[str, Any]]:
        headers = await self._get_headers({"Content-Type": "application/connect+json"})
        async with self._client.stream(
            "POST",
            f"{self._base_url}{KIMI_CHAT_PATH}",
            content=content,
            headers=headers,
            timeout=self._timeout,
        ) as response:
            if response.status_code != 401:
                await self._raise_for_response(response)
                async for event in self._iter_grpc_events(response, context):
                    yield event
                return

        await self._token_manager.invalidate_and_retry()
        headers = await self._get_headers({"Content-Type": "application/connect+json"})
        async with self._client.stream(
            "POST",
            f"{self._base_url}{KIMI_CHAT_PATH}",
            content=content,
            headers=headers,
            timeout=self._timeout,
        ) as response:
            await self._raise_for_response(response)
            async for event in self._iter_grpc_events(response, context):
                yield event

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
                async for event in self._iter_chat_events(content, context):
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
        return build_chat_completion(
            completion_id=final_id,
            created=created,
            model=model,
            content_parts=content_parts,
            reasoning_parts=reasoning_parts,
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

            async for event in self._iter_chat_events(content, context):
                chunk_id = context.remote_chat_id or context.request_conversation_id
                if not sent_role:
                    sent_role = True
                    yield role_chunk(chunk_id=chunk_id, created=created, model=model)

                delta = self._extract_delta(event, current_phase)
                current_phase = delta["phase"]

                if delta["reasoning_content"]:
                    yield reasoning_chunk(
                        chunk_id=chunk_id,
                        created=created,
                        model=model,
                        reasoning_content=delta["reasoning_content"],
                    )

                if delta["content"]:
                    yield content_chunk(
                        chunk_id=chunk_id,
                        created=created,
                        model=model,
                        content=delta["content"],
                    )

                if "done" in event:
                    sent_stop = True
                    yield stop_chunk(chunk_id=chunk_id, created=created, model=model)
                    break

            if not sent_stop:
                chunk_id = context.remote_chat_id or context.request_conversation_id
                yield stop_chunk(chunk_id=chunk_id, created=created, model=model)

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
