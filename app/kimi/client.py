import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Set, Union

import httpx

from ..config import Config as _Config
from ..core.kimi_account_pool import KimiAccountRuntime, get_account_pool
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
)
from .transport import (
    build_kimi_headers,
    classify_upstream_status,
    get_shared_transport,
    load_or_create_client_identity,
    process_session_id,
    retry_after_seconds,
)


AccountUsageCallback = Callable[[Dict[str, str]], None]


class _LegacyRuntime:
    def __init__(
        self,
        *,
        token_manager: Any,
        transport: Any,
        device_id: str,
        session_id: str,
    ):
        self.account_id = ""
        self.account_name = ""
        self.token_manager = token_manager
        self.transport = transport
        self.account = type(
            "LegacyAccount",
            (),
            {
                "id": "",
                "name": "",
                "device_id": device_id,
            },
        )()
        self.session_id = session_id


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
        on_account_used: Optional[AccountUsageCallback] = None,
        **kwargs: Any,
    ):
        del kwargs

        self._base_url = (base_url or _Config.KIMI_API_BASE).rstrip("/")
        self._timeout = timeout or _Config.TIMEOUT
        self._max_retries = max_retries
        self._on_account_used = on_account_used
        self.last_account_id = ""
        self.last_account_name = ""
        self._account_pool = get_account_pool(required=False)
        self._legacy_runtime: Optional[_LegacyRuntime] = None
        self._device_id = load_or_create_client_identity().device_id
        self._session_id = process_session_id()
        self._transport = get_shared_transport(
            base_url=self._base_url,
            timeout=self._timeout,
            max_retries=self._max_retries,
        )
        if self._account_pool is None or not self._account_pool.configured:
            try:
                token_manager = get_token_manager()
            except RuntimeError as exc:
                raise KimiAPIError("Kimi token is not configured") from exc
            self._legacy_runtime = _LegacyRuntime(
                token_manager=token_manager,
                transport=self._transport,
                device_id=self._device_id,
                session_id=self._session_id,
            )
        self._conversation_contexts: Dict[str, ConversationContext] = {}
        self.chat = _ChatNamespace(self)

    def _notify_account_used(self, runtime: Union[KimiAccountRuntime, _LegacyRuntime]) -> None:
        self.last_account_id = runtime.account_id
        self.last_account_name = runtime.account_name
        if self._on_account_used is not None and runtime.account_id:
            self._on_account_used({
                "id": runtime.account_id,
                "name": runtime.account_name,
            })

    async def _get_headers(
        self,
        runtime: Union[KimiAccountRuntime, _LegacyRuntime],
        extra: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        token = await runtime.token_manager.get_access_token()
        return build_kimi_headers(
            base_url=self._base_url,
            token=token,
            device_id=runtime.account.device_id,
            session_id=runtime.session_id,
            extra={
                "Connect-Protocol-Version": "1",
                **(extra or {}),
            },
        )

    async def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        retryable_status_codes: Optional[List[int]] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        return await self._transport.request(
            method,
            url,
            retryable_status_codes=retryable_status_codes,
            **kwargs,
        )

    @asynccontextmanager
    async def _acquire_runtime(
        self,
        *,
        exclude: Optional[Set[str]] = None,
    ) -> AsyncIterator[Union[KimiAccountRuntime, _LegacyRuntime]]:
        if self._account_pool is not None and self._account_pool.configured:
            async with self._account_pool.acquire(exclude=exclude) as runtime:
                self._notify_account_used(runtime)
                yield runtime
            return
        if self._legacy_runtime is None:
            raise KimiAPIError("Kimi token is not configured")
        self._notify_account_used(self._legacy_runtime)
        yield self._legacy_runtime

    async def validate_token(self) -> bool:
        try:
            data = await self.get_subscription()
            return bool(data and data.get("subscription"))
        except Exception:
            return False

    async def get_subscription(self) -> Optional[Dict[str, Any]]:
        try:
            async with self._acquire_runtime() as runtime:
                headers = await self._get_headers(runtime)
                response = await runtime.transport.request(
                    "POST",
                    KIMI_SUBSCRIPTION_PATH,
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
            async with self._acquire_runtime() as runtime:
                headers = await self._get_headers(runtime)
                response = await runtime.transport.request(
                    "GET",
                    KIMI_RESEARCH_USAGE_PATH,
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
            f"upstream error {response.status_code}: {body or '<empty>'}",
            retry_after=retry_after_seconds(response.headers)
            if response.status_code == 429
            else None,
            upstream_status_code=response.status_code,
            upstream_error_type=classify_upstream_status(response.status_code),
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

    async def _iter_chat_events_for_runtime(
        self,
        runtime: Union[KimiAccountRuntime, _LegacyRuntime],
        content: bytes,
        context: ConversationContext,
    ) -> AsyncIterator[Dict[str, Any]]:
        headers = await self._get_headers(
            runtime,
            {"Content-Type": "application/connect+json"},
        )
        async with runtime.transport.stream(
            "POST",
            KIMI_CHAT_PATH,
            content=content,
            headers=headers,
            timeout=self._timeout,
        ) as response:
            if response.status_code != 401:
                await self._raise_for_response(response)
                async for event in self._iter_grpc_events(response, context):
                    yield event
                return

        await runtime.token_manager.invalidate_and_retry()
        headers = await self._get_headers(
            runtime,
            {"Content-Type": "application/connect+json"},
        )
        async with runtime.transport.stream(
            "POST",
            KIMI_CHAT_PATH,
            content=content,
            headers=headers,
            timeout=self._timeout,
        ) as response:
            await self._raise_for_response(response)
            async for event in self._iter_grpc_events(response, context):
                yield event

    async def _iter_chat_events(
        self,
        content: bytes,
        context: ConversationContext,
    ) -> AsyncIterator[Dict[str, Any]]:
        async with self._acquire_runtime() as runtime:
            async for event in self._iter_chat_events_for_runtime(runtime, content, context):
                yield event

    def _can_switch_account(self, exc: Exception) -> bool:
        if not isinstance(exc, KimiAPIError):
            return True
        status_code = int(exc.upstream_status_code or 0)
        return (
            status_code in {401, 403, 429}
            or 500 <= status_code <= 599
            or exc.upstream_error_type
            in {
                "rate_limited",
                "server_error",
                "network_error",
                "stream_interrupted",
                "token_refresh_failed",
                "unauthorized",
                "forbidden",
            }
        )

    def _record_runtime_failure(
        self,
        runtime: Union[KimiAccountRuntime, _LegacyRuntime],
        exc: Exception,
    ) -> None:
        if self._account_pool is not None and isinstance(runtime, KimiAccountRuntime):
            self._account_pool.record_failure(runtime, exc)

    def _record_runtime_success(
        self,
        runtime: Union[KimiAccountRuntime, _LegacyRuntime],
    ) -> None:
        if self._account_pool is not None and isinstance(runtime, KimiAccountRuntime):
            self._account_pool.record_success(runtime)

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
        attempted_accounts: Set[str] = set()
        attempt_limit = (
            max(self._max_retries, self._account_pool.account_count())
            if self._account_pool is not None and self._account_pool.configured
            else self._max_retries
        )
        for attempt in range(1, attempt_limit + 1):
            reasoning_parts.clear()
            content_parts.clear()
            current_phase = None
            runtime: Optional[Union[KimiAccountRuntime, _LegacyRuntime]] = None
            produced_output = False
            try:
                async with self._acquire_runtime(exclude=attempted_accounts) as selected_runtime:
                    runtime = selected_runtime
                    if runtime.account_id:
                        attempted_accounts.add(runtime.account_id)
                    async for event in self._iter_chat_events_for_runtime(runtime, content, context):
                        delta = self._extract_delta(event, current_phase)
                        current_phase = delta["phase"]
                        if delta["reasoning_content"]:
                            produced_output = True
                            reasoning_parts.append(delta["reasoning_content"])
                        if delta["content"]:
                            produced_output = True
                            content_parts.append(delta["content"])
                        if "done" in event:
                            produced_output = True
                            break
                    self._record_runtime_success(runtime)
                break
            except KimiAPIError as exc:
                last_error = exc
                if runtime is not None:
                    self._record_runtime_failure(runtime, exc)
                if (
                    produced_output
                    or attempt == attempt_limit
                    or not self._can_switch_account(exc)
                ):
                    raise KimiAPIError(
                        f"chat completion failed after {attempt} attempts: {exc}",
                        retry_after=exc.retry_after,
                        upstream_status_code=exc.upstream_status_code,
                        upstream_error_type=exc.upstream_error_type,
                    ) from exc
                await asyncio.sleep(
                    exc.retry_after
                    if exc.retry_after is not None and self._account_pool is None
                    else (0.0 if self._account_pool is not None else min(0.5 * attempt, 2.0))
                )
            except Exception as exc:
                last_error = exc
                wrapped = KimiAPIError(
                    f"Kimi upstream request failed: {exc}",
                    upstream_error_type="network_error",
                )
                if runtime is not None:
                    self._record_runtime_failure(runtime, wrapped)
                if produced_output or attempt == attempt_limit:
                    raise wrapped from exc
                await asyncio.sleep(0.0 if self._account_pool is not None else min(0.5 * attempt, 2.0))

        if last_error and not content_parts and not reasoning_parts:
            if isinstance(last_error, KimiAPIError):
                raise KimiAPIError(
                    str(last_error),
                    retry_after=last_error.retry_after,
                    upstream_status_code=last_error.upstream_status_code,
                    upstream_error_type=last_error.upstream_error_type,
                ) from last_error
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
            attempted_accounts: Set[str] = set()
            attempt_limit = (
                max(self._max_retries, self._account_pool.account_count())
                if self._account_pool is not None and self._account_pool.configured
                else self._max_retries
            )

            for attempt in range(1, attempt_limit + 1):
                runtime: Optional[Union[KimiAccountRuntime, _LegacyRuntime]] = None
                try:
                    async with self._acquire_runtime(exclude=attempted_accounts) as selected_runtime:
                        runtime = selected_runtime
                        if runtime.account_id:
                            attempted_accounts.add(runtime.account_id)
                        async for event in self._iter_chat_events_for_runtime(runtime, content, context):
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
                                self._record_runtime_success(runtime)
                                return
                        self._record_runtime_success(runtime)
                    break
                except KimiAPIError as exc:
                    if runtime is not None:
                        self._record_runtime_failure(runtime, exc)
                    if sent_role or attempt == attempt_limit or not self._can_switch_account(exc):
                        raise
                    await asyncio.sleep(0.0 if self._account_pool is not None else min(0.5 * attempt, 2.0))
                except Exception as exc:
                    wrapped = KimiAPIError(
                        f"Kimi upstream request failed: {exc}",
                        upstream_error_type="network_error",
                    )
                    if runtime is not None:
                        self._record_runtime_failure(runtime, wrapped)
                    if sent_role or attempt == attempt_limit:
                        raise wrapped from exc
                    await asyncio.sleep(0.0 if self._account_pool is not None else min(0.5 * attempt, 2.0))

            if not sent_stop:
                chunk_id = context.remote_chat_id or context.request_conversation_id
                yield stop_chunk(chunk_id=chunk_id, created=created, model=model)

        return generator()

    async def close(self) -> None:
        return None

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
