"""Anthropic Messages API provider (``claude-haiku-5-5``).

API details used (verified against platform.claude.com docs, Nov 2026):

* ``POST https://api.anthropic.com/v1/messages`` with headers ``x-api-key``,
  ``anthropic-version: 2026-10-21``.
* Adaptive thinking: ``thinking: {"type": "adaptive", "display": "summarized"}``.
  Haiku 5.5 only supports adaptive thinking (``enabled``/``budget_tokens`` -> 400).
  Effort is controlled with ``output_config.effort`` (low|medium|high|xhigh|max);
  by default we do not send it, i.e. the model default (``medium``) applies.
  ``display: "summarized"`` makes the summarised thinking text visible (used as
  ``reasoning_summary``); it does not change cost.
* Thinking blocks (``thinking`` / ``redacted_thinking``) returned in the assistant
  turn are stored unmodified in the history and sent back on every later call
  (Haiku 5.5 keeps all prior turns' thinking blocks in context).
* Prompt caching: ``cache_control: {"type": "ephemeral"}`` on the system text
  block and on the last content block of the most recent user message (which
  holds ``tool_result`` blocks and/or text).  Markers are added at request time
  only, so the stored history is clean and exactly 2 of the 4 allowed
  breakpoints are used.  ``tools`` precede ``system`` in the cache prefix, so the
  system breakpoint covers the tool definitions too.
* Usage: ``input_tokens`` (uncached part), ``cache_read_input_tokens``,
  ``cache_creation_input_tokens``, ``output_tokens`` and
  ``output_tokens_details.thinking_tokens`` (-> ``reasoning_tokens``).
* Long-context pricing: a request whose prompt (input + cache read + cache write)
  exceeds 100k tokens is billed at the higher tier for all its tokens.
"""

from __future__ import annotations

import time
from typing import Any

from .base import (
    CONNECT_TIMEOUT_S,
    REQUEST_TIMEOUT_S,
    Conversation,
    Pricing,
    Provider,
    ProviderError,
    RetryableError,
    ToolCall,
    ToolSpec,
    TurnResult,
    Usage,
    classify_http_error,
    deepcopy_json,
    env_or_none,
    parse_tool_arguments,
    retry_call,
)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2026-10-21"
LONG_CONTEXT_THRESHOLD = 100_000  # tokens; strictly greater -> long-context prices

#: USD per 1M tokens: (<=100k prompt, >100k prompt). Source: SPEC.md "Models".
ANTHROPIC_PRICES: dict[str, tuple[Pricing, Pricing]] = {
    "claude-haiku-5-5": (
        Pricing(input=0.10, cached_input=0.01, cache_write=0.125, output=0.50),
        Pricing(input=0.50, cached_input=0.05, cache_write=0.625, output=2.50),
    ),
}

_STOP_MAP = {
    "tool_use": "tool_use",
    "end_turn": "end_turn",
    "max_tokens": "max_tokens",
    "stop_sequence": "end_turn",
    "refusal": "refusal",
    "pause_turn": "incomplete",
    "model_context_window_exceeded": "max_tokens",
}


def anthropic_usage(raw: dict, model: str) -> Usage:
    """Convert an Anthropic ``usage`` object to :class:`Usage` with tiered cost."""
    uncached = int(raw.get("input_tokens") or 0)
    cached = int(raw.get("cache_read_input_tokens") or 0)
    written = int(raw.get("cache_creation_input_tokens") or 0)
    out = int(raw.get("output_tokens") or 0)
    thinking = int((raw.get("output_tokens_details") or {}).get("thinking_tokens") or 0)
    u = Usage(
        input_tokens=uncached + cached + written,
        cached_input_tokens=cached,
        cache_write_tokens=written,
        output_tokens=out,
        reasoning_tokens=thinking,  # usage.output_tokens_details.thinking_tokens (part of output_tokens)
        cost_usd=None,
        raw=dict(raw),
    )
    prices = ANTHROPIC_PRICES.get(model)
    if prices is not None:
        tier = prices[1] if u.input_tokens > LONG_CONTEXT_THRESHOLD else prices[0]
        u.cost_usd = tier.cost(u)
    return u


class AnthropicConversation(Conversation):
    """Message history in native Anthropic format (``messages`` list of blocks)."""

    def __init__(self, provider: "AnthropicProvider", system_prompt: str, tools: list[ToolSpec], conv_id: str,
                 messages: list[dict] | None = None, last_usage: dict | None = None):
        self.provider = provider
        self.system_prompt = system_prompt
        self.tools = list(tools)
        self.conv_id = conv_id
        self.messages: list[dict] = messages if messages is not None else []
        self._last_usage: Usage | None = Usage.from_dict(last_usage) if last_usage else None

    # ----- history construction -------------------------------------------- #

    def add_user(self, text: str) -> None:
        block = {"type": "text", "text": text}
        # Consecutive user content (e.g. tool_result followed by the next question)
        # is merged into one user message: tool_result blocks first, then text.
        if self.messages and self.messages[-1]["role"] == "user":
            self.messages[-1]["content"].append(block)
        else:
            self.messages.append({"role": "user", "content": [block]})

    def add_tool_results(self, results: list[tuple[str, str]]) -> None:
        blocks = [{"type": "tool_result", "tool_use_id": cid, "content": out} for cid, out in results]
        if self.messages and self.messages[-1]["role"] == "user":
            # Only legal if the previous user message has no text yet (tool_result must come first).
            if any(b.get("type") == "text" for b in self.messages[-1]["content"]):
                raise ProviderError("tool results must directly follow the assistant tool_use turn")
            self.messages[-1]["content"].extend(blocks)
        else:
            self.messages.append({"role": "user", "content": blocks})

    # ----- request building -------------------------------------------------- #

    def _tools_payload(self) -> list[dict]:
        return [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in self.tools]

    def _build_body(self) -> dict:
        p = self.provider
        system = [{"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}}]
        messages = deepcopy_json(self.messages)
        # Re-mark the last block of the most recent user message each turn (breakpoint #2).
        for m in reversed(messages):
            if m["role"] == "user" and m["content"]:
                m["content"][-1]["cache_control"] = {"type": "ephemeral"}
                break
        body: dict[str, Any] = {
            "model": p.model,
            "max_tokens": p.max_tokens,
            "system": system,
            "messages": messages,
            "thinking": {"type": "adaptive", "display": p.thinking_display},
        }
        if self.tools:
            body["tools"] = self._tools_payload()
        if p.effort is not None:
            body["output_config"] = {"effort": p.effort}
        return body

    # ----- model call ---------------------------------------------------------- #

    def step(self) -> TurnResult:
        p = self.provider
        body = self._build_body()
        headers = {
            "x-api-key": p.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        t_start = time.monotonic()

        def attempt(n: int) -> dict:
            t0 = time.monotonic()
            resp = p.session.post(ANTHROPIC_URL, headers=headers, json=body,
                                  timeout=(CONNECT_TIMEOUT_S, REQUEST_TIMEOUT_S))
            lat = time.monotonic() - t0
            text = resp.text
            try:
                data = resp.json()
            except ValueError:
                data = {"_non_json_body": text[:2000]}
            p.raw_log({"conv_id": self.conv_id, "attempt": n, "url": ANTHROPIC_URL, "status": resp.status_code,
                       "latency_s": round(lat, 3), "request_id": resp.headers.get("request-id"),
                       "request": {"headers": headers, "body": body}, "response": data})
            if resp.status_code != 200:
                raise classify_http_error(resp.status_code, text, resp.headers)
            if not isinstance(data, dict) or data.get("type") != "message":
                raise RetryableError(f"unexpected response shape: {text[:300]}", resp.status_code, data)
            return data

        data = retry_call(attempt, what=f"anthropic[{self.conv_id}]")
        latency = time.monotonic() - t_start
        return self._ingest(data, latency)

    def _ingest(self, data: dict, latency: float) -> TurnResult:
        content: list[dict] = data.get("content") or []
        # Store the assistant turn exactly as returned (thinking/redacted_thinking/text/tool_use).
        self.messages.append({"role": "assistant", "content": deepcopy_json(content)})
        texts = [b["text"] for b in content if b.get("type") == "text" and b.get("text")]
        thoughts = [b["thinking"] for b in content if b.get("type") == "thinking" and b.get("thinking")]
        calls = [ToolCall(id=b["id"], name=b["name"], arguments=parse_tool_arguments(b.get("input")))
                 for b in content if b.get("type") == "tool_use"]
        usage = anthropic_usage(data.get("usage") or {}, self.provider.model)
        self._last_usage = usage
        stop_raw = data.get("stop_reason") or ""
        stop = _STOP_MAP.get(stop_raw, stop_raw or "unknown")
        if calls and stop == "end_turn":
            stop = "tool_use"
        return TurnResult(
            text="\n".join(texts) if texts else None,
            tool_calls=calls,
            reasoning_summary="\n\n".join(thoughts) if thoughts else None,
            usage=usage,
            stop_reason=stop,
            latency_s=latency,
            raw=data,
        )

    # ----- introspection -------------------------------------------------------- #

    def export_state(self) -> dict:
        return {
            "version": 1,
            "provider": self.provider.key,
            "model": self.provider.model,
            "conv_id": self.conv_id,
            "system_prompt": self.system_prompt,
            "tools": [t.to_dict() for t in self.tools],
            "messages": deepcopy_json(self.messages),
            "last_usage": self._last_usage.to_dict() if self._last_usage else None,
        }

    def history_view(self) -> list[dict]:
        view: list[dict] = []
        for m in self.messages:
            if m["role"] == "user":
                results = [{"call_id": b["tool_use_id"], "output": b.get("content")}
                           for b in m["content"] if b.get("type") == "tool_result"]
                texts = [b["text"] for b in m["content"] if b.get("type") == "text"]
                if results:
                    view.append({"role": "tool", "text": None, "tool_calls": [], "tool_results": results,
                                 "reasoning_summary": None})
                if texts:
                    view.append({"role": "user", "text": "\n".join(texts), "tool_calls": [], "tool_results": [],
                                 "reasoning_summary": None})
            else:
                texts = [b["text"] for b in m["content"] if b.get("type") == "text"]
                thoughts = [b["thinking"] for b in m["content"] if b.get("type") == "thinking" and b.get("thinking")]
                calls = [{"id": b["id"], "name": b["name"], "arguments": b.get("input")}
                         for b in m["content"] if b.get("type") == "tool_use"]
                view.append({"role": "assistant", "text": "\n".join(texts) or None, "tool_calls": calls,
                             "tool_results": [], "reasoning_summary": "\n\n".join(thoughts) or None})
        return view

    def context_tokens_estimate(self) -> int:
        if self._last_usage is None:
            return 0
        return self._last_usage.input_tokens + self._last_usage.output_tokens


class AnthropicProvider(Provider):
    """Provider for the Anthropic Messages API.

    Parameters
    ----------
    api_key:
        Defaults to ``ANTHROPIC_API_KEY`` from the environment.
    max_tokens:
        Output cap incl. thinking tokens (default 16000).
    effort:
        ``output_config.effort`` (``low``/``medium``/``high``/``xhigh``/``max``);
        ``None`` (default) leaves the model default (``medium`` on Haiku 5.5).
    thinking_display:
        ``"summarized"`` (default, thinking text available as reasoning_summary) or ``"omitted"``.
    """

    RAW_LOG_OPAQUE_KEYS = ("signature", "data")  # thinking signature / redacted_thinking data

    def __init__(self, model: str = "claude-haiku-5-5", key: str = "haiku", *, api_key: str | None = None,
                 max_tokens: int = 16000, effort: str | None = None, thinking_display: str = "summarized",
                 raw_log_path: str | None = None):
        super().__init__(key=key, model=model, raw_log_path=raw_log_path)
        self.api_key = api_key or env_or_none("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        self.max_tokens = max_tokens
        self.effort = effort
        self.thinking_display = thinking_display

    def new_conversation(self, system_prompt: str, tools: list[ToolSpec], conv_id: str) -> AnthropicConversation:
        return AnthropicConversation(self, system_prompt, tools, conv_id)

    def restore_conversation(self, state: dict) -> AnthropicConversation:
        if state.get("provider") not in (self.key, "anthropic") and state.get("model") != self.model:
            raise ProviderError(f"state is for provider {state.get('provider')!r}/{state.get('model')!r}")
        return AnthropicConversation(
            self, state["system_prompt"], [ToolSpec.from_dict(t) for t in state["tools"]], state["conv_id"],
            messages=deepcopy_json(state["messages"]), last_usage=state.get("last_usage"),
        )
