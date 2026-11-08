"""Model providers for the memory-modes experiment.

Use :func:`make_provider` with one of the SPEC keys::

    from clrev.providers import make_provider
    p = make_provider("haiku")            # luna | haiku | glm
    p.raw_log_path = "runs/x/raw/haiku.jsonl"
    conv = p.new_conversation(system_prompt, tools, conv_id="run1-icl")

Keys -> (provider, model):

* ``luna``  -> :class:`~clrev.providers.openai_codex.CodexProvider`     / ``gpt-6-luna``
* ``haiku`` -> :class:`~clrev.providers.anthropic_p.AnthropicProvider`  / ``claude-haiku-5-5``
* ``glm``   -> :class:`~clrev.providers.openrouter_p.OpenRouterProvider`/ ``z-ai/glm-5.3-flash``
"""

from __future__ import annotations

from typing import Any, Callable

from .anthropic_p import AnthropicProvider
from .base import (
    AuthError,
    Conversation,
    Provider,
    ProviderError,
    RetryableError,
    ToolCall,
    ToolSpec,
    TurnResult,
    Usage,
)
from .openai_codex import CodexProvider
from .openrouter_p import OpenRouterProvider

# OpenRouter upstream pin for GLM-5.3-flash.  Relace is the endpoint whose prices
# match SPEC (in 0.0335 / out 0.083 per 1M), serves fp4 with tools + reasoning
# support and 100% uptime at the time of writing.  Z.AI (official, fp8, 0.15/0.50)
# is listed second so a Relace outage does not kill a run; allow_fallbacks=false
# keeps OpenRouter from silently routing to any of the other ~38 upstreams.
GLM_PROVIDER_ORDER: list[str] = ["Relace", "Z.AI"]

MODELS: dict[str, dict[str, Any]] = {
    "luna": {"provider": "openai_codex", "model": "gpt-6-luna"},
    "haiku": {"provider": "anthropic", "model": "claude-haiku-5-5"},
    "glm": {"provider": "openrouter", "model": "z-ai/glm-5.3-flash"},
}

_FACTORIES: dict[str, Callable[..., Provider]] = {
    "luna": lambda **kw: CodexProvider(model=MODELS["luna"]["model"], key="luna", **kw),
    "haiku": lambda **kw: AnthropicProvider(model=MODELS["haiku"]["model"], key="haiku", **kw),
    "glm": lambda **kw: OpenRouterProvider(model=MODELS["glm"]["model"], key="glm",
                                           **{"provider_order": GLM_PROVIDER_ORDER, **kw}),
}


def make_provider(key: str, **overrides: Any) -> Provider:
    """Build the provider for a SPEC model key (``luna`` / ``haiku`` / ``glm``).

    ``overrides`` are forwarded to the provider constructor (e.g. ``raw_log_path=...``,
    ``effort="low"`` for haiku, ``reasoning_effort="low"`` for luna,
    ``provider_order=None`` for glm to use default OpenRouter routing).
    """
    try:
        factory = _FACTORIES[key]
    except KeyError:
        raise KeyError(f"unknown model key {key!r}; expected one of {sorted(_FACTORIES)}") from None
    return factory(**overrides)


__all__ = [
    "AnthropicProvider", "AuthError", "CodexProvider", "Conversation", "GLM_PROVIDER_ORDER", "MODELS",
    "OpenRouterProvider", "Provider", "ProviderError", "RetryableError", "ToolCall", "ToolSpec", "TurnResult",
    "Usage", "make_provider",
]
