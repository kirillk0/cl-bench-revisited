"""Provider-agnostic interface for the memory-modes experiment.

This module defines the data classes and abstract classes described in
``SPEC.md`` ("Provider interface") plus small shared helpers used by the three
concrete providers (Anthropic Messages API, OpenAI Codex backend, OpenRouter):

* :class:`ToolSpec`, :class:`ToolCall`, :class:`Usage`, :class:`TurnResult`
* :class:`Conversation` / :class:`Provider` abstract base classes
* :func:`retry_call` -- exponential backoff on 429 / 5xx / network errors
* :class:`RawLogger` -- JSONL raw request/response log with secret redaction
* :func:`redact` -- recursive redaction of secret-looking keys/values

Only ``requests`` and the standard library are used.

Token accounting convention (identical for every provider)
----------------------------------------------------------
``Usage.input_tokens`` is the *total* prompt size of the request, i.e. it
already **includes** ``cached_input_tokens`` (read from the prompt cache) and
``cache_write_tokens`` (written to the cache on this request).
``Usage.output_tokens`` is the total generated size and **includes**
``reasoning_tokens``.  Costs are therefore computed as::

    uncached_in = input_tokens - cached_input_tokens - cache_write_tokens
    cost = uncached_in * p_in + cached * p_cached + cache_write * p_write
         + output_tokens * p_out
"""

from __future__ import annotations

import abc
import copy
import dataclasses
import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, TypeVar

import requests

log = logging.getLogger("clrev.providers")

# --------------------------------------------------------------------------- #
# Data classes (SPEC: Provider interface)
# --------------------------------------------------------------------------- #


@dataclass
class ToolSpec:
    """A tool exposed to the model (JSON-schema parameters)."""

    name: str
    description: str
    parameters: dict  # JSON schema object

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "ToolSpec":
        return cls(name=d["name"], description=d["description"], parameters=dict(d["parameters"]))


@dataclass
class ToolCall:
    """A tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class Usage:
    """Token usage of one model call (see module docstring for conventions).

    ``cost_usd`` is ``None`` only if it could not be determined at all.
    ``raw`` carries the provider's own usage object untouched.
    """

    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float | None = None
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Usage":
        return cls(
            input_tokens=int(d.get("input_tokens") or 0),
            cached_input_tokens=int(d.get("cached_input_tokens") or 0),
            cache_write_tokens=int(d.get("cache_write_tokens") or 0),
            output_tokens=int(d.get("output_tokens") or 0),
            reasoning_tokens=int(d.get("reasoning_tokens") or 0),
            cost_usd=d.get("cost_usd"),
            raw=dict(d.get("raw") or {}),
        )

    def __add__(self, other: "Usage") -> "Usage":
        cost = None
        if self.cost_usd is not None or other.cost_usd is not None:
            cost = (self.cost_usd or 0.0) + (other.cost_usd or 0.0)
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            cost_usd=cost,
            raw={},
        )


@dataclass
class TurnResult:
    """Outcome of one :meth:`Conversation.step` call.

    ``stop_reason`` is normalised to one of ``"tool_use"``, ``"end_turn"``,
    ``"max_tokens"``, ``"refusal"``, ``"incomplete"`` or the provider's raw
    value when none of those apply.  The raw response is in ``raw``.
    """

    text: str | None
    tool_calls: list[ToolCall]
    reasoning_summary: str | None
    usage: Usage
    stop_reason: str
    latency_s: float
    raw: dict


# --------------------------------------------------------------------------- #
# Pricing helper
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Pricing:
    """USD per 1M tokens."""

    input: float
    cached_input: float
    cache_write: float
    output: float

    def cost(self, u: Usage) -> float:
        uncached = max(0, u.input_tokens - u.cached_input_tokens - u.cache_write_tokens)
        return (
            uncached * self.input
            + u.cached_input_tokens * self.cached_input
            + u.cache_write_tokens * self.cache_write
            + u.output_tokens * self.output
        ) / 1_000_000.0


# --------------------------------------------------------------------------- #
# Errors and retry policy
# --------------------------------------------------------------------------- #


class ProviderError(RuntimeError):
    """Non-retryable provider failure (4xx other than 429, malformed response...)."""

    def __init__(self, message: str, status: int | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


class RetryableError(ProviderError):
    """Transient failure: 429, 5xx, network error, truncated stream."""

    def __init__(self, message: str, status: int | None = None, body: Any = None,
                 retry_after_s: float | None = None):
        super().__init__(message, status, body)
        self.retry_after_s = retry_after_s


class AuthError(ProviderError):
    """401/403: the caller may refresh credentials and retry once."""


RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 529}
MAX_ATTEMPTS = 6
REQUEST_TIMEOUT_S = 180.0
CONNECT_TIMEOUT_S = 30.0

T = TypeVar("T")


def classify_http_error(status: int, body_text: str, headers: Mapping[str, str] | None = None) -> ProviderError:
    """Map an HTTP error status to :class:`RetryableError` / :class:`AuthError` / :class:`ProviderError`."""
    snippet = body_text[:2000]
    if status in RETRYABLE_STATUS:
        ra = None
        if headers:
            v = headers.get("retry-after") or headers.get("Retry-After")
            try:
                ra = float(v) if v else None
            except ValueError:
                ra = None
        return RetryableError(f"HTTP {status}: {snippet}", status, snippet, retry_after_s=ra)
    if status in (401, 403):
        return AuthError(f"HTTP {status}: {snippet}", status, snippet)
    return ProviderError(f"HTTP {status}: {snippet}", status, snippet)


def retry_call(fn: Callable[[int], T], *, what: str, max_attempts: int = MAX_ATTEMPTS,
               base_delay_s: float = 1.0, max_delay_s: float = 30.0,
               on_auth_error: Callable[[], None] | None = None) -> T:
    """Run ``fn(attempt)`` with exponential backoff.

    ``fn`` must raise :class:`RetryableError` (or a ``requests`` exception) for
    transient failures; anything else propagates immediately.  If
    ``on_auth_error`` is given, an :class:`AuthError` triggers it once (e.g. a
    token refresh) and the call is retried; a second :class:`AuthError` propagates.
    Every attempt is logged (never including secrets).
    """
    auth_retried = False
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        t0 = time.monotonic()
        try:
            result = fn(attempt)
            log.info("%s: attempt %d ok (%.2fs)", what, attempt, time.monotonic() - t0)
            return result
        except AuthError as e:
            if on_auth_error is not None and not auth_retried:
                auth_retried = True
                log.warning("%s: attempt %d auth error (%s); refreshing credentials and retrying", what, attempt, e.status)
                on_auth_error()
                continue
            raise
        except RetryableError as e:
            last_exc = e
            delay = e.retry_after_s
            log.warning("%s: attempt %d/%d failed (retryable, status=%s): %s", what, attempt, max_attempts, e.status, str(e)[:300])
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ContentDecodingError) as e:
            last_exc = e
            delay = None
            log.warning("%s: attempt %d/%d network error: %s", what, attempt, max_attempts, str(e)[:300])
        if attempt == max_attempts:
            break
        if delay is None:
            delay = min(max_delay_s, base_delay_s * (2 ** (attempt - 1)))
        delay = delay * (0.7 + 0.6 * random.random())  # jitter
        time.sleep(delay)
    assert last_exc is not None
    raise RetryableError(f"{what}: giving up after {max_attempts} attempts: {last_exc}") from last_exc


# --------------------------------------------------------------------------- #
# Redaction and raw logging
# --------------------------------------------------------------------------- #

_SECRET_KEYS = {
    "authorization", "x-api-key", "api_key", "apikey", "access_token", "refresh_token", "id_token",
    "token", "secret", "password", "chatgpt-account-id",
}
_SECRET_PREFIXES = ("sk-", "sk-ant-", "Bearer ", "eyJ")  # API keys, bearer tokens, JWTs


def _redact_str(s: str) -> str:
    if len(s) > 12 and s.startswith(_SECRET_PREFIXES):
        return f"<redacted:{len(s)} chars>"
    return s


def redact(obj: Any, *, opaque_keys: Iterable[str] = (), opaque_max_chars: int | None = None) -> Any:
    """Return a deep copy of ``obj`` with secrets masked.

    Keys in ``_SECRET_KEYS`` (case-insensitive) are replaced with a marker; string
    values that look like API keys / bearer tokens / JWTs are masked too.
    Keys listed in ``opaque_keys`` (e.g. ``encrypted_content``, ``signature``)
    are truncated to ``opaque_max_chars`` when that is not ``None`` -- they are
    not secrets but can be very large and are preserved in full in
    :meth:`Conversation.export_state` anyway.
    """
    opaque = set(opaque_keys)

    def rec(x: Any, key: str | None) -> Any:
        if isinstance(x, Mapping):
            out = {}
            for k, v in x.items():
                kl = str(k).lower()
                if kl in _SECRET_KEYS and isinstance(v, str):
                    out[k] = f"<redacted:{len(v)} chars>"
                else:
                    out[k] = rec(v, str(k))
            return out
        if isinstance(x, (list, tuple)):
            return [rec(v, key) for v in x]
        if isinstance(x, str):
            if key in opaque and opaque_max_chars is not None and len(x) > opaque_max_chars:
                return x[:opaque_max_chars] + f"...<truncated, {len(x)} chars total>"
            return _redact_str(x)
        return x

    return rec(obj, None)


class RawLogger:
    """Append-only JSONL log of raw request/response pairs with redaction.

    ``path`` may be ``None`` (logging disabled).  Thread-safe.
    """

    def __init__(self, path: str | os.PathLike[str] | None = None, *, opaque_keys: Iterable[str] = (),
                 opaque_max_chars: int | None = 400):
        self.path = os.fspath(path) if path is not None else None
        self.opaque_keys = tuple(opaque_keys)
        self.opaque_max_chars = opaque_max_chars
        self._lock = threading.Lock()

    def write(self, record: Mapping[str, Any]) -> None:
        if not self.path:
            return
        rec = dict(record)
        rec.setdefault("ts", time.time())
        safe = redact(rec, opaque_keys=self.opaque_keys, opaque_max_chars=self.opaque_max_chars)
        line = json.dumps(safe, ensure_ascii=False, default=str)
        with self._lock:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")


# --------------------------------------------------------------------------- #
# Abstract classes
# --------------------------------------------------------------------------- #


class Conversation(abc.ABC):
    """One provider-native message history.

    Lifecycle: ``add_user`` -> ``step`` -> (``add_tool_results`` -> ``step``)* ...
    ``step`` performs exactly one model call with the full history and appends the
    assistant turn, including its native reasoning carrier (thinking blocks /
    reasoning items / reasoning_details), to the history.
    """

    provider: "Provider"
    conv_id: str
    system_prompt: str
    tools: list[ToolSpec]

    @abc.abstractmethod
    def add_user(self, text: str) -> None:
        """Append a user text message."""

    @abc.abstractmethod
    def add_tool_results(self, results: list[tuple[str, str]]) -> None:
        """Append tool results as ``(call_id, output_text)`` pairs."""

    @abc.abstractmethod
    def step(self) -> TurnResult:
        """One model call with the full history; appends the assistant turn."""

    @abc.abstractmethod
    def export_state(self) -> dict:
        """JSON-serialisable snapshot; ``Provider.restore_conversation`` reproduces the exact native history."""

    @abc.abstractmethod
    def history_view(self) -> list[dict]:
        """Provider-agnostic rendering: ``{role, text, tool_calls, tool_results, reasoning_summary}``."""

    @abc.abstractmethod
    def context_tokens_estimate(self) -> int:
        """Last known prompt size from usage (plus the last response's output tokens)."""


class Provider(abc.ABC):
    """Factory for conversations against one model.

    Attributes
    ----------
    key:
        Short key from SPEC (``luna`` / ``haiku`` / ``glm``).
    model:
        Provider model id.
    raw_log_path:
        Path of the JSONL raw log (``None`` disables raw logging).  Settable at
        any time; conversations read it on every request.
    """

    key: str
    model: str
    #: keys whose (large, opaque) string values are truncated in the raw log
    RAW_LOG_OPAQUE_KEYS: tuple[str, ...] = ()

    def __init__(self, key: str, model: str, raw_log_path: str | None = None):
        self.key = key
        self.model = model
        self._raw_log_path = raw_log_path
        self._raw_logger = RawLogger(raw_log_path, opaque_keys=self.RAW_LOG_OPAQUE_KEYS)
        self.session = requests.Session()

    # raw_log_path is a property so that reassigning it swaps the logger
    @property
    def raw_log_path(self) -> str | None:
        return self._raw_log_path

    @raw_log_path.setter
    def raw_log_path(self, value: str | None) -> None:
        self._raw_log_path = value
        self._raw_logger = RawLogger(value, opaque_keys=self.RAW_LOG_OPAQUE_KEYS)

    def raw_log(self, record: Mapping[str, Any]) -> None:
        """Append one redacted record to the raw log (no-op when disabled)."""
        self._raw_logger.write({"provider": self.key, "model": self.model, **record})

    @abc.abstractmethod
    def new_conversation(self, system_prompt: str, tools: list[ToolSpec], conv_id: str) -> Conversation:
        """Start a fresh conversation."""

    @abc.abstractmethod
    def restore_conversation(self, state: dict) -> Conversation:
        """Rebuild a conversation from :meth:`Conversation.export_state` output."""


# --------------------------------------------------------------------------- #
# Small shared utilities
# --------------------------------------------------------------------------- #


def parse_tool_arguments(raw: Any) -> dict:
    """Parse tool-call arguments that may arrive as a JSON string or a dict.

    Invalid JSON is preserved under ``{"_raw": "<string>"}`` so the runner can
    surface the problem to the model instead of crashing.
    """
    if isinstance(raw, Mapping):
        return dict(raw)
    if raw is None or raw == "":
        return {}
    if isinstance(raw, str):
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw}
        return val if isinstance(val, dict) else {"_value": val}
    return {"_value": raw}


def deepcopy_json(obj: T) -> T:
    """Deep copy restricted to JSON-compatible data (used for export_state)."""
    return copy.deepcopy(obj)


def env_or_none(name: str) -> str | None:
    v = os.environ.get(name)
    return v if v else None
