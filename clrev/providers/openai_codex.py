"""OpenAI Codex backend provider (``gpt-6-luna`` via ChatGPT subscription).

Endpoint details (SPEC.md, verified 2026-11-08):

* ``POST https://chatgpt.com/backend-api/codex/responses`` -- Responses API shape,
  **streaming only** (``stream: true``, ``accept: text/event-stream``).  The final
  result is taken from the ``response.completed`` SSE event; ``response.failed``,
  ``response.incomplete`` and ``error`` events are handled.
* Headers: ``Authorization: Bearer <access_token>``, ``chatgpt-account-id`` (JWT claim
  ``https://api.openai.com/auth``.``chatgpt_account_id``), ``OpenAI-Beta:
  responses=experimental``, ``originator: codex_cli_rs``.
* Body: ``{model, instructions, input, tools, tool_choice:"auto", parallel_tool_calls,
  store:false, stream:true, include:["reasoning.encrypted_content"],
  reasoning:{effort, summary:"auto"}, prompt_cache_key:<conv_id>}``.
* Reasoning is preserved natively: ``reasoning`` output items carry
  ``encrypted_content`` and are appended to ``input`` unchanged for every later call.
* OAuth: ``POST https://auth.openai.com/oauth/token`` with
  ``{grant_type:"refresh_token", client_id, refresh_token}``.  Refresh tokens
  rotate; the whole response plus ``obtained_at`` is persisted atomically
  (``chmod 600``) to the token file.  Refresh happens when the access token is
  within ``REFRESH_MARGIN_S`` of expiry or after a 401.
* Usage: ``input_tokens`` (incl. ``input_tokens_details.cached_tokens`` and
  ``input_tokens_details.cache_write_tokens``), ``output_tokens`` (incl.
  ``output_tokens_details.reasoning_tokens``).  Cost is *imputed* from SPEC prices
  (subscription has no per-token billing).

Secrets are never logged: raw-log headers are redacted and token-exchange bodies
are not written to the raw log at all.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
import time
from typing import Any, Iterator

import requests

from .base import (
    CONNECT_TIMEOUT_S,
    REQUEST_TIMEOUT_S,
    AuthError,
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
    log,
    parse_tool_arguments,
    retry_call,
)

CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
CODEX_MODELS_URL = "https://chatgpt.com/backend-api/codex/models?client_version=1.0.0"
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
DEFAULT_TOKEN_PATHS = ("/workspace/secrets/openai-tokens.json", "secrets/openai-tokens.json")
REFRESH_MARGIN_S = 24 * 3600  # refresh when less than a day of validity remains

#: imputed USD per 1M tokens (SPEC.md "Models"; subscription, no real billing)
CODEX_PRICES: dict[str, Pricing] = {
    "gpt-6-luna": Pricing(input=0.10, cached_input=0.01, cache_write=0.125, output=0.50),
}


# --------------------------------------------------------------------------- #
# OAuth token store
# --------------------------------------------------------------------------- #


def _jwt_claims(token: str) -> dict:
    """Decode JWT payload without verification (only to read the account id)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:  # noqa: BLE001 - malformed token -> no claims
        return {}


class TokenStore:
    """Codex OAuth tokens persisted in a JSON file (``access_token``, ``refresh_token``,
    ``expires_in``, ``obtained_at`` + whatever else the token endpoint returned).

    Thread-safe; writes are atomic (temp file + ``os.replace``) with mode 0600.
    """

    def __init__(self, path: str, session: requests.Session | None = None, client_id: str = OAUTH_CLIENT_ID):
        self.path = path
        self.client_id = client_id
        self.session = session or requests.Session()
        self._lock = threading.RLock()
        self._data: dict = self._load()

    def _load(self) -> dict:
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("access_token") or not data.get("refresh_token"):
            raise ProviderError(f"token file {self.path} lacks access_token/refresh_token")
        return data

    def _save(self, data: dict) -> None:
        d = os.path.dirname(os.path.abspath(self.path)) or "."
        fd, tmp = tempfile.mkstemp(prefix=".openai-tokens.", suffix=".tmp", dir=d)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
            os.chmod(self.path, 0o600)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ----- public API -------------------------------------------------------- #

    @property
    def expires_at(self) -> float:
        d = self._data
        if d.get("expires_at"):
            return float(d["expires_at"])
        obtained = float(d.get("obtained_at") or 0)
        return obtained + float(d.get("expires_in") or 0)

    def access_token(self) -> str:
        """Return a valid access token, refreshing when (nearly) expired."""
        with self._lock:
            now = time.time()
            if now >= self.expires_at - REFRESH_MARGIN_S:
                earliest = self._data.get("earliest_refresh_at")
                if now >= self.expires_at or earliest is None or now >= float(earliest):
                    self.refresh()
            return self._data["access_token"]

    def account_id(self) -> str:
        claims = _jwt_claims(self._data["access_token"])
        acc = (claims.get("https://api.openai.com/auth") or {}).get("chatgpt_account_id")
        if not acc:
            raise ProviderError("access token has no chatgpt_account_id claim")
        return acc

    def refresh(self) -> None:
        """Exchange the refresh token; persist the rotated pair atomically."""
        with self._lock:
            # Re-read the file first: another process may have rotated the token already.
            try:
                on_disk = self._load()
                if on_disk.get("refresh_token") != self._data.get("refresh_token") and \
                        float(on_disk.get("obtained_at") or 0) > float(self._data.get("obtained_at") or 0):
                    self._data = on_disk
                    log.info("codex: picked up rotated tokens from disk")
                    if time.time() < self.expires_at - 60:
                        return
            except (OSError, ValueError, ProviderError):
                pass
            body = {"grant_type": "refresh_token", "client_id": self.client_id,
                    "refresh_token": self._data["refresh_token"]}
            t0 = time.time()
            resp = self.session.post(OAUTH_TOKEN_URL, json=body, timeout=(CONNECT_TIMEOUT_S, 60))
            if resp.status_code != 200:
                # Do not include the body verbatim in logs beyond a short, token-free snippet.
                snippet = resp.text[:200].replace(self._data["refresh_token"], "<rt>")
                raise AuthError(f"token refresh failed: HTTP {resp.status_code}: {snippet}", resp.status_code)
            new = resp.json()
            if not new.get("access_token"):
                raise AuthError("token refresh returned no access_token")
            merged = dict(self._data)
            merged.update(new)
            merged["obtained_at"] = t0
            merged.pop("expires_at", None)
            if not new.get("refresh_token"):
                merged["refresh_token"] = self._data["refresh_token"]  # no rotation this time
            # Keep the author's convention: earliest_refresh_at = expiry - 24h.
            merged["earliest_refresh_at"] = int(t0 + float(merged.get("expires_in") or 0) - REFRESH_MARGIN_S)
            # The server has already rotated the refresh token: adopt the new pair in memory first so
            # that a failed write cannot leave this process with a revoked token.
            self._data = merged
            try:
                self._save(merged)
            except OSError as e:
                log.critical("codex: tokens rotated but could not be persisted to %s: %s", self.path, e)
                raise
            log.info("codex: access token refreshed; expires in %.1f h", float(merged.get("expires_in") or 0) / 3600)


def find_token_file(explicit: str | None = None) -> str:
    """Locate the token file: explicit arg > ``OPENAI_CODEX_TOKENS`` env > defaults."""
    candidates = [c for c in (explicit, env_or_none("OPENAI_CODEX_TOKENS")) if c] + list(DEFAULT_TOKEN_PATHS)
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise ProviderError(f"Codex token file not found; tried {candidates}")


# --------------------------------------------------------------------------- #
# SSE parsing
# --------------------------------------------------------------------------- #


def iter_sse(resp: requests.Response) -> Iterator[tuple[str | None, str]]:
    """Yield ``(event, data)`` pairs from a ``text/event-stream`` response."""
    event: str | None = None
    data_lines: list[str] = []
    for raw in resp.iter_lines():
        if raw is None:
            continue
        line = (raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw).rstrip("\r")
        if line == "":
            if data_lines:
                yield event, "\n".join(data_lines)
            event, data_lines = None, []
            continue
        if line.startswith(":"):
            continue
        key, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if key == "event":
            event = value
        elif key == "data":
            data_lines.append(value)
    if data_lines:
        yield event, "\n".join(data_lines)


def codex_usage(raw: dict, model: str) -> Usage:
    """Convert a Responses-API ``usage`` object to :class:`Usage` with imputed cost."""
    inp = int(raw.get("input_tokens") or 0)
    details = raw.get("input_tokens_details") or {}
    cached = int(details.get("cached_tokens") or 0)
    written = int(details.get("cache_write_tokens") or 0)  # reported by the Codex backend
    out = int(raw.get("output_tokens") or 0)
    reasoning = int((raw.get("output_tokens_details") or {}).get("reasoning_tokens") or 0)
    u = Usage(input_tokens=inp, cached_input_tokens=cached, cache_write_tokens=written, output_tokens=out,
              reasoning_tokens=reasoning, cost_usd=None, raw=dict(raw))
    price = CODEX_PRICES.get(model)
    if price is not None:
        u.cost_usd = price.cost(u)
    return u


# --------------------------------------------------------------------------- #
# Conversation
# --------------------------------------------------------------------------- #


class CodexConversation(Conversation):
    """History as a list of Responses-API input items.

    Assistant output items (``reasoning`` with ``encrypted_content``, ``message``,
    ``function_call``) are appended exactly as returned; user messages are
    ``{"type":"message","role":"user","content":[{"type":"input_text",...}]}`` and
    tool results are ``function_call_output`` items.
    """

    def __init__(self, provider: "CodexProvider", system_prompt: str, tools: list[ToolSpec], conv_id: str,
                 items: list[dict] | None = None, last_usage: dict | None = None):
        self.provider = provider
        self.system_prompt = system_prompt
        self.tools = list(tools)
        self.conv_id = conv_id
        self.items: list[dict] = items if items is not None else []
        self._last_usage: Usage | None = Usage.from_dict(last_usage) if last_usage else None

    def add_user(self, text: str) -> None:
        self.items.append({"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]})

    def add_tool_results(self, results: list[tuple[str, str]]) -> None:
        for call_id, output in results:
            self.items.append({"type": "function_call_output", "call_id": call_id, "output": output})

    def _tools_payload(self) -> list[dict]:
        return [{"type": "function", "name": t.name, "description": t.description, "parameters": t.parameters,
                 "strict": False} for t in self.tools]

    def _build_body(self) -> dict:
        p = self.provider
        body: dict[str, Any] = {
            "model": p.model,
            "instructions": self.system_prompt,
            "input": deepcopy_json(self.items),
            "tools": self._tools_payload(),
            "tool_choice": "auto",
            "parallel_tool_calls": p.parallel_tool_calls,
            "store": False,
            "stream": True,
            "include": ["reasoning.encrypted_content"],
            "reasoning": {"effort": p.reasoning_effort, "summary": p.reasoning_summary},
            "prompt_cache_key": self.conv_id,
        }
        if p.text_verbosity is not None:
            body["text"] = {"verbosity": p.text_verbosity}
        return body

    def step(self) -> TurnResult:
        p = self.provider
        body = self._build_body()
        t_start = time.monotonic()

        def attempt(n: int) -> dict:
            token = p.tokens.access_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "chatgpt-account-id": p.tokens.account_id(),
                "OpenAI-Beta": "responses=experimental",
                "originator": "codex_cli_rs",
                "accept": "text/event-stream",
                "content-type": "application/json",
                "session_id": self.conv_id,
            }
            t0 = time.monotonic()
            events: list[dict] = []
            final: dict | None = None
            error: dict | None = None
            status = None
            try:
                with p.session.post(CODEX_RESPONSES_URL, headers=headers, json=body, stream=True,
                                    timeout=(CONNECT_TIMEOUT_S, REQUEST_TIMEOUT_S)) as resp:
                    status = resp.status_code
                    if resp.status_code != 200:
                        text = resp.text
                        p.raw_log({"conv_id": self.conv_id, "attempt": n, "url": CODEX_RESPONSES_URL,
                                   "status": status, "latency_s": round(time.monotonic() - t0, 3),
                                   "request": {"headers": headers, "body": body}, "response": text[:4000]})
                        raise classify_http_error(resp.status_code, text, resp.headers)
                    for ev_name, data in iter_sse(resp):
                        try:
                            ev = json.loads(data)
                        except ValueError:
                            continue
                        ev_type = ev.get("type") or ev_name
                        if ev_type not in ("response.output_text.delta", "response.reasoning_summary_text.delta",
                                           "response.function_call_arguments.delta",
                                           "response.reasoning_text.delta"):
                            events.append(ev)  # keep non-delta events for the raw log
                        if ev_type == "response.completed":
                            final = ev.get("response")
                        elif ev_type == "response.incomplete":
                            final = ev.get("response")
                        elif ev_type in ("response.failed", "error"):
                            error = ev
                            break
            finally:
                lat = time.monotonic() - t0
                p.raw_log({"conv_id": self.conv_id, "attempt": n, "url": CODEX_RESPONSES_URL, "status": status,
                           "latency_s": round(lat, 3), "request": {"headers": headers, "body": body},
                           "response": {"final": final, "error": error, "events": events}})
            if error is not None:
                err = (error.get("response") or {}).get("error") or error.get("error") or error
                code = str(err.get("code") or "")
                msg = f"codex stream error: {json.dumps(err)[:500]}"
                if code in ("rate_limit_exceeded", "server_error", "overloaded") or "rate" in code:
                    raise RetryableError(msg, status, err)
                raise ProviderError(msg, status, err)
            if final is None:
                raise RetryableError("codex stream ended without response.completed", status)
            return final

        final = retry_call(attempt, what=f"codex[{self.conv_id}]", on_auth_error=p.tokens.refresh)
        return self._ingest(final, time.monotonic() - t_start)

    def _ingest(self, response: dict, latency: float) -> TurnResult:
        output: list[dict] = response.get("output") or []
        # Append every output item unchanged (reasoning items carry encrypted_content).
        self.items.extend(deepcopy_json(output))
        texts: list[str] = []
        summaries: list[str] = []
        calls: list[ToolCall] = []
        for item in output:
            t = item.get("type")
            if t == "message":
                for c in item.get("content") or []:
                    if c.get("type") in ("output_text", "text") and c.get("text"):
                        texts.append(c["text"])
            elif t == "reasoning":
                for s in item.get("summary") or []:
                    if s.get("text"):
                        summaries.append(s["text"])
            elif t == "function_call":
                calls.append(ToolCall(id=item["call_id"], name=item["name"],
                                      arguments=parse_tool_arguments(item.get("arguments"))))
        usage = codex_usage(response.get("usage") or {}, self.provider.model)
        self._last_usage = usage
        status = response.get("status") or "completed"
        if calls:
            stop = "tool_use"
        elif status == "completed":
            stop = "end_turn"
        elif status == "incomplete":
            reason = ((response.get("incomplete_details") or {}).get("reason") or "")
            stop = "max_tokens" if "max_output_tokens" in reason else "incomplete"
        else:
            stop = status
        return TurnResult(
            text="\n".join(texts) if texts else None,
            tool_calls=calls,
            reasoning_summary="\n\n".join(summaries) if summaries else None,
            usage=usage,
            stop_reason=stop,
            latency_s=latency,
            raw=response,
        )

    def export_state(self) -> dict:
        return {
            "version": 1,
            "provider": self.provider.key,
            "model": self.provider.model,
            "conv_id": self.conv_id,
            "system_prompt": self.system_prompt,
            "tools": [t.to_dict() for t in self.tools],
            "items": deepcopy_json(self.items),
            "last_usage": self._last_usage.to_dict() if self._last_usage else None,
        }

    def history_view(self) -> list[dict]:
        view: list[dict] = []
        pending_summary: list[str] = []
        pending_calls: list[dict] = []
        pending_text: list[str] = []

        def flush_assistant() -> None:
            if pending_summary or pending_calls or pending_text:
                view.append({"role": "assistant", "text": "\n".join(pending_text) or None,
                             "tool_calls": list(pending_calls), "tool_results": [],
                             "reasoning_summary": "\n\n".join(pending_summary) or None})
                pending_summary.clear(); pending_calls.clear(); pending_text.clear()

        pending_results: list[dict] = []

        def flush_results() -> None:
            if pending_results:
                view.append({"role": "tool", "text": None, "tool_calls": [], "tool_results": list(pending_results),
                             "reasoning_summary": None})
                pending_results.clear()

        for item in self.items:
            t = item.get("type")
            if t == "message" and item.get("role") == "user":
                flush_assistant(); flush_results()
                txt = "\n".join(c.get("text", "") for c in item.get("content") or [] if isinstance(c, dict))
                view.append({"role": "user", "text": txt, "tool_calls": [], "tool_results": [],
                             "reasoning_summary": None})
            elif t == "function_call_output":
                flush_assistant()
                pending_results.append({"call_id": item.get("call_id"), "output": item.get("output")})
            elif t == "reasoning":
                flush_results()
                pending_summary.extend(s.get("text", "") for s in item.get("summary") or [] if s.get("text"))
            elif t == "message":
                flush_results()
                pending_text.extend(c.get("text", "") for c in item.get("content") or []
                                    if c.get("type") in ("output_text", "text"))
            elif t == "function_call":
                flush_results()
                pending_calls.append({"id": item.get("call_id"), "name": item.get("name"),
                                      "arguments": parse_tool_arguments(item.get("arguments"))})
        flush_assistant(); flush_results()
        return view

    def context_tokens_estimate(self) -> int:
        if self._last_usage is None:
            return 0
        return self._last_usage.input_tokens + self._last_usage.output_tokens


class CodexProvider(Provider):
    """Provider for the ChatGPT Codex backend (Responses API over SSE).

    Parameters
    ----------
    tokens_path:
        JSON token file; defaults to ``$OPENAI_CODEX_TOKENS`` or
        ``/workspace/secrets/openai-tokens.json``.
    reasoning_effort:
        ``low``/``medium``/``high``/``xhigh``/``max`` (default ``medium``, per SPEC).
    reasoning_summary:
        ``auto`` (default), ``concise``, ``detailed`` or ``None``.
    parallel_tool_calls:
        Sent as the Responses-API ``parallel_tool_calls`` flag (default ``True``).
    text_verbosity:
        Optional ``text.verbosity`` (``low``/``medium``/``high``); ``None`` omits it.
    """

    RAW_LOG_OPAQUE_KEYS = ("encrypted_content",)

    def __init__(self, model: str = "gpt-6-luna", key: str = "luna", *, tokens_path: str | None = None,
                 reasoning_effort: str = "medium", reasoning_summary: str | None = "auto",
                 parallel_tool_calls: bool = True, text_verbosity: str | None = None,
                 raw_log_path: str | None = None):
        super().__init__(key=key, model=model, raw_log_path=raw_log_path)
        self.tokens = TokenStore(find_token_file(tokens_path), session=self.session)
        self.reasoning_effort = reasoning_effort
        self.reasoning_summary = reasoning_summary
        self.parallel_tool_calls = parallel_tool_calls
        self.text_verbosity = text_verbosity

    def new_conversation(self, system_prompt: str, tools: list[ToolSpec], conv_id: str) -> CodexConversation:
        return CodexConversation(self, system_prompt, tools, conv_id)

    def restore_conversation(self, state: dict) -> CodexConversation:
        if state.get("provider") not in (self.key, "openai_codex") and state.get("model") != self.model:
            raise ProviderError(f"state is for provider {state.get('provider')!r}/{state.get('model')!r}")
        return CodexConversation(
            self, state["system_prompt"], [ToolSpec.from_dict(t) for t in state["tools"]], state["conv_id"],
            items=deepcopy_json(state["items"]), last_usage=state.get("last_usage"),
        )

    def list_models(self) -> list[dict]:
        """``GET /backend-api/codex/models`` (diagnostics)."""
        headers = {"Authorization": f"Bearer {self.tokens.access_token()}",
                   "chatgpt-account-id": self.tokens.account_id(), "originator": "codex_cli_rs"}
        resp = self.session.get(CODEX_MODELS_URL, headers=headers, timeout=(CONNECT_TIMEOUT_S, 60))
        if resp.status_code != 200:
            raise classify_http_error(resp.status_code, resp.text, resp.headers)
        return resp.json().get("models", [])
