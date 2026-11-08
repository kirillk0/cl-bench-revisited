"""OpenRouter chat-completions provider (``z-ai/glm-5.3-flash``).

API details used (verified against openrouter.ai docs and the public
``/api/v1/models/z-ai/glm-5.3-flash/endpoints`` listing, Nov 2026):

* ``POST https://openrouter.ai/api/v1/chat/completions`` with
  ``Authorization: Bearer $OPENROUTER_API_KEY`` (+ ``HTTP-Referer``/``X-Title``).
* Native tools: ``tools:[{type:"function",function:{name,description,parameters}}]``,
  ``tool_choice:"auto"``; tool results are ``{"role":"tool","tool_call_id",...}``.
* Reasoning: ``reasoning:{enabled:true}``.  The assistant message comes back with
  ``reasoning`` (plain text) and/or ``reasoning_details`` (array of
  ``reasoning.text`` / ``reasoning.summary`` / ``reasoning.encrypted`` items).
  We store the assistant message as returned and send ``reasoning_details`` back
  **unmodified** in the assistant message on later calls ("preserving reasoning
  blocks"); when only ``reasoning`` text is present it is passed back as the
  ``reasoning`` string field.
* Usage: always included (``usage:{include:true}`` is accepted but deprecated/no-op);
  ``usage.cost`` is the amount charged in USD and is used when present, otherwise
  cost is computed from SPEC prices.  ``prompt_tokens_details.cached_tokens`` and
  ``completion_tokens_details.reasoning_tokens`` feed the cached/reasoning fields.
* Prompt caching: GLM-5.3-flash endpoints advertise ``supports_implicit_caching``
  (no request-side markers); cache reads show up in ``cached_tokens``.
* Provider routing: ~40 upstreams serve this model with different quantisation
  (fp4/nvfp4/fp8) and prices.  The SPEC prices (in 0.0335 / out 0.083 per 1M)
  correspond to **Relace** (``relace/fp4``), which supports ``tools`` and
  ``reasoning``.  Pass ``provider_order`` to pin upstreams via
  ``provider:{order:[...], allow_fallbacks:false}``; ``None`` uses default routing.
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

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

#: fallback USD per 1M tokens when ``usage.cost`` is absent (SPEC.md "Models")
OPENROUTER_PRICES: dict[str, Pricing] = {
    "z-ai/glm-5.3-flash": Pricing(input=0.0335, cached_input=0.03, cache_write=0.0, output=0.083),
}

_FINISH_MAP = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens",
               "content_filter": "refusal", "error": "error"}


def openrouter_usage(raw: dict, model: str) -> Usage:
    """Convert an OpenRouter ``usage`` object to :class:`Usage` (prefers ``usage.cost``)."""
    inp = int(raw.get("prompt_tokens") or 0)
    cached = int((raw.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    written = int((raw.get("prompt_tokens_details") or {}).get("cache_write_tokens") or 0)
    out = int(raw.get("completion_tokens") or 0)
    reasoning = int((raw.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
    u = Usage(input_tokens=inp, cached_input_tokens=cached, cache_write_tokens=written, output_tokens=out,
              reasoning_tokens=reasoning, cost_usd=None, raw=dict(raw))
    cost = raw.get("cost")
    if isinstance(cost, (int, float)):
        u.cost_usd = float(cost)
    else:
        price = OPENROUTER_PRICES.get(model)
        if price is not None:
            u.cost_usd = price.cost(u)
    return u


class OpenRouterConversation(Conversation):
    """History as OpenAI-style chat messages (system message first)."""

    def __init__(self, provider: "OpenRouterProvider", system_prompt: str, tools: list[ToolSpec], conv_id: str,
                 messages: list[dict] | None = None, last_usage: dict | None = None):
        self.provider = provider
        self.system_prompt = system_prompt
        self.tools = list(tools)
        self.conv_id = conv_id
        self.messages: list[dict] = messages if messages is not None else [{"role": "system", "content": system_prompt}]
        self._last_usage: Usage | None = Usage.from_dict(last_usage) if last_usage else None

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def add_tool_results(self, results: list[tuple[str, str]]) -> None:
        for call_id, output in results:
            self.messages.append({"role": "tool", "tool_call_id": call_id, "content": output})

    def _tools_payload(self) -> list[dict]:
        return [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                   "parameters": t.parameters}} for t in self.tools]

    def _build_body(self) -> dict:
        p = self.provider
        body: dict[str, Any] = {
            "model": p.model,
            "messages": deepcopy_json(self.messages),
            "usage": {"include": True},
            "reasoning": {"enabled": True},
            "user": self.conv_id,
        }
        if self.tools:
            body["tools"] = self._tools_payload()
            body["tool_choice"] = "auto"
        if p.max_tokens is not None:
            body["max_tokens"] = p.max_tokens
        if p.provider_order:
            body["provider"] = {"order": list(p.provider_order), "allow_fallbacks": p.allow_fallbacks}
        if p.extra_body:
            body.update(deepcopy_json(p.extra_body))
        return body

    def step(self) -> TurnResult:
        p = self.provider
        body = self._build_body()
        headers = {
            "Authorization": f"Bearer {p.api_key}",
            "content-type": "application/json",
            "HTTP-Referer": p.referer,
            "X-Title": p.title,
        }
        t_start = time.monotonic()

        def attempt(n: int) -> dict:
            t0 = time.monotonic()
            resp = p.session.post(OPENROUTER_URL, headers=headers, json=body,
                                  timeout=(CONNECT_TIMEOUT_S, REQUEST_TIMEOUT_S))
            lat = time.monotonic() - t0
            text = resp.text
            try:
                data = resp.json()
            except ValueError:
                data = {"_non_json_body": text[:2000]}
            p.raw_log({"conv_id": self.conv_id, "attempt": n, "url": OPENROUTER_URL, "status": resp.status_code,
                       "latency_s": round(lat, 3), "request": {"headers": headers, "body": body}, "response": data})
            if resp.status_code != 200:
                raise classify_http_error(resp.status_code, text, resp.headers)
            # OpenRouter may return 200 with an error object (e.g. upstream failure mid-request).
            if isinstance(data, dict) and data.get("error") and not data.get("choices"):
                err = data["error"]
                code = int(err.get("code") or 0) if str(err.get("code") or "").isdigit() else 0
                raise classify_http_error(code or 502, str(err)[:2000], resp.headers)
            if not isinstance(data, dict) or not data.get("choices"):
                raise RetryableError(f"unexpected response shape: {text[:300]}", resp.status_code, data)
            return data

        data = retry_call(attempt, what=f"openrouter[{self.conv_id}]")
        return self._ingest(data, time.monotonic() - t_start)

    def _ingest(self, data: dict, latency: float) -> TurnResult:
        choice = data["choices"][0]
        msg: dict = choice.get("message") or {}
        # Native assistant message to keep in history: content, tool_calls and the reasoning carrier.
        stored: dict[str, Any] = {"role": "assistant", "content": msg.get("content")}
        if msg.get("tool_calls"):
            stored["tool_calls"] = deepcopy_json(msg["tool_calls"])
        if msg.get("reasoning_details"):
            stored["reasoning_details"] = deepcopy_json(msg["reasoning_details"])  # pass back unmodified
        elif msg.get("reasoning"):
            stored["reasoning"] = msg["reasoning"]
        self.messages.append(stored)

        calls = [ToolCall(id=tc.get("id") or f"call_{i}", name=tc["function"]["name"],
                          arguments=parse_tool_arguments(tc["function"].get("arguments")))
                 for i, tc in enumerate(msg.get("tool_calls") or []) if tc.get("type", "function") == "function"]
        summary = msg.get("reasoning") or None
        if not summary and msg.get("reasoning_details"):
            parts = [d.get("text") or d.get("summary") for d in msg["reasoning_details"]
                     if d.get("type") in ("reasoning.text", "reasoning.summary")]
            summary = "\n\n".join(x for x in parts if x) or None
        usage = openrouter_usage(data.get("usage") or {}, self.provider.model)
        usage.raw["provider"] = data.get("provider")  # upstream that actually served the request
        self._last_usage = usage
        fin = choice.get("finish_reason") or choice.get("native_finish_reason") or ""
        stop = _FINISH_MAP.get(fin, fin or "unknown")
        if calls:
            stop = "tool_use"
        text = msg.get("content")
        return TurnResult(
            text=text if text else None,
            tool_calls=calls,
            reasoning_summary=summary,
            usage=usage,
            stop_reason=stop,
            latency_s=latency,
            raw=data,
        )

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
        pending_results: list[dict] = []
        for m in self.messages:
            role = m.get("role")
            if role == "tool":
                pending_results.append({"call_id": m.get("tool_call_id"), "output": m.get("content")})
                continue
            if pending_results:
                view.append({"role": "tool", "text": None, "tool_calls": [], "tool_results": pending_results,
                             "reasoning_summary": None})
                pending_results = []
            if role == "system":
                continue
            if role == "user":
                view.append({"role": "user", "text": m.get("content"), "tool_calls": [], "tool_results": [],
                             "reasoning_summary": None})
            elif role == "assistant":
                calls = [{"id": tc.get("id"), "name": tc["function"]["name"],
                          "arguments": parse_tool_arguments(tc["function"].get("arguments"))}
                         for tc in m.get("tool_calls") or []]
                summary = m.get("reasoning")
                if not summary and m.get("reasoning_details"):
                    summary = "\n\n".join(d.get("text") or d.get("summary") or "" for d in m["reasoning_details"]
                                          if d.get("type") in ("reasoning.text", "reasoning.summary")) or None
                view.append({"role": "assistant", "text": m.get("content") or None, "tool_calls": calls,
                             "tool_results": [], "reasoning_summary": summary})
        if pending_results:
            view.append({"role": "tool", "text": None, "tool_calls": [], "tool_results": pending_results,
                         "reasoning_summary": None})
        return view

    def context_tokens_estimate(self) -> int:
        if self._last_usage is None:
            return 0
        return self._last_usage.input_tokens + self._last_usage.output_tokens


class OpenRouterProvider(Provider):
    """Provider for OpenRouter chat completions.

    Parameters
    ----------
    api_key:
        Defaults to ``OPENROUTER_API_KEY``.
    provider_order:
        Upstream names for ``provider.order`` (e.g. ``["Relace"]``); ``None`` -> default routing.
    allow_fallbacks:
        ``provider.allow_fallbacks`` (only sent together with ``provider_order``).
    max_tokens:
        Optional completion cap (``None`` -> provider default).
    extra_body:
        Extra top-level request fields merged into every request.
    """

    RAW_LOG_OPAQUE_KEYS = ("data", "signature")  # reasoning.encrypted payloads

    def __init__(self, model: str = "z-ai/glm-5.3-flash", key: str = "glm", *, api_key: str | None = None,
                 provider_order: list[str] | None = None, allow_fallbacks: bool = False,
                 max_tokens: int | None = None, extra_body: dict | None = None,
                 referer: str = "https://github.com/kirillk0/cl-bench-revisited", title: str = "cl-bench-revisited",
                 raw_log_path: str | None = None):
        super().__init__(key=key, model=model, raw_log_path=raw_log_path)
        self.api_key = api_key or env_or_none("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ProviderError("OPENROUTER_API_KEY is not set")
        self.provider_order = list(provider_order) if provider_order else None
        self.allow_fallbacks = allow_fallbacks
        self.max_tokens = max_tokens
        self.extra_body = dict(extra_body) if extra_body else None
        self.referer = referer
        self.title = title

    def new_conversation(self, system_prompt: str, tools: list[ToolSpec], conv_id: str) -> OpenRouterConversation:
        return OpenRouterConversation(self, system_prompt, tools, conv_id)

    def restore_conversation(self, state: dict) -> OpenRouterConversation:
        if state.get("provider") not in (self.key, "openrouter") and state.get("model") != self.model:
            raise ProviderError(f"state is for provider {state.get('provider')!r}/{state.get('model')!r}")
        return OpenRouterConversation(
            self, state["system_prompt"], [ToolSpec.from_dict(t) for t in state["tools"]], state["conv_id"],
            messages=deepcopy_json(state["messages"]), last_usage=state.get("last_usage"),
        )
