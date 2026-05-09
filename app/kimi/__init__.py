from .protocol import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionUsage,
    ConversationContext,
    KimiAPIError,
    Message,
    detect_token_type,
    generate_device_id,
    generate_session_id,
    parse_jwt,
)

# Lazy imports to avoid circular dependency:
# core.token_manager -> kimi.protocol -> kimi.__init__ -> kimi.client -> core.token_manager
# Import Kimi2API and ChatCompletions directly when needed:
#   from app.kimi.client import Kimi2API, ChatCompletions, create_client


def __getattr__(name: str):
    """Lazy import for names that depend on token_manager."""
    if name in ("Kimi2API", "ChatCompletions", "create_client"):
        from .client import ChatCompletions, Kimi2API, create_client
        globals()["Kimi2API"] = Kimi2API
        globals()["ChatCompletions"] = ChatCompletions
        globals()["create_client"] = create_client
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ChatCompletion",
    "ChatCompletionChunk",
    "ChatCompletionChoice",
    "ChatCompletionMessage",
    "ChatCompletionUsage",
    "ChatCompletions",
    "ConversationContext",
    "Kimi2API",
    "KimiAPIError",
    "Message",
    "create_client",
    "detect_token_type",
    "generate_device_id",
    "generate_session_id",
    "parse_jwt",
]
