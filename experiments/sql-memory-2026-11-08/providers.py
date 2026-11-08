"""Native, lossless tool sessions using requests (no provider SDKs).

No network activity occurs during construction/import/state restoration. Only
step() sends a request; bash is declared, never executed here. Sessions are not
thread-safe. There are no automatic retries, including on 400/429 or SSE failure.

    session = create('anthropic', 'claude-haiku-5-5', system, session_id,
                     config={'thinking': {'type': 'adaptive'}})
    session.add_user('Inspect the database')
    turn = session.step()
    # Execute approved tool calls externally, then:
    session.add_tool_results([{'id': call_id, 'output': stdout}])

Config keys (also accepted as constructor/create keyword arguments):
  max_tokens: 8192 (Anthropic/OpenRouter only).
  thinking: Anthropic dict; defaults to {'type': 'adaptive'}. None/False omits
    thinking, True selects adaptive. No support-probe or fallback request is made.
  reasoning: override OR/Codex reasoning dict; None/False disables it.
  cache_control: Anthropic cache marker; default {'type': 'ephemeral'}.
    None/False disables explicit caching; e.g. add ttl='1h' to select that TTL.
  connect_timeout: 15 seconds; read_timeout: 120 seconds (may be set to 300).
    Requests read timeout is an inactivity timeout, NOT a wall-clock deadline.
  codex_auth_path: /workspace/.credentials/codex-auth.json.
  codex_include: defaults to ['reasoning.encrypted_content']; optionally add
    'output.encrypted_content' when supported by the selected backend. No retry
    with a different include list is attempted after an error.
  api_key_env: overrides the provider's usual environment-variable name.
  rates: USD per MILLION tokens: input, output, cache_read, cache_write,
    cache_write_5m, cache_write_1h. Only nonzero token categories require rates.
    cache_write is the fallback for TTL-specific writes. No assumed prices.
  model_rates: {model: rates}, overriding rates for the resolved/requested model.

api_key and http_client may be injected as keyword arguments, NOT config keys.
Neither is exported. http_client must support requests.Session.post(). Its retry
policy is the caller's responsibility; the default client explicitly has none.

step() returns tool_calls, final_text, usage (unmodified native usage), cost_usd,
response_id, elapsed_s, plus token_accounting and cost_source. Accounting counts
cached input and reasoning output only once. cost_usd=None means unpriced (not
free). OpenRouter usage.cost, when supplied, is authoritative including zero.

export_state() returns a private JSON-compatible snapshot; as_json=True returns
JSON text. It contains ALL native reasoning/encrypted content and tool outputs.
Never log/publish it. No credentials are included. Write snapshots yourself to a
private file (0600), preferably atomically. from_state() accepts either format.

An interrupted request has an unknown charge/outcome. A sanitized ProviderError
is raised and blocks further step() calls until acknowledge_failure() is called
explicitly. This also applies to failed/incomplete/malformed successful responses.
HTTP failures likewise require acknowledgement; nothing is retried implicitly.
Codex expired JWTs fail locally; OAuth refresh is intentionally not automatic.
"""
from __future__ import annotations

import base64
import copy
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Mapping

import requests
from requests.adapters import HTTPAdapter

__all__ = [
    'NativeSession', 'AnthropicSession', 'OpenRouterSession', 'CodexSession',
    'ProviderError', 'create', 'from_state',
]

_DEFAULT_MODELS = {
    'anthropic': 'claude-haiku-5-5',
    'openrouter': 'z-ai/glm-5.3-flash',
    'codex': 'gpt-6-luna',
}
_ALIASES = {'or': 'openrouter', 'claude': 'anthropic', 'openai': 'codex'}
_DEFAULT_CONFIG = {
    'max_tokens': 8192,
    'connect_timeout': 15,
    'read_timeout': 120,
    'cache_control': {'type': 'ephemeral'},
    'codex_auth_path': '/workspace/.credentials/codex-auth.json',
    'codex_include': ['reasoning.encrypted_content'],
    'api_key_env': None,
    'rates': None,
    'model_rates': {},
}
_CONFIG_KEYS = set(_DEFAULT_CONFIG) | {'thinking', 'reasoning'}
_PARAMETERS = {
    'type': 'object',
    'properties': {'command': {'type': 'string'}},
    'required': ['command'],
    'additionalProperties': False,
}
_DESCRIPTION = 'Execute a bash command and return its output.'


def _clone(value: Any) -> Any:
    # Deep copying preserves every native field; no typed SDK/schema coercion.
    return copy.deepcopy(value)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class ProviderError(RuntimeError):
    """Safe to log str(error); raw HTTP errors/bodies are deliberately not exposed."""

    def __init__(self, provider: str, kind: str, *, status_code: int | None = None,
                 charge_unknown: bool = False, elapsed_s: float | None = None):
        self.provider = provider
        self.kind = kind
        self.status_code = status_code
        self.charge_unknown = charge_unknown
        self.elapsed_s = elapsed_s
        suffix = f' (HTTP {status_code})' if status_code is not None else ''
        if charge_unknown:
            suffix += '; outcome/charge unknown, no automatic retry'
        super().__init__(f'{provider}: {kind}{suffix}')


def _tool_call(identifier: Any, name: Any, arguments: Any) -> dict:
    if not isinstance(identifier, str) or not identifier:
        raise ValueError('Invalid tool id')
    if name not in ('bash', 'functions.bash'):
        raise ValueError('Unexpected tool name')
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if not isinstance(arguments, dict) or set(arguments) != {'command'}:
        raise ValueError('Invalid bash arguments')
    if not isinstance(arguments['command'], str):
        raise ValueError('Invalid bash command')
    return {'id': identifier, 'name': 'bash', 'arguments': _clone(arguments)}


def _tokens(usage: Mapping, provider: str) -> dict:
    """Normalize accounting without altering the native usage dictionary."""
    def n(obj: Mapping, key: str) -> int:
        value = obj.get(key, 0)
        if value is None:
            return 0
        if not _number(value) or value < 0 or int(value) != value:
            raise ValueError('Invalid usage')
        return int(value)

    write_5m = write_1h = reasoning = 0
    if provider == 'anthropic':
        uncached = n(usage, 'input_tokens')
        cached = n(usage, 'cache_read_input_tokens')
        creation = usage.get('cache_creation') or {}
        write_5m = n(creation, 'ephemeral_5m_input_tokens')
        write_1h = n(creation, 'ephemeral_1h_input_tokens')
        written = n(usage, 'cache_creation_input_tokens')
        if 'cache_creation_input_tokens' not in usage:
            written = write_5m + write_1h
        if write_5m + write_1h > written:
            raise ValueError('Invalid cache accounting')
        inputs = uncached + cached + written
        outputs = n(usage, 'output_tokens')
    else:
        chat = provider == 'openrouter'
        inputs = n(usage, 'prompt_tokens' if chat else 'input_tokens')
        outputs = n(usage, 'completion_tokens' if chat else 'output_tokens')
        detail = usage.get('prompt_tokens_details' if chat else 'input_tokens_details') or {}
        cached = n(detail, 'cached_tokens')
        written = n(detail, 'cache_write_tokens')
        # OR cache writes are a subset of prompt_tokens, as are cache reads.
        uncached = inputs - cached - written
        if uncached < 0:
            raise ValueError('Invalid cached token accounting')
        out_detail = usage.get('completion_tokens_details' if chat else 'output_tokens_details') or {}
        reasoning = n(out_detail, 'reasoning_tokens')
    return {
        'input_tokens': inputs,
        'input_uncached_tokens': uncached,
        'cache_read_input_tokens': cached,
        'cache_creation_input_tokens': written,
        'cache_creation_5m_input_tokens': write_5m,
        'cache_creation_1h_input_tokens': write_1h,
        'output_tokens': outputs,
        'reasoning_tokens': reasoning,
        'total_tokens': inputs + outputs,
    }


def _price(usage: dict, accounting: dict, provider: str, rates: Mapping | None) -> tuple:
    if provider == 'openrouter' and usage.get('cost') is not None:
        cost = usage['cost']
        if not _number(cost):
            raise ValueError('Invalid provider cost')
        return float(cost), 'usage.cost'
    if not usage or rates is None:
        return None, 'unpriced'
    quantities = [
        (accounting['input_uncached_tokens'], 'input'),
        (accounting['output_tokens'], 'output'),
        (accounting['cache_read_input_tokens'], 'cache_read'),
    ]
    w5, w1 = accounting['cache_creation_5m_input_tokens'], accounting['cache_creation_1h_input_tokens']
    quantities += [
        (w5, 'cache_write_5m'), (w1, 'cache_write_1h'),
        (accounting['cache_creation_input_tokens'] - w5 - w1, 'cache_write'),
    ]
    cost = 0.0
    for count, category in quantities:
        if not count:
            continue
        rate = rates.get(category)
        if rate is None and category in ('cache_write_5m', 'cache_write_1h'):
            rate = rates.get('cache_write')
        if rate is None:
            return None, 'unpriced'
        if not _number(rate) or rate < 0:
            raise ValueError('Invalid rate')
        cost += count * rate / 1_000_000
    return cost, 'configured_rates'


class NativeSession:
    """Factory/base class. Use NativeSession.create(...) or module create(...)."""

    provider = ''
    endpoint = ''

    def __init__(self, model: str | None, system_text: str, session_id: str, *,
                 config: Mapping | None = None, api_key: str | None = None,
                 http_client: Any = None, **settings: Any):
        if not self.provider:
            raise TypeError('Use NativeSession.create()')
        if not isinstance(system_text, str) or not isinstance(session_id, str) or not session_id:
            raise ValueError('system_text must be text and session_id must be nonempty text')
        self.model = model or _DEFAULT_MODELS[self.provider]
        if not isinstance(self.model, str):
            raise ValueError('model must be text')
        self.system_text = system_text
        self.session_id = session_id
        supplied = dict(config or {})
        supplied.update(settings)
        if set(supplied) - _CONFIG_KEYS:
            raise ValueError('Unknown provider configuration key')
        self.config = _clone(_DEFAULT_CONFIG)
        self.config.update(_clone(supplied))
        self._validate_config()
        self._api_key = api_key
        self._owns_http = http_client is None
        if http_client is None:
            http_client = requests.Session()
            http_client.mount('https://', HTTPAdapter(max_retries=0))
        self._http = http_client
        self._history: list[dict] = []
        self._pending: list[dict] = []
        self._ready = False
        self._failure: dict | None = None
        self._last_response: dict | None = None
        self._start_history()

    def _validate_config(self) -> None:
        cfg = self.config
        if not isinstance(cfg['max_tokens'], int) or isinstance(cfg['max_tokens'], bool) or cfg['max_tokens'] <= 0:
            raise ValueError('max_tokens must be a positive integer')
        for key in ('connect_timeout', 'read_timeout'):
            if not _number(cfg[key]) or cfg[key] <= 0:
                raise ValueError('Timeouts must be finite and positive')
        for key in ('thinking', 'reasoning', 'cache_control'):
            value = cfg.get(key)
            if value is not None and value is not False and not isinstance(value, dict):
                if not (key == 'thinking' and value is True):
                    raise ValueError('Invalid reasoning/cache configuration')
        includes = cfg['codex_include']
        if not isinstance(includes, list) or not all(isinstance(x, str) for x in includes):
            raise ValueError('codex_include must be a list of strings')
        if 'reasoning.encrypted_content' not in includes:
            raise ValueError('codex_include must retain reasoning.encrypted_content')
        if cfg['api_key_env'] is not None and not isinstance(cfg['api_key_env'], str):
            raise ValueError('api_key_env must be text')
        if not isinstance(cfg['codex_auth_path'], str):
            raise ValueError('codex_auth_path must be text')
        if not isinstance(cfg['model_rates'], dict):
            raise ValueError('model_rates must be a mapping')
        for rates in [cfg['rates'], *cfg['model_rates'].values()]:
            if rates is not None and (not isinstance(rates, dict) or any(
                not _number(v) or v < 0 for v in rates.values() if v is not None
            )):
                raise ValueError('rates must contain nonnegative numeric USD/M values')
        # Ensure exported settings are JSON data; never stringify arbitrary objects.
        try:
            _dump(cfg)
        except (ValueError, TypeError):
            raise ValueError('Configuration must be JSON compatible') from None

    @classmethod
    def create(cls, provider: str, model: str | None, system_text: str,
               session_id: str, **kwargs: Any) -> NativeSession:
        return create(provider, model, system_text, session_id, **kwargs)

    def _start_history(self) -> None:
        pass

    def _ensure_mutable(self) -> None:
        if self._failure is not None:
            raise ProviderError(self.provider, 'previous_failure_requires_acknowledgement',
                                charge_unknown=self._failure['charge_unknown'])

    def add_user(self, text: str) -> None:
        self._ensure_mutable()
        if self._pending:
            raise ValueError('Submit all pending tool results before adding a user task')
        if not isinstance(text, str):
            raise TypeError('User text must be a string')
        if self.provider == 'anthropic':
            message = {'role': 'user', 'content': [{'type': 'text', 'text': text}]}
        elif self.provider == 'openrouter':
            message = {'role': 'user', 'content': text}
        else:
            message = {'role': 'user', 'content': [{'type': 'input_text', 'text': text}]}
        self._history.append(message)
        self._ready = True

    def add_tool_results(self, results: list[dict]) -> None:
        self._ensure_mutable()
        if not self._pending:
            raise ValueError('No pending tool calls')
        if not isinstance(results, list) or not all(isinstance(r, dict) for r in results):
            raise TypeError('Tool results must be a list of mappings')
        by_id = {}
        for result in results:
            identifier = result.get('id')
            if not isinstance(identifier, str) or identifier in by_id or 'output' not in result:
                raise ValueError('Each result needs a unique id and output')
            output = result['output']
            by_id[identifier] = output if isinstance(output, str) else _dump(output)
        if set(by_id) != {call['id'] for call in self._pending}:
            raise ValueError('Submit exactly one result for every pending tool call')
        items = []
        for call in self._pending:
            identifier, output = call['id'], by_id[call['id']]
            if self.provider == 'anthropic':
                items.append({'type': 'tool_result', 'tool_use_id': identifier, 'content': output})
            elif self.provider == 'openrouter':
                items.append({'role': 'tool', 'tool_call_id': identifier, 'content': output})
            else:
                items.append({'type': 'function_call_output', 'call_id': identifier, 'output': output})
        if self.provider == 'anthropic':
            self._history.append({'role': 'user', 'content': items})
        else:
            self._history.extend(items)
        self._pending = []
        self._ready = True

    def _headers(self) -> dict:
        variable = self.config['api_key_env'] or {
            'anthropic': 'ANTHROPIC_API_KEY', 'openrouter': 'OPENROUTER_API_KEY'
        }[self.provider]
        key = self._api_key or os.environ.get(variable)
        if not key:
            raise ProviderError(self.provider, 'missing_api_key')
        if self.provider == 'anthropic':
            return {'x-api-key': key, 'anthropic-version': '2023-06-01',
                    'Content-Type': 'application/json', 'Accept': 'application/json'}
        return {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                'Accept': 'application/json'}

    def _payload(self) -> dict:
        raise NotImplementedError

    def _extract(self, response: dict) -> tuple[list[dict], list[dict], str]:
        raise NotImplementedError

    def _request(self, payload: dict, headers: dict) -> dict:
        response = None
        try:
            response = self._http.post(
                self.endpoint, headers=headers, json=payload,
                stream=self.provider == 'codex', allow_redirects=False,
                timeout=(self.config['connect_timeout'], self.config['read_timeout']),
            )
            if not 200 <= response.status_code < 300:
                raise ProviderError(self.provider, 'http_failure',
                                    status_code=response.status_code,
                                    charge_unknown=response.status_code >= 500)
            if self.provider == 'codex':
                data = self._read_sse(response)
            else:
                try:
                    data = response.json()
                except (ValueError, TypeError):
                    raise ProviderError(self.provider, 'invalid_json_response', charge_unknown=True) from None
            if not isinstance(data, dict):
                raise ProviderError(self.provider, 'invalid_response', charge_unknown=True)
            return data
        except requests.RequestException:
            # Never propagate requests exceptions: they retain headers/body via
            # request/response objects and may contain secrets in their message.
            raise ProviderError(self.provider, 'transport_interrupted', charge_unknown=True) from None
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

    def _read_sse(self, response: Any) -> dict:
        """Parse real SSE framing; discard deltas, keep the final response verbatim."""
        data_lines: list[str] = []
        event_name = ''

        def consume() -> dict | None:
            if not data_lines:
                return None
            raw = '\n'.join(data_lines)
            if raw.strip() == '[DONE]':
                raise ProviderError(self.provider, 'stream_ended_without_completed_response', charge_unknown=True)
            try:
                event = json.loads(raw)
            except (ValueError, TypeError):
                raise ProviderError(self.provider, 'invalid_sse_data', charge_unknown=True) from None
            if not isinstance(event, dict):
                raise ProviderError(self.provider, 'invalid_sse_event', charge_unknown=True)
            kind = event.get('type', event_name)
            if kind in ('response.failed', 'response.incomplete', 'error', 'response.error'):
                # Preserve final native failure data privately, not in exceptions.
                if isinstance(event.get('response'), dict):
                    self._last_response = _clone(event['response'])
                raise ProviderError(self.provider, 'stream_response_failed_or_incomplete', charge_unknown=True)
            if kind == 'response.completed':
                final = event.get('response')
                if not isinstance(final, dict) or final.get('status', 'completed') != 'completed':
                    raise ProviderError(self.provider, 'invalid_completed_response', charge_unknown=True)
                return final
            return None

        for line in response.iter_lines(decode_unicode=False):
            if isinstance(line, bytes):
                try:
                    line = line.decode('utf-8')
                except UnicodeDecodeError:
                    raise ProviderError(self.provider, 'invalid_sse_encoding', charge_unknown=True) from None
            if line == '':
                final = consume()
                if final is not None:
                    return final
                data_lines = []
                event_name = ''
            elif line.startswith('data:'):
                field = line[5:]
                data_lines.append(field[1:] if field.startswith(' ') else field)
            elif line.startswith('event:'):
                event_name = line[6:].lstrip(' ')
            # Ignore comments, id, retry fields. Never honor SSE retry hints.
        final = consume()  # Some servers omit the last blank line.
        if final is not None:
            return final
        raise ProviderError(self.provider, 'stream_interrupted_before_completion', charge_unknown=True)

    def step(self) -> dict:
        self._ensure_mutable()
        if self._pending:
            raise ValueError('Pending tool calls require results before step()')
        if not self._ready:
            raise ValueError('Add a user message or tool results before step()')
        # Local validation/credential errors happen before a potentially billed call.
        payload = self._payload()
        headers = self._headers()
        start = time.monotonic()
        try:
            response = self._request(payload, headers)
            self._last_response = _clone(response)
            try:
                native_items, calls, text = self._extract(response)
                if len({c['id'] for c in calls}) != len(calls):
                    raise ValueError('Duplicate tool ids')
                usage = response.get('usage') or {}
                if not isinstance(usage, dict):
                    raise ValueError('Invalid usage')
                accounting = _tokens(usage, self.provider)
                resolved_model = response.get('model', self.model)
                rates = self.config['model_rates'].get(
                    resolved_model, self.config['model_rates'].get(self.model, self.config['rates']))
                cost, source = _price(usage, accounting, self.provider, rates)
                identifier = response.get('id')
                if identifier is not None and not isinstance(identifier, str):
                    raise ValueError('Invalid response id')
            except (ValueError, TypeError, KeyError, IndexError, AttributeError):
                raise ProviderError(self.provider, 'invalid_or_incomplete_native_response', charge_unknown=True) from None
            # Commit history only after validation; _last_response also retains
            # malformed/incomplete native output privately for manual recovery.
            self._history.extend(_clone(native_items))
            self._pending = _clone(calls)
            self._ready = False
            return {
                'tool_calls': calls,
                'final_text': text,
                'usage': _clone(usage),
                'cost_usd': cost,
                'response_id': identifier,
                'elapsed_s': time.monotonic() - start,
                'token_accounting': accounting,
                'cost_source': source,
            }
        except ProviderError as error:
            error.elapsed_s = time.monotonic() - start
            self._failure = {
                'kind': error.kind, 'status_code': error.status_code,
                'charge_unknown': error.charge_unknown, 'elapsed_s': error.elapsed_s,
            }
            raise

    def acknowledge_failure(self) -> dict | None:
        """Explicitly unblock after caller review; does NOT send or recover anything.

        Retrying the same turn afterwards may incur another charge. For a
        malformed completed response, inspect the PRIVATE exported last_response
        before deciding whether to retry, restore an edited state, or abandon it.
        """
        failure = _clone(self._failure)
        self._failure = None
        return failure

    def export_state(self, *, as_json: bool = False) -> dict | str:
        state = {
            'version': 1, 'provider': self.provider, 'model': self.model,
            'system_text': self.system_text, 'session_id': self.session_id,
            'config': _clone(self.config), 'native_history': _clone(self._history),
            'pending_tool_calls': _clone(self._pending), 'ready': self._ready,
            'failure': _clone(self._failure), 'last_response': _clone(self._last_response),
        }
        return _dump(state) if as_json else state

    @classmethod
    def from_state(cls, state: dict | str, *, config: Mapping | None = None,
                   **kwargs: Any) -> NativeSession:
        """Restore a trusted private snapshot without making network calls."""
        try:
            data = json.loads(state) if isinstance(state, str) else _clone(state)
            if not isinstance(data, dict) or data.get('version') != 1:
                raise ValueError
            if not isinstance(data['native_history'], list) or not all(
                isinstance(item, dict) for item in data['native_history']
            ):
                raise ValueError
            if not isinstance(data['pending_tool_calls'], list) or not isinstance(data['ready'], bool):
                raise ValueError
            pending = [_tool_call(x['id'], x['name'], x['arguments']) for x in data['pending_tool_calls']]
            if len({x['id'] for x in pending}) != len(pending) or (pending and data['ready']):
                raise ValueError
            failure = data['failure']
            if failure is not None and (not isinstance(failure, dict) or not isinstance(failure['charge_unknown'], bool)):
                raise ValueError
            if data['last_response'] is not None and not isinstance(data['last_response'], dict):
                raise ValueError
            settings = dict(data['config'])
            settings.update(config or {})
            session = create(data['provider'], data['model'], data['system_text'],
                             data['session_id'], config=settings, **kwargs)
            if cls is not NativeSession and not isinstance(session, cls):
                session.close()
                raise ValueError
            session._history = data['native_history']
            session._pending = pending
            session._ready = data['ready']
            session._failure = failure
            session._last_response = data['last_response']
            return session
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ValueError('Invalid native session snapshot or configuration') from None

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> NativeSession:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class AnthropicSession(NativeSession):
    provider = 'anthropic'
    endpoint = 'https://api.anthropic.com/v1/messages'

    def _payload(self) -> dict:
        messages = _clone(self._history)
        system = [{'type': 'text', 'text': self.system_text}] if self.system_text else []
        cache = self.config['cache_control']
        if cache:
            if system:
                system[-1]['cache_control'] = _clone(cache)
            for message in reversed(messages):
                if message.get('role') == 'user' and message.get('content'):
                    message['content'][-1]['cache_control'] = _clone(cache)
                    break
        body = {
            'model': self.model, 'max_tokens': self.config['max_tokens'],
            'system': system, 'messages': messages,
            'tools': [{'name': 'bash', 'description': _DESCRIPTION,
                       'input_schema': _clone(_PARAMETERS)}],
        }
        thinking = self.config.get('thinking', {'type': 'adaptive'})
        if thinking:
            body['thinking'] = {'type': 'adaptive'} if thinking is True else _clone(thinking)
        return body

    def _extract(self, response: dict) -> tuple:
        content = response['content']
        if not isinstance(content, list) or response.get('stop_reason') in ('max_tokens', 'pause_turn'):
            raise ValueError('Incomplete Anthropic response')
        calls, text = [], []
        for block in content:
            if block.get('type') == 'tool_use':
                calls.append(_tool_call(block['id'], block['name'], block['input']))
            elif block.get('type') == 'text':
                text.append(block['text'])
        # Includes thinking signatures, redacted_thinking and future block types.
        return [{'role': 'assistant', 'content': content}], calls, ''.join(text)


class OpenRouterSession(NativeSession):
    provider = 'openrouter'
    endpoint = 'https://openrouter.ai/api/v1/chat/completions'

    def _start_history(self) -> None:
        self._history.append({'role': 'system', 'content': self.system_text})

    def _payload(self) -> dict:
        messages = _clone(self._history)
        for message in messages:
            if message.get('role') == 'assistant':
                for call in message.get('tool_calls') or []:
                    call.pop('index', None)  # Response-only field; raw state unchanged.
        body = {
            'model': self.model, 'messages': messages, 'stream': False,
            'max_tokens': self.config['max_tokens'],
            'tools': [{'type': 'function', 'function': {
                'name': 'bash', 'description': _DESCRIPTION, 'parameters': _clone(_PARAMETERS),
            }}],
            'tool_choice': 'auto',
            'session_id': self.session_id,
        }
        reasoning = self.config.get('reasoning', {'enabled': True, 'effort': 'medium'})
        if reasoning:
            body['reasoning'] = _clone(reasoning)
        elif 'reasoning' in self.config:
            body['reasoning'] = {'enabled': False}
        return body

    def _extract(self, response: dict) -> tuple:
        choice = response['choices'][0]
        if choice.get('finish_reason') in ('length', 'error') or response.get('error'):
            raise ValueError('Incomplete OpenRouter response')
        message = choice['message']
        if not isinstance(message, dict) or message.get('role') != 'assistant':
            raise ValueError('Invalid assistant message')
        calls = [_tool_call(x['id'], x['function']['name'], x['function']['arguments'])
                 for x in message.get('tool_calls') or []]
        content = message.get('content')
        if content is None:
            text = ''
        elif isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = ''.join(x['text'] for x in content if x.get('type') == 'text')
        else:
            raise ValueError('Invalid assistant content')
        # Preserve whole message: reasoning, reasoning_details, signatures,
        # refusal, annotations, null content, and unknown future native fields.
        return [message], calls, text


class CodexSession(NativeSession):
    provider = 'codex'
    endpoint = 'https://chatgpt.com/backend-api/codex/responses'

    def _start_history(self) -> None:
        tool = {'type': 'function', 'name': 'bash', 'description': _DESCRIPTION,
                'parameters': _clone(_PARAMETERS), 'strict': True}
        self._history.extend([
            {'type': 'additional_tools', 'role': 'developer', 'tools': [
                {'type': 'namespace', 'name': 'functions', 'description': '', 'tools': [tool]},
            ]},
            {'type': 'message', 'role': 'developer',
             'content': [{'type': 'input_text', 'text': self.system_text}]},
        ])

    def _headers(self) -> dict:
        try:
            auth = json.loads(Path(self.config['codex_auth_path']).read_text(encoding='utf-8'))
            # Accept both the probe's flat credentials and official nested tokens.
            tokens = auth.get('tokens') or auth
            token = tokens['access_token']
            if not isinstance(token, str) or not token:
                raise ValueError
            raw = token.split('.')[1]
            claims = json.loads(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))
            account_id = (claims.get('https://api.openai.com/auth') or {}).get('chatgpt_account_id')
            if not isinstance(account_id, str) or not account_id:
                raise ValueError
            expires = claims.get('exp')
            if expires is not None and (not _number(expires) or expires <= time.time()):
                raise ProviderError(self.provider, 'oauth_token_expired_refresh_required')
        except ProviderError:
            raise
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
            raise ProviderError(self.provider, 'invalid_or_missing_codex_credentials') from None
        # JWT decoding only extracts claims; server validates authenticity.
        return {
            'Authorization': 'Bearer ' + token,
            'ChatGPT-Account-Id': account_id,
            'originator': 'codex_cli_rs',
            'User-Agent': 'codex_cli_rs/0.167.0',
            'x-openai-internal-codex-responses-lite': 'true',
            'Content-Type': 'application/json', 'Accept': 'text/event-stream',
        }

    def _payload(self) -> dict:
        body = {
            'model': self.model, 'input': _clone(self._history),
            'tool_choice': 'auto', 'parallel_tool_calls': False,
            'store': False, 'stream': True,
            'include': _clone(self.config['codex_include']),
            'prompt_cache_key': self.session_id,
        }
        reasoning = self.config.get('reasoning', {'effort': 'medium', 'context': 'all_turns'})
        if reasoning:
            body['reasoning'] = _clone(reasoning)
        return body

    def _extract(self, response: dict) -> tuple:
        if response.get('status', 'completed') != 'completed' or response.get('error'):
            raise ValueError('Incomplete Codex response')
        output = response['output']
        if not isinstance(output, list):
            raise ValueError('Invalid Codex output')
        calls, text = [], []
        for item in output:
            if item.get('type') == 'function_call':
                # call_id, not the response output item's id, correlates results.
                calls.append(_tool_call(item['call_id'], item['name'], item['arguments']))
            elif item.get('type') == 'message':
                for block in item.get('content') or []:
                    if block.get('type') == 'output_text':
                        text.append(block['text'])
                    elif block.get('type') == 'refusal':
                        text.append(block['refusal'])
        # Never reconstruct these items: keep ids, status, encrypted_content,
        # reasoning summaries, phase and every unknown field exactly as received.
        return output, calls, ''.join(text)


def create(provider: str, model: str | None, system_text: str,
           session_id: str, **kwargs: Any) -> NativeSession:
    if not isinstance(provider, str):
        raise ValueError('Unsupported provider')
    provider = _ALIASES.get(provider.lower(), provider.lower())
    implementations = {'anthropic': AnthropicSession,
                       'openrouter': OpenRouterSession, 'codex': CodexSession}
    if provider not in implementations:
        raise ValueError('Unsupported provider')
    return implementations[provider](model, system_text, session_id, **kwargs)


def from_state(state: dict | str, **kwargs: Any) -> NativeSession:
    return NativeSession.from_state(state, **kwargs)
