#!/usr/bin/env python3
"""Offline, rerunnable cost audit. Writes only the three named public artifacts and this report.

Usage: python analysis/cost_audit.py [--root /workspace/memory_sql_study]
No model calls, shell-command execution, grading, credential reads or network access.
Private snapshots are compared in memory; no private history, reasoning or signatures
are exported. Command text comes ONLY from tool_results.command, not native history.
"""
from __future__ import annotations
import argparse
import collections
import copy
import csv
import datetime as dt
import fcntl
import hashlib
import types
import io
import json
import os
from pathlib import Path
import re
import socket
import sys
import time

sys.dont_write_bytecode = True
PROVIDERS = ('anthropic', 'openrouter', 'codex')
TASKS = ('W1', 'W2', 'T1', 'T2', 'T3')
TOKEN_KEYS = ('input_total', 'input_cache_read', 'input_cache_write',
              'input_uncached_excluding_writes', 'input_not_cache_read',
              'input_cache_write_5m', 'input_cache_write_1h', 'output', 'reasoning')
RATES = {'input': .10, 'output': .50, 'cache_read': .01,
         'cache_write_5m': .125, 'cache_write_1h': .20}
CATEGORIES = ('schema_exploration', 'task_analytical', 'memory_file_io', 'error_recovery', 'other')


def block_network(*args, **kwargs):
    raise RuntimeError('cost_audit is strictly offline')


class OfflineHTTP:
    def post(self, *args, **kwargs):
        return block_network()
    def close(self):
        pass


def phase(task):
    return 'prep_W1W2' if task in ('W1', 'W2') else 'target_T1T2T3' if task in ('T1', 'T2', 'T3') else 'other'


def cohort(job):
    if job.startswith('diag-'):
        return 'diagnostic'
    if job == 'main-haiku-stateless-cont':
        return 'continuation'
    if job.startswith(('pilot2-luna', 'main-haiku', 'main-glm')):
        return 'primary'
    return 'excluded'


def norm(u, provider):
    """Native usage only, never trust normalized reasoning=0 for Anthropic."""
    u = u or {}
    if provider == 'anthropic':
        uncached = u.get('input_tokens', 0) or 0
        read = u.get('cache_read_input_tokens', 0) or 0
        ttl = u.get('cache_creation') or {}
        w1 = ttl.get('ephemeral_1h_input_tokens', 0) or 0
        write = u.get('cache_creation_input_tokens', sum(ttl.values())) or 0
        w5 = ttl.get('ephemeral_5m_input_tokens', write - w1) or 0
        total = uncached + read + write
        output = u.get('output_tokens', 0) or 0
        detail = u.get('output_tokens_details') or {}
        reasoning = detail.get('thinking_tokens', detail.get('reasoning_tokens', 0)) or 0
        present = 'thinking_tokens' in detail or 'reasoning_tokens' in detail
    else:
        chat = provider == 'openrouter'
        total = u.get('prompt_tokens' if chat else 'input_tokens', 0) or 0
        output = u.get('completion_tokens' if chat else 'output_tokens', 0) or 0
        detail = u.get('prompt_tokens_details' if chat else 'input_tokens_details') or {}
        read, write = detail.get('cached_tokens', 0) or 0, detail.get('cache_write_tokens', 0) or 0
        uncached = total - read - write
        w5 = w1 = 0
        out_detail = u.get('completion_tokens_details' if chat else 'output_tokens_details') or {}
        reasoning = out_detail.get('reasoning_tokens', 0) or 0
        present = 'reasoning_tokens' in out_detail
    assert total == uncached + read + write and uncached >= 0
    return dict(zip(TOKEN_KEYS, (total, read, write, uncached, total-read, w5, w1, output, reasoning))), present


def tokens(usages, provider):
    total = dict.fromkeys(TOKEN_KEYS, 0)
    hits = zero = partial = missing = 0
    for u in usages:
        n, has_reasoning = norm(u, provider)
        for k in TOKEN_KEYS:
            total[k] += n[k]
        hits += n['input_cache_read'] > 0
        zero += n['input_cache_read'] == 0
        partial += 0 < n['input_cache_read'] < n['input_total']
        missing += not has_reasoning
    total.update(responses=len(usages), reasoning_detail_missing_responses=missing,
                 cache_read_fraction=total['input_cache_read']/total['input_total'] if total['input_total'] else None,
                 responses_with_cache_read=hits, responses_without_cache_read=zero,
                 responses_with_partial_cache_read=partial,
                 response_cache_hit_fraction=hits/len(usages) if usages else None)
    return total


def money(rows, provider):
    priced = [r['cost_usd'] for r in rows if isinstance(r.get('cost_usd'), (int, float))]
    unknown = len(rows)-len(priced)
    known = sum(priced) if priced or provider != 'codex' else None
    return {'entries': len(rows), 'priced_entries': len(priced), 'unknown_cost_entries': unknown,
            'known_usd_subtotal': known,
            'total_usd': known if not unknown and provider != 'codex' else None,
            'currency': 'USD', 'valuation': 'unknown_subscription_marginal_cost' if provider == 'codex' else 'ledger_recorded'}


def anth_price(u):
    n, _ = norm(u, 'anthropic')
    tier = 5 if n['input_total'] > 100000 else 1
    parts = {'input_uncached_usd': n['input_uncached_excluding_writes']*.10,
             'output_usd': n['output']*.50,
             'cache_read_usd': n['input_cache_read']*.01,
             'cache_write_5m_usd': n['input_cache_write_5m']*.125,
             'cache_write_1h_usd': n['input_cache_write_1h']*.20}
    return {k: v*tier/1e6 for k, v in parts.items()}


def metrics(rows, provider):
    return {'money': money(rows, provider), 'tokens': tokens([r.get('usage', {}) for r in rows], provider)}


def safe_command(text):
    """Defense in depth: never publish literal credentials or opaque native fields."""
    text = re.sub(r'(?i)((?:api[_-]?key|access_token|refresh_token|authorization|encrypted_content|signature)\s*[=:]\s*)[^\s;]+', r'\1[REDACTED]', text)
    text = re.sub(r'\b(?:sk-ant-|sk-or-|sk-proj-|ghp_|github_pat_)[A-Za-z0-9_-]+', '[REDACTED]', text)
    text = re.sub(r'\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[REDACTED_JWT]', text)
    return text


def sanitize(value):
    # Same comparison representation as run_study.sanitize; never exported itself.
    if isinstance(value, dict):
        return {k: ({'omitted': True, 'sha256': hashlib.sha256(str(v).encode()).hexdigest(), 'length': len(str(v))}
                    if k in ('encrypted_content', 'signature', 'encrypted_function_args') else sanitize(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(x) for x in value]
    return value


def history_size(h):
    return {'items': len(h), 'json_chars_runner_format': len(json.dumps(h)),
            'json_utf8_bytes_compact': len(json.dumps(h, ensure_ascii=False, separators=(',', ':')).encode())}


def native_counts(h):
    c = collections.Counter()
    for x in h:
        if x.get('type') == 'reasoning':
            c['codex_reasoning_items'] += 1
            if x.get('encrypted_content'):
                c['codex_reasoning_items_with_encrypted_content'] += 1
        content = x.get('content')
        for b in content if isinstance(content, list) else []:
            if b.get('type') in ('thinking', 'redacted_thinking'):
                c['anthropic_'+b['type']+'_blocks'] += 1
                if b.get('signature'):
                    c['anthropic_thinking_blocks_with_signature'] += 1
        if x.get('role') == 'assistant':
            if x.get('reasoning'):
                c['openrouter_messages_with_reasoning'] += 1
            if x.get('reasoning_details'):
                c['openrouter_messages_with_reasoning_details'] += 1
                for b in x['reasoning_details']:
                    c['openrouter_detail_type:'+str(b.get('type', 'unspecified'))] += 1
    return dict(c)


class Snapshot:
    def __init__(self, root):
        self.root = root
        self.data = {}
        self.inventory = []
        self.warnings = []
        self.start = time.time()
        paths = [root/x for x in ('providers.py', 'run_study.py', 'sandbox.py', 'provider_config.json', 'analyze.py', 'analysis/amendments.md', 'analysis/protocol.md')]
        paths += sorted(root.glob('access*.json')) + [root/'native_smoke.json']
        paths += sorted((root/'runs').glob('*/manifest.json'))
        for pattern in ('*/*/trace.json', '*/*/pre_state.private.json', '*/*/post_state.private.json', '*/*/error_state.private.json'):
            paths += sorted((root/'runs').glob(pattern))
        for p in paths:
            if p.exists():
                self.capture(p)
        # Lock only the short ledger read. Never hold it while analyzing live jobs.
        p = root/'ledger.jsonl'
        if p.exists():
            with p.open('rb') as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                raw = f.read()
                fcntl.flock(f, fcntl.LOCK_UN)
            self.save(p, raw)
        self.end = time.time()
        self.changed_during_capture = self.changed()

    def capture(self, p):
        try:
            self.save(p, p.read_bytes())
        except OSError:
            self.warnings.append({'path': str(p.relative_to(self.root)), 'kind': 'read_failed'})

    def save(self, p, raw):
        rel = str(p.relative_to(self.root))
        self.data[rel] = raw
        self.inventory.append({'path': rel, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})

    def get(self, rel, default=None):
        raw = self.data.get(str(rel))
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError):
            self.warnings.append({'path': str(rel), 'kind': 'json_parse_failed_not_used'})
            return default

    def changed(self):
        changed = []
        for row in self.inventory:
            try:
                if hashlib.sha256((self.root/row['path']).read_bytes()).hexdigest() != row['sha256']:
                    changed.append(row['path'])
            except OSError:
                changed.append(row['path'])
        return changed


def command_categories(command, result, previous_error, known_python_sql):
    low = command.lower()
    reasons = collections.defaultdict(list)
    memory = bool(re.search(r'(?:\.\./|/|\b)memory(?:/|\b)', low))
    # These describe attempts, not proof of execution (&&, redirects, quoting, heredocs).
    py = bool(re.search(r'\bpython(?:3(?:\.\d+)?)?\s', low))
    py_sql = py and (bool(re.search(r'(?:import\s+sqlite3|from\s+sqlite3|sqlite3\.connect)', low)) or any(p in low for p in known_python_sql))
    if re.search(r'import\s+sqlite3|from\s+sqlite3', low):
        for p in re.findall(r'[^\s\'"<>;]+\.py\b', low):
            known_python_sql.add(p)
    mem_modes = []
    if memory:
        reasons['memory_file_io'].append('memory_path_reference_attempt')
        if re.search(r'(?:cat|head|tail|sed|grep|less)\s+[^;\n]*memory(?:/|\b)|open\([^\n]*memory[^\n]*[\'\"]r', low):
            mem_modes.append('read_candidate')
        if re.search(r'(?:>>?|tee\s+)[^;\n]*memory(?:/|\b)|(?:write_text|write_bytes)|open\([^\n]*memory[^\n]*[\'\"][wa]', low):
            mem_modes.append('write_candidate')
        if re.search(r'\b(?:ls|find|mkdir|stat|test)\b[^;\n]*memory(?:/|\b)', low):
            mem_modes.append('directory_discovery_or_setup')
        if not mem_modes:
            mem_modes.append('path_reference_unresolved')
    if re.search(r'\.schema\b|\.tables\b|\bpragma\b|sqlite_(?:master|schema)|readme(?:\.md)?', low):
        reasons['schema_exploration'].append('schema_catalog_or_readme')
    if re.search(r'\b(?:pwd|ls|find)\b', low) and not memory:
        reasons['schema_exploration'].append('filesystem_orientation')
    # Simple dimension/registry browsing; intentionally broader than DDL inspection.
    lookups = r'feed_registry|subsystems|services|service_routes|worker_pools|failure_codes|regions|releases|operation_classes|policy_profiles|change_kinds|telemetry_signals|incident_windows|execution_cells|route_assignments|tenant_tiers'
    if re.search(r'\bfrom\s+(?:'+lookups+r')\b', low) or (py_sql and re.search(r"['\"](?:"+lookups+r")[ '\"]", low)):
        reasons['schema_exploration'].append('dimension_registry_data_browsing')
    sql_hint = bool(result.get('sql_cli_calls')) or bool(re.search(r'\bsqlite3\s', low)) or py_sql
    analytical = bool(re.search(r'\b(?:count|sum|avg|min|max|round|row_number)\s*\(|\bgroup\s+by\b|\bjoin\b|\bwith\s+\w+\s+as\b|\b(?:datetime|strftime)\s*\(', low))
    if sql_hint and analytical:
        reasons['task_analytical'].append('SQL_aggregation_join_or_task_computation')
    if re.search(r'\b(?:logical_operations|attempt_events|outcome_events|telemetry_samples|change_events)\b', low) and sql_hint:
        reasons['task_analytical'].append('fact_table_or_incident_analysis')
    if py and not py_sql:
        reasons['task_analytical'].append('python_task_support_or_answer_serialization_candidate')
    if re.search(r'(?:\.sql\b|answer\.json|/tmp/out\.json|/tmp/ev\.txt)', low) and not (memory and not sql_hint and not py):
        reasons['task_analytical'].append('task_scratch_SQL_or_answer_artifact')
    if previous_error:
        reasons['error_recovery'].append('immediately_after_observed_command_error')
    # A failed command is not itself automatically a recovery command.
    output = result.get('output', '')
    error_text = bool(re.search(r'(?:Parse error|Runtime error|Traceback \(most recent call last\)|no such (?:table|column|file)|ambiguous column|syntax error|OperationalError|cannot open|Permission denied)', output, re.I))
    observed_error = bool(result.get('exit_code') not in (0, None) or result.get('timeout') or any(x.get('exit_code') not in (0, None) for x in result.get('sql_cli_calls', [])) or error_text)
    labels = [k for k in CATEGORIES if k in reasons]
    if not labels:
        labels = ['other']
        reasons['other'].append('no_matching_rule')
    return {'categories': labels, 'classification_evidence': dict(reasons),
            'mixed_command': len(labels) > 1, 'memory_io_modes': mem_modes,
            'python_command_candidate': py, 'python_sqlite_candidate': py_sql,
            'observed_error': observed_error, 'error_text_detected': error_text,
            'recovery_after_previous_error': previous_error}


def checkpoint_audit(pre, post, error, trace, provider_module):
    result = {'checkpoints': {}, 'pre_prefix_of_post': None,
              'successful_trace_native_history_reconstruction_matches_post': None,
              'turn_state_chars_match_reconstruction': None}
    for name, state in (('pre', pre), ('post', post), ('error', error)):
        if not state:
            continue
        h = state.get('native_history', [])
        record = {'history': history_size(h), 'native_reasoning_observed': native_counts(h)}
        try:
            session = provider_module.from_state(state, http_client=OfflineHTTP())
            restored = session.export_state()
            record['roundtrip_state_exact'] = restored == state
            payload = session._payload()  # Pure construction. Never _headers, _request or step.
            wire = payload['input' if state['provider'] == 'codex' else 'messages']
            expected = copy.deepcopy(h)
            if state['provider'] == 'anthropic' and state['config'].get('cache_control'):
                for msg in reversed(expected):
                    if msg.get('role') == 'user' and msg.get('content'):
                        msg['content'][-1]['cache_control'] = copy.deepcopy(state['config']['cache_control'])
                        break
            if state['provider'] == 'openrouter':
                for msg in expected:
                    if msg.get('role') == 'assistant':
                        for call in msg.get('tool_calls') or []:
                            call.pop('index', None)
            record['payload_history_matches_documented_projection'] = wire == expected
            record['payload_history_size'] = history_size(wire)
            record['payload_reasoning_counts_equal_history'] = native_counts(wire) == native_counts(h)
            # Full equality above checks opaque fields too; nothing is printed.
            response = state.get('last_response')
            if response and name != 'pre' and not state.get('failure'):
                native, _, _ = session._extract(response)
                record['last_successful_native_response_exact_history_suffix'] = h[-len(native):] == native if native else True
            if state.get('failure'):
                record['failure'] = {k: state['failure'].get(k) for k in ('kind', 'charge_unknown', 'elapsed_s', 'status_code')}
            session.close()
        except Exception as exc:
            record['audit_exception_type'] = type(exc).__name__  # Never include private exception text.
        result['checkpoints'][name] = record
    if pre and post:
        h = pre['native_history']
        result['pre_prefix_of_post'] = post['native_history'][:len(h)] == h
    if pre and trace:
        try:
            session = provider_module.from_state(pre, http_client=OfflineHTTP())
            session.add_user(trace['prompt'])
            wire = session._payload()
            first_h = wire['input' if pre['provider'] == 'codex' else 'messages']
            result['first_request_history_after_task_prompt'] = history_size(first_h)
            result['first_request_payload_json_chars'] = len(json.dumps(wire))
            result['first_request_payload_json_utf8_bytes_compact'] = len(json.dumps(wire, ensure_ascii=False, separators=(',', ':')).encode())
            result['pre_history_preserved_in_first_request_before_cache_projection'] = session._history[:len(pre['native_history'])] == pre['native_history']
            checks = []
            for turn in trace.get('turns', []):
                native, calls, _ = session._extract(turn['native_response'])
                session._history.extend(native)
                session._pending = calls
                # Compare sanitized native prefixes, measure ONLY original private history.
                if post:
                    original_prefix = post['native_history'][:len(session._history)]
                    reconstructed_prefix = sanitize(pre['native_history']) + session._history[len(pre['native_history']):]
                    checks.append(len(json.dumps(original_prefix)) == turn.get('state_chars')
                                  if reconstructed_prefix == sanitize(original_prefix) else None)
                else:
                    checks.append(None)
                if turn.get('tool_results'):
                    res = [{'id': c['id'], 'output': r['output']+f'\n[exit_code={r["exit_code"]}]'}
                           for c, r in zip(calls, turn['tool_results'])]
                    session.add_tool_results(res)
            # Pre is raw; trace native responses already use the runner's sanitized form.
            reconstructed = sanitize(pre['native_history']) + session._history[len(pre['native_history']):]
            if post:
                result['successful_trace_native_history_reconstruction_matches_post'] = reconstructed == sanitize(post['native_history'])
            result['turn_state_chars_comparable_checks'] = sum(x is not None for x in checks)
            result['turn_state_chars_match_reconstruction'] = all(x for x in checks if x is not None) if any(x is not None for x in checks) else None
            session.close()
        except Exception as exc:
            result['reconstruction_exception_type'] = type(exc).__name__
    return result


def sum_timing(tasks):
    fields = ('model_wall_success_s', 'model_wall_failed_observed_s', 'shell_wall_s',
              'sql_cli_wall_s', 'sql_cli_invocations', 'sql_cli_over_1s', 'shell_over_1s',
              'shell_commands', 'python_command_candidates', 'python_sqlite_candidates',
              'command_errors', 'truncated_outputs', 'shell_timeouts', 'successful_model_turns')
    return {k: sum(t['timing'].get(k, 0) for t in tasks) for k in fields}


def aggregate(task_rows, ledger_rows, provider):
    turns = [t for row in task_rows for t in row['_turns']]
    failed = [r for r in ledger_rows if 'error' in r]
    success = [r for r in ledger_rows if 'error' not in r]
    states = [t['state_chars'] for t in turns if isinstance(t.get('state_chars'), int)]
    return {'tasks_observed': sum(bool(r['_trace']) for r in task_rows),
            'task_statuses': dict(collections.Counter(r['status'] for r in task_rows)),
            'ledger_all': metrics(ledger_rows, provider),
            'ledger_successful_responses': metrics(success, provider),
            'ledger_failed_responses': metrics(failed, provider),
            'successful_recorded_turns': metrics(turns, provider),
            'timing': sum_timing(task_rows),
            'state_history_after_response_chars': {'sum_repeated_history_snapshots': sum(states), 'max': max(states, default=None), 'observations': len(states)},
            'action_category_counts_nonexclusive': {c: sum(r['action_category_counts_nonexclusive'][c] for r in task_rows) for c in CATEGORIES}}


def access_audit(snap):
    entries, unavailable = [], []
    for name in sorted(k for k in snap.data if k.startswith('access') and k.endswith('.json')) + ['native_smoke.json']:
        obj = snap.get(name, {})
        for p in PROVIDERS:
            block = obj.get(p)
            if not isinstance(block, dict):
                continue
            samples = block.get('turns', []) if name == 'native_smoke.json' else [block]
            found = False
            for i, sample in enumerate(samples):
                usage = sample.get('usage')
                if not isinstance(usage, dict) or not usage:
                    continue
                found = True
                if p == 'anthropic':
                    cost = sum(anth_price(usage).values())
                    source = 'estimate_configured_Haiku_rates_not_ledger'
                elif p == 'openrouter':
                    cost = usage.get('cost')
                    source = 'usage.cost' if cost is not None else 'unknown'
                else:
                    cost, source = None, 'unknown_subscription_marginal_cost'
                n, present = norm(usage, p)
                entries.append({'file': name, 'provider': p, 'turn_1based': i+1 if name == 'native_smoke.json' else None,
                                'tokens': n, 'reasoning_detail_present': present,
                                'cost_usd': cost, 'cost_source': source,
                                '_usage': usage})
            if not found:
                unavailable.append({'file': name, 'provider': p,
                                    'status': block.get('status'), 'charge_usd': None,
                                    'note': 'No per-call usage in this artifact; catalog/summary/error is not a zero-cost inference observation.'})
    by_provider = {}
    for p in PROVIDERS:
        e = [r for r in entries if r['provider'] == p]
        by_provider[p] = {'money': money(e, p), 'tokens': tokens([r['_usage'] for r in e], p)}
        by_provider[p]['money']['valuation'] = 'available_probe_usage_only; Anthropic estimated, OR authoritative, Codex unknown'
    for r in entries:
        del r['_usage']
    return {'entries': entries, 'by_provider': by_provider, 'no_per_call_usage_records': unavailable,
            'coverage': 'Only available access*.json and native_smoke.json usage. Not a complete preflight bill; no invented charge for absent usage. Not added to study ledger.'}


def build(root):
    # This process cannot create a network socket, including accidental library calls.
    class OfflineSocket(socket.socket):
        def __new__(cls, *args, **kwargs):
            return block_network()
    socket.socket = OfflineSocket
    socket.create_connection = block_network
    snap = Snapshot(root)
    module = types.ModuleType('_cost_audit_providers')
    module.__file__ = str(root/'providers.py')
    exec(compile(snap.data['providers.py'], module.__file__, 'exec'), module.__dict__)
    ledger = []
    for line_number, line in enumerate(snap.data.get('ledger.jsonl', b'').splitlines(), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            r['_line'] = line_number
            ledger.append(r)
        except ValueError:
            snap.warnings.append({'path': 'ledger.jsonl', 'line': line_number, 'kind': 'invalid_line_not_used'})
    manifests = {Path(k).parent.name: snap.get(k) for k in snap.data if re.fullmatch(r'runs/[^/]+/manifest.json', k)}
    manifests = {k: v for k, v in manifests.items() if v}
    selected = {j: m for j, m in manifests.items() if cohort(j) != 'excluded' and m.get('valid_for_comparison', True)}
    ledger_index = collections.defaultdict(list)
    for r in ledger:
        ledger_index[(r.get('job'), r.get('task'))].append(r)
    tasks, commands, longs, long_shell = [], [], [], []
    checkpoints = {}
    corrections = []
    for job, m in sorted(selected.items()):
        provider = m['provider']
        observed_tasks = {Path(k).parent.name for k in snap.data if k.startswith('runs/'+job+'/') and k.endswith('/trace.json')}
        tids = sorted(set(m.get('tasks', [])) | observed_tasks | {t for j, t in ledger_index if j == job}, key=lambda t: TASKS.index(t) if t in TASKS else 99)
        previous_post = None
        for tid in tids:
            prefix = f'runs/{job}/{tid}'
            trace = snap.get(prefix+'/trace.json', {})
            pre = snap.get(prefix+'/pre_state.private.json')
            post = snap.get(prefix+'/post_state.private.json')
            error = snap.get(prefix+'/error_state.private.json')
            checkpoints[(job, tid)] = (pre, post)
            turns = trace.get('turns', [])
            rows = ledger_index.get((job, tid), [])
            a = checkpoint_audit(pre, post, error, trace, module)
            if pre and previous_post:
                a['previous_task_post_equals_this_pre_history'] = previous_post['native_history'] == pre['native_history']
                a['cross_task_policy'] = 'expect_equal_icl' if m['arm'] == 'icl' else 'expect_reset'
            if pre:
                a['pre_history_native_reasoning_counts'] = native_counts(pre['native_history'])
                a['pre_history_contains_assistant_or_reasoning'] = any(x.get('role') == 'assistant' or x.get('type') in ('reasoning', 'function_call') for x in pre['native_history'])
            previous_post = post
            local_commands = []
            previous_error = False
            py_scripts = set()
            for turn_i, turn in enumerate(turns, 1):
                n, present = norm(turn.get('usage', {}), provider)
                old = turn.get('token_accounting', {}).get('reasoning_tokens')
                if provider == 'anthropic' and present and old != n['reasoning']:
                    corrections.append({'job': job, 'task': tid, 'turn_1based': turn_i,
                                        'old_normalized_reasoning': old, 'native_thinking_tokens': n['reasoning']})
                for command_i, r in enumerate(turn.get('tool_results', []), 1):
                    cls = command_categories(r.get('command', ''), r, previous_error, py_scripts)
                    previous_error = cls['observed_error']
                    cmd = {'command_id': f'{job}/{tid}/turn-{turn_i}/command-{command_i}',
                           'job': job, 'provider': provider, 'arm': m['arm'], 'cohort': cohort(job),
                           'task': tid, 'phase': phase(tid), 'turn_1based': turn_i, 'command_1based': command_i,
                           'source_trace': prefix+'/trace.json',
                           'command': safe_command(r.get('command', '')),
                           'command_sha256': hashlib.sha256(r.get('command', '').encode()).hexdigest(),
                           **cls, 'shell_wall_s': r.get('wall_seconds', 0), 'exit_code': r.get('exit_code'),
                           'timeout': r.get('timeout', False), 'truncated': r.get('truncated', False),
                           'sql_cli_invocations': len(r.get('sql_cli_calls', [])),
                           'sql_cli_wall_s': sum(s.get('wall_seconds', 0) for s in r.get('sql_cli_calls', [])),
                           'sql_cli_over_1s': sum(s.get('wall_seconds', 0) > 1 for s in r.get('sql_cli_calls', [])),
                           'sql_cli_timings': r.get('sql_cli_calls', [])}
                    local_commands.append(cmd)
                    commands.append(cmd)
                    for ordinal, s in enumerate(r.get('sql_cli_calls', []), 1):
                        if s.get('wall_seconds', 0) > 1:
                            longs.append({'command_id': cmd['command_id'], 'job': job, 'task': tid,
                                          'cohort': cohort(job), 'turn_1based': turn_i, 'command_1based': command_i,
                                          'sql_cli_timing_ordinal_1based': ordinal,
                                          'sql_cli_wall_s': s['wall_seconds'], 'sql_exit_code': s.get('exit_code'),
                                          'shell_wall_s': cmd['shell_wall_s'], 'shell_exit_code': cmd['exit_code'],
                                          'parent_command': cmd['command'],
                                          'attribution': 'Timer ordinal within parent shell command; wrapper did not log argv/individual SQL statements.'})
                    if cmd['shell_wall_s'] > 1:
                        long_shell.append({'command_id': cmd['command_id'], 'shell_wall_s': cmd['shell_wall_s'],
                                           'sql_cli_invocations': cmd['sql_cli_invocations'],
                                           'python_sqlite_candidate': cmd['python_sqlite_candidate'],
                                           'parent_command': cmd['command']})
            failure_elapsed = ((error or post or {}).get('failure') or {}).get('elapsed_s') or 0
            timing = {'model_wall_success_s': sum(t.get('elapsed_s', 0) for t in turns),
                      'model_wall_failed_observed_s': failure_elapsed,
                      'shell_wall_s': sum(c['shell_wall_s'] for c in local_commands),
                      'sql_cli_wall_s': sum(c['sql_cli_wall_s'] for c in local_commands),
                      'sql_cli_invocations': sum(c['sql_cli_invocations'] for c in local_commands),
                      'sql_cli_over_1s': sum(c['sql_cli_over_1s'] for c in local_commands),
                      'shell_over_1s': sum(c['shell_wall_s'] > 1 for c in local_commands),
                      'shell_commands': len(local_commands), 'successful_model_turns': len(turns),
                      'python_command_candidates': sum(c['python_command_candidate'] for c in local_commands),
                      'python_sqlite_candidates': sum(c['python_sqlite_candidate'] for c in local_commands),
                      'command_errors': sum(c['observed_error'] for c in local_commands),
                      'truncated_outputs': sum(c['truncated'] for c in local_commands),
                      'shell_timeouts': sum(c['timeout'] for c in local_commands),
                      'task_elapsed_s_observed': trace.get('elapsed_s')}
            trace_keys = {(job, tid, i) for i in range(len(turns))}
            matches, mismatch, untraced = [], [], []
            for lr in rows:
                if 'error' in lr:
                    continue
                if (job, tid, lr.get('turn')) in trace_keys:
                    turn = turns[lr['turn']]
                    equal = turn.get('usage') == lr.get('usage') and turn.get('cost_usd') == lr.get('cost_usd')
                    (matches if equal else mismatch).append(lr['_line'])
                else:
                    untraced.append(lr['_line'])
            ledger_turns = {r.get('turn') for r in rows if 'error' not in r}
            first_rows = [r for r in rows if r.get('turn') == 0]
            first = None
            if tid.startswith('T') and (first_rows or turns or pre):
                first_usage = first_rows[0].get('usage', {}) if first_rows else (turns[0].get('usage', {}) if turns else None)
                first = {'usage_source': 'ledger_turn_0' if first_rows else 'trace_first_turn' if turns else 'not_yet_observed',
                         'tokens': tokens([first_usage], provider) if first_usage else None,
                         'cost_usd': first_rows[0].get('cost_usd') if first_rows else turns[0].get('cost_usd') if turns else None,
                         'pre_task_history': history_size(pre['native_history']) if pre else None,
                         'first_request_history_after_task_prompt': a.get('first_request_history_after_task_prompt'),
                         'first_request_payload_json_chars': a.get('first_request_payload_json_chars'),
                         'first_response_history_chars_runner': turns[0].get('state_chars') if turns else None,
                         'memory_before_chars': sum(len(v) for v in trace.get('memory_before', {}).values()),
                         'interpretation': 'Observed full input/context, not causal memory overhead; characters are not tokens.'}
            row = {'job': job, 'provider': provider, 'arm': m['arm'], 'cohort': cohort(job),
                   'task': tid, 'phase': phase(tid),
                   'status': trace.get('status', 'started_no_trace_yet' if pre else 'not_observed'),
                   'job_finished_at': m.get('finished_at'), 'source_trace': prefix+'/trace.json' if trace else None,
                   'checkpoint_audit': a, 'first_target_turn': first,
                   'provider_failure': ({'kind': (error.get('failure') or {}).get('kind'),
                       'charge_unknown_flag': (error.get('failure') or {}).get('charge_unknown'),
                       'failed_response_ledger_entries': sum('error' in x for x in rows),
                       'cost_status': 'recorded_in_ledger' if any('error' in x for x in rows) else 'unknown_no_failed_response_ledger_entry'} if error else None),
                   'timing': timing, 'action_category_counts_nonexclusive': {c: sum(c in x['categories'] for x in local_commands) for c in CATEGORIES},
                   'memory_before_chars': sum(len(v) for v in trace.get('memory_before', {}).values()),
                   'memory_after_chars': sum(len(v) for v in trace.get('memory_after', {}).values()) if 'memory_after' in trace else None,
                   'ledger_reconciliation': {'matched_successful_ledger_lines': matches,
                                             'mismatched_successful_ledger_lines': mismatch,
                                             'successful_ledger_lines_without_recorded_turn': untraced,
                                             'recorded_turns_without_ledger': [i+1 for i in range(len(turns)) if i not in ledger_turns]},
                   '_turns': turns, '_trace': trace}
            row['cost_and_tokens'] = aggregate([row], rows, provider)
            tasks.append(row)
    # Exact-source matches for diagnostic replay seeds (no assumed lineage).
    for row in tasks:
        if row['cohort'] != 'diagnostic':
            continue
        pre = checkpoints[(row['job'], row['task'])][0]
        if pre and row['arm'] == 'icl':
            row['checkpoint_audit']['exact_pre_history_matches_other_job_pre'] = [f'{j}/{t}' for (j, t), (p, _) in checkpoints.items() if j != row['job'] and cohort(j) == 'primary' and p and p['native_history'] == pre['native_history']]
    jobs = []
    for job, m in sorted(selected.items()):
        ts = [r for r in tasks if r['job'] == job]
        lr = [r for r in ledger if r.get('job') == job]
        jobs.append({'job': job, 'provider': m['provider'], 'arm': m['arm'], 'cohort': cohort(job),
                     'memory_instruction_variant': m.get('memory_instruction_variant', 'minimal'),
                     'job_finished': m.get('finished_at') is not None,
                     'all_planned_tasks_completed': all(r['status'] == 'completed' for r in ts),
                     'status_by_task': {r['task']: r['status'] for r in ts},
                     'all': aggregate(ts, lr, m['provider']),
                     'phases': {ph: aggregate([r for r in ts if r['phase'] == ph], [r for r in lr if phase(r.get('task')) == ph], m['provider']) for ph in ('prep_W1W2', 'target_T1T2T3')}})
    provider_totals = {}
    price_checks = []
    for p in PROVIDERS:
        rows = [r for r in ledger if r['provider'] == p]
        selected_rows = [r for r in rows if r.get('job') in selected]
        provider_totals[p] = {'entire_ledger': metrics(rows, p),
                              'entire_ledger_successful_responses': metrics([r for r in rows if 'error' not in r], p),
                              'entire_ledger_failed_responses': metrics([r for r in rows if 'error' in r], p),
                              'selected_runs': aggregate([r for r in tasks if r['provider'] == p], selected_rows, p),
                              'excluded_or_unselected_ledger': metrics([r for r in rows if r.get('job') not in selected], p),
                              'cohorts': {co: metrics([r for r in selected_rows if cohort(r['job']) == co], p) for co in ('primary', 'continuation', 'diagnostic')}}
        for r in rows:
            expected = sum(anth_price(r['usage']).values()) if p == 'anthropic' else r.get('usage', {}).get('cost') if p == 'openrouter' else None
            observed = r.get('cost_usd')
            price_checks.append({'provider': p, 'ledger_line': r['_line'], 'expected_usd': expected,
                                 'observed_ledger_usd': observed,
                                 'matches': abs(expected-observed) < 1e-12 if expected is not None and observed is not None else None})
        if p == 'anthropic':
            for label, subset in [('all', rows), ('success', [r for r in rows if 'error' not in r]), ('failed', [r for r in rows if 'error' in r])]:
                parts = collections.Counter()
                for r in subset:
                    parts.update(anth_price(r['usage']))
                provider_totals[p]['configured_price_components_'+label] = dict(parts)
            provider_totals[p]['long_context_tier_5x_entries'] = sum(norm(r['usage'], p)[0]['input_total'] > 100000 for r in rows)
    failed_entries = []
    for r in ledger:
        if 'error' not in r:
            continue
        err = snap.get(f'runs/{r["job"]}/{r["task"]}/error_state.private.json', {})
        response = err.get('last_response') or {}
        t = next((x for x in tasks if x['job'] == r['job'] and x['task'] == r['task']), None)
        previous_id = t['_turns'][-1].get('response_id') if t and t['_turns'] else None
        failed_entries.append({'provider': r['provider'], 'job': r.get('job'), 'task': r.get('task'),
                               'ledger_turn_0based': r.get('turn'), 'cost_usd': r.get('cost_usd'),
                               'tokens': tokens([r.get('usage', {})], r['provider']),
                               'failure_kind': (err.get('failure') or {}).get('kind'),
                               'native_stop_reason': response.get('stop_reason'),
                               'native_usage_equals_ledger': response.get('usage') == r.get('usage'),
                               'last_response_is_previous_success_candidate': bool(previous_id and response.get('id') == previous_id),
                               'note': 'Paid/recorded failed provider response; not a successful turn and not a shell error.'})
    # Diagnostic summaries count each task suffix only once; do not sum cumulative checkpoints.
    retention = {}
    for p in PROVIDERS:
        counts = collections.Counter()
        audited = []
        for r in tasks:
            if r['provider'] != p:
                continue
            pre, post = checkpoints[(r['job'], r['task'])]
            if post:
                h = post['native_history']
                if pre and h[:len(pre['native_history'])] == pre['native_history']:
                    h = h[len(pre['native_history']):]
                counts.update(native_counts(h))
            audited.append(r['checkpoint_audit'])
        retention[p] = {'new_native_reasoning_blocks_in_available_post_history': dict(counts),
                         'tasks_with_post_checkpoint': sum('post' in a['checkpoints'] for a in audited),
                         'prefix_checks': {'checked': sum(a['pre_prefix_of_post'] is not None for a in audited), 'failed': sum(a['pre_prefix_of_post'] is False for a in audited)},
                         'trace_reconstruction_checks': {'checked': sum(a['successful_trace_native_history_reconstruction_matches_post'] is not None for a in audited), 'failed': sum(a['successful_trace_native_history_reconstruction_matches_post'] is False for a in audited)},
                         'payload_projection_checks': {'checked': sum('payload_history_matches_documented_projection' in c for a in audited for c in a['checkpoints'].values()), 'failed': sum(c.get('payload_history_matches_documented_projection') is False for a in audited for c in a['checkpoints'].values())},
                         'state_roundtrip_checks': {'checked': sum('roundtrip_state_exact' in c for a in audited for c in a['checkpoints'].values()), 'failed': sum(c.get('roundtrip_state_exact') is False for a in audited for c in a['checkpoints'].values())},
                         'turn_state_chars_checks': {'checked': sum(a.get('turn_state_chars_comparable_checks', 0) for a in audited), 'tasks_failed': sum(a.get('turn_state_chars_match_reconstruction') is False for a in audited)},
                         'audit_exception_count': sum('reconstruction_exception_type' in a for a in audited) + sum('audit_exception_type' in c for a in audited for c in a['checkpoints'].values()),
                         'claim_limit': 'Observed client-side exact retention and locally prepared request replay, not server-side use of hidden reasoning, cache equivalence, or actual replay API request.'}
    scopes = []
    for job in jobs:
        for ph in ('all', 'prep_W1W2', 'target_T1T2T3'):
            cs = [c for c in commands if c['job'] == job['job'] and (ph == 'all' or c['phase'] == ph)]
            scopes.append({'job': job['job'], 'provider': job['provider'], 'cohort': job['cohort'], 'phase': ph,
                           'commands': len(cs), 'category_counts_nonexclusive': {k: sum(k in c['categories'] for c in cs) for k in CATEGORIES},
                           'mixed_commands': sum(c['mixed_command'] for c in cs),
                           'commands_with_observed_error': sum(c['observed_error'] for c in cs),
                           'memory_mode_counts_nonexclusive': dict(collections.Counter(mode for c in cs for mode in c['memory_io_modes']))})
    action = {'schema_version': 1, 'generated_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'method': 'Whole shell commands; deterministic regex heuristics; non-exclusive labels; no token/cost allocation by action.',
              'definitions': {'schema_exploration': 'README, DDL/schema/catalog, filesystem orientation and dimension/registry browsing.',
                              'task_analytical': 'SQL metrics/joins/fact data, task Python, scratch SQL and answer preparation.',
                              'memory_file_io': 'Memory path access attempt, with discovery/read/write candidate sublabels; not proof of successful content reuse.',
                              'error_recovery': 'Immediately next shell command after an observed exit/SQL/text error in the same task; not verified causal repair.',
                              'other': 'No matched rule.'},
              'caveats': ['Labels overlap, so sums exceed number of commands.', 'SQL strings in scripts/notes and short-circuit shell execution can cause false positives.',
                          'Error-text heuristic misses masked or unrecognized failures and may flag printed error text.',
                          'No shell AST, dynamic SQL tracing or per-SQL argv. Full parent command and evidence are provided for manual audit.',
                          'Python sqlite3 is uninstrumented; inferred candidates are not a SQL query count.',
                          'Memory IO includes failed/wrong-path attempts and directory checks; these are not read/write token costs.',
                          'Never treat mixed-command labels as exact token, USD or wall-time allocation.'],
              'by_job_phase': scopes, 'commands': commands}
    access = access_audit(snap)
    for r in tasks:
        del r['_turns'], r['_trace']
    reconciliation = {'matched_successful_entries': sum(len(r['ledger_reconciliation']['matched_successful_ledger_lines']) for r in tasks),
                      'mismatched_entries': sum(len(r['ledger_reconciliation']['mismatched_successful_ledger_lines']) for r in tasks),
                      'ledger_success_entries_without_trace_turn': sum(len(r['ledger_reconciliation']['successful_ledger_lines_without_recorded_turn']) for r in tasks),
                      'trace_turns_without_ledger': sum(len(r['ledger_reconciliation']['recorded_turns_without_ledger']) for r in tasks),
                      'duplicate_ledger_keys': []}
    keys = collections.Counter((r['provider'], r.get('job'), r.get('task'), r.get('turn')) for r in ledger)
    reconciliation['duplicate_ledger_keys'] = [{'key': list(k), 'count': n} for k, n in keys.items() if n > 1]
    summary = {'schema_version': 1, 'generated_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
               'snapshot': {'capture_started_unix': snap.start, 'capture_finished_unix': snap.end,
                            'not_transactional_across_files': True, 'changed_during_capture': snap.changed_during_capture,
                            'changed_since_capture': snap.changed(), 'warnings': snap.warnings,
                            'ledger_lines': len(ledger), 'source_inventory': snap.inventory},
               'scope': {'included_jobs': list(selected), 'selection': 'valid_for_comparison and pilot2-luna*, main-haiku*, main-glm*, diag-*',
                         'excluded_jobs': [j for j in manifests if j not in selected],
                         'diagnostics_not_pooled_into_primary': True, 'continuation_is_separate_job': True,
                         'live_jobs': [j['job'] for j in jobs if not j['job_finished']]},
               'accounting_rules': {'money': 'Ledger values authoritative for runs. OR usage.cost reconciliation; Anthropic configured runner rates (not an invoice). Codex null, never $0.',
                                    'anthropic_rates_usd_per_million': RATES,
                                    'anthropic_long_context': 'All cost components x5 when input_uncached + cache_read + cache_write >100000, matching run_study.cost.',
                                    'input_identity': 'input_total = input_uncached_excluding_writes + input_cache_read + input_cache_write',
                                    'reasoning': 'Subset of output; Anthropic output_tokens_details.thinking_tokens corrected locally. Not added to output or billed a second time.',
                                    'cache_rate': 'Token weighted cache_read/input_total; also actual per-response any-hit and zero-read counts. Zero reads do not by themselves identify cache expiry or a cold cache.',
                                    'state_history': 'Measured JSON characters/bytes, not token estimates. Sums repeat prefixes and do not measure unique retained content.',
                                    'first_target_turn': 'Full observed input and first locally constructed request history, not invented memory-only overhead.',
                                    'timing': 'Model successful and failed request wall separated. Shell includes SQL/Python/process overhead. SQL CLI timings are a nested subset; do not add shell+SQL.',
                                    'coverage': 'CLI timer count is process invocations, not SQL statements; Python SQLite and killed/missing wrappers have partial coverage.',
                                    'causality': 'No action-category token pricing, causal overhead allocation or guaranteed cold-cache comparison.'},
               'provider_ledger_subtotals': provider_totals, 'jobs': jobs, 'tasks': tasks,
               'ledger_trace_reconciliation': reconciliation,
               'price_reconciliation': {'checked': sum(r['matches'] is not None for r in price_checks),
                                        'mismatches': [r for r in price_checks if r['matches'] is False]},
               'anthropic_reasoning_bug': {'successful_turns_corrected': len(corrections),
                                           'reasoning_tokens_recovered': sum(r['native_thinking_tokens']-(r['old_normalized_reasoning'] or 0) for r in corrections),
                                           'turns': corrections, 'provider_and_analyze_files_unchanged': True},
               'failed_response_charges': failed_entries, 'native_history_retention': retention,
               'long_sql_cli_invocations_over_1s': longs, 'long_shell_commands_over_1s': long_shell,
               'access_probe_costs_separate': access,
               'continuation_note': 'main-haiku-stateless-cont covers unattempted T2/T3 at original settings. Original T1 failed output and diagnostic T1 are not silently replaced or counted as one primary trajectory.'}
    return summary, action


def usd(v):
    return 'неизв.' if v is None else f'{v:.6f}'


def pct(v):
    return '—' if v is None else f'{100*v:.1f}%'


def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |', '| '+' | '.join('---' for _ in headers)+' |'] +
                     ['| '+' | '.join(str(x).replace('|', '\\|').replace('\n', ' ') for x in row)+' |' for row in rows])


def report(s, a):
    out = ['# Аудит затрат SQL-memory study', '', f'Срез: **{s["generated_at_utc"]}**. Аудит полностью локальный: **API-вызовов нет**.',
           '', '## 1. Область и воспроизводимость',
           '`python analysis/cost_audit.py` заново создаёт `public_results/cost_summary.json`, '
           '`public_results/action_categories.json`, `public_results/action_categories.csv` и этот документ. '
           'Скрипт не запускает команды агентов, grading или runner; не читает credentials; сеть в процессе заблокирована. '
           'Исходные providers.py, run_study.py, analyze.py и файлы других аналитиков не изменяются.',
           '', f'Включено {len(s["jobs"])} jobs. `pilot-luna-*` v1 исключены из сравнений из-за описанной в amendments контаминации; их расходы остаются в полном subtotal ledger. '
           'Диагностики отобраны после наблюдений и показаны отдельно. `main-haiku-stateless-cont` — отдельное продолжение, а не замена неуспешного T1.',
           '', '**Живой срез:** файлы читаются последовательно, ledger — под краткой shared-lock. Межфайловой транзакции нет. '
           'Хеши/размеры источников и изменения в процессе чтения сохранены в JSON. Не завершённые задачи имеют только наблюдённый lower bound. '
           'Отсутствующая запись не означает нулевые затраты; ещё выполняющийся API-вызов в ledger не виден.',
           '', 'Не завершены на момент manifest: '+(', '.join('`'+j+'`' for j in s['scope']['live_jobs']) or 'нет')+'.',
           f'Изменились при захвате: {len(s["snapshot"]["changed_during_capture"])} файлов; после захвата до конца анализа: {len(s["snapshot"]["changed_since_capture"])}. '
           f'Предупреждений чтения: {len(s["snapshot"]["warnings"])}.',
           '', '## 2. Деньги: ledger, успешные ответы и оплаченные ошибки',
           'USD берутся из ledger, не пересуммируются только из успешных traces. «Успешный turn» означает принятый adapter ответ, '
           'а не правильное решение задачи: он может вызвать SQL-ошибку. Неполный модельный ответ отдельно может быть оплачен. '
           '**Codex: USD неизвестны, не $0.** `known_usd_subtotal` — лишь сумма известных цен; `total_usd=null` при неизвестной стоимости.', '']
    rows = []
    for p, d in s['provider_ledger_subtotals'].items():
        allm = d['entire_ledger']['money']
        rows.append([p, allm['entries'], usd(allm['total_usd']), usd(d['entire_ledger_successful_responses']['money']['total_usd']),
                     usd(d['entire_ledger_failed_responses']['money']['total_usd']),
                     usd(d['selected_runs']['ledger_all']['money']['total_usd']), allm['unknown_cost_entries']])
    out += [table(['Provider', 'Ledger entries, все', 'Все USD', 'Успешные USD', 'Failed USD', 'Выбранные jobs USD', 'USD неизвестно, entries'], rows), '',
            'OpenRouter `usage.cost` — авторитетный источник (включая возможный 0). Haiku — **оценка по настроенным тарифам**, не внешний invoice: '
            '$0.10 input, $0.50 output, $0.01 cache read, $0.125 cache write 5m, $0.20 cache write 1h за миллион; '
            'runner умножает все компоненты на 5 при полном input >100 000. Reasoning входит в output и не тарифицируется повторно.',
            f'Сверено {s["price_reconciliation"]["checked"]} цен; расхождений: {len(s["price_reconciliation"]["mismatches"])}. '
            f'Haiku вызовов с tier ×5: {s["provider_ledger_subtotals"]["anthropic"]["long_context_tier_5x_entries"]}.', '']
    parts = s['provider_ledger_subtotals']['anthropic'].get('configured_price_components_all', {})
    out += ['Компоненты всех записей Haiku в ledger: '+', '.join(f'`{k}` ${v:.6f}' for k, v in parts.items())+'.', '']
    for f in s['failed_response_charges']:
        n = f['tokens']
        out.append(f'- `{f["job"]}/{f["task"]}`, ledger turn {f["ledger_turn_0based"]} (0-based): **${usd(f["cost_usd"])}**, stop=`{f["native_stop_reason"]}`, '
                   f'input {n["input_total"]:,}, output {n["output"]:,}, thinking {n["reasoning"]:,}. '
                   f'Usage совпадает с error checkpoint: {f["native_usage_equals_ledger"]}; '
                   f'подозрение на повтор last_response предыдущего успешного turn: {f["last_response_is_previous_success_candidate"]}.')
    rec = s['ledger_trace_reconciliation']
    out += ['', f'Сверка выбранных jobs: {rec["matched_successful_entries"]} successful ledger entries совпали с usage/ценой trace; '
            f'расхождений {rec["mismatched_entries"]}; ledger entries ещё без trace turn {rec["ledger_success_entries_without_trace_turn"]}; '
            f'trace turns без ledger {rec["trace_turns_without_ledger"]}; повторных ключей ledger {len(rec["duplicate_ledger_keys"])}. '
            'Разрыв ledger→trace возможен во время shell-вызова: запись денег предшествует сохранению turn.',
            '', '### Затраты по job и фазе',
            'В таблице **все ledger responses, включая failed**. Cache — read / весь input; write отдельно от uncached. '
            'Детальные успешные turns, failed usage, timing и статусы каждого task доступны в JSON. W1/W2 включены в затраты подготовки, '
            'но это не стоимость исключительно «создания памяти»: warmup задачи решаются во всех режимах.', '']
    rows = []
    for j in s['jobs']:
        for ph, d in j['phases'].items():
            n = d['ledger_all']['tokens']
            rows.append([j['job'], 'W1/W2' if ph.startswith('prep') else 'T1/T2/T3', j['cohort'],
                         n['responses'], n['input_total'], n['input_cache_read'], n['input_cache_write'],
                         n['input_uncached_excluding_writes'], n['output'], n['reasoning'], pct(n['cache_read_fraction']),
                         usd(d['ledger_successful_responses']['money']['total_usd']), usd(d['ledger_failed_responses']['money']['total_usd']),
                         usd(d['ledger_all']['money']['total_usd'])])
    out += [table(['Job', 'Фаза', 'Группа', 'Calls', 'Input', 'Cache read', 'Cache write', 'Uncached без write', 'Output', 'Reasoning ⊂ output', 'Hit токены', 'Success USD', 'Failed USD', 'Все USD'], rows),
            '', '### Состояние покрытия задач',
            table(['Job', 'Manifest завершён', 'Task statuses'], [[j['job'], j['job_finished'], ', '.join(f'{k}:{v}' for k, v in j['status_by_task'].items())] for j in s['jobs']]),
            '', '## 3. Reasoning и фактический кэш',
            f'**Баг подтверждён:** `providers._tokens()` для Anthropic оставляет reasoning=0, а `analyze.py` суммирует это поле. '
            f'Аудит читает native `usage.output_tokens_details.thinking_tokens`: исправлено {s["anthropic_reasoning_bug"]["successful_turns_corrected"]} successful turns, '
            f'восстановлено **{s["anthropic_reasoning_bug"]["reasoning_tokens_recovered"]:,} thinking tokens**. Failed response usage учитывается отдельно. '
            'Output, input и деньги от этой коррекции не увеличиваются. Отсутствующее поле reasoning отмечается счётчиком missing, а не интерпретируется как доказанный ноль.', '']
    rows = []
    for j in s['jobs']:
        n = j['all']['ledger_all']['tokens']
        rows.append([j['job'], n['input_total'], n['input_cache_read'], pct(n['cache_read_fraction']),
                     n['responses_with_cache_read'], n['responses_without_cache_read'], n['responses_with_partial_cache_read']])
    out += [table(['Job', 'Input всего', 'Cache read', 'Read/input', 'Вызовы с hit', 'Без cache read', 'Частичный hit'], rows), '',
            'Наличие cache marker или большого общего префикса **не означает 100% hit**. Нулевая доля может быть cold/short prompt/expiry/provider policy; '
            'по логам нельзя однозначно выбрать причину. Partial hit означает наличие и cached, и non-read input, не обязательно ошибку кэша. '
            'Результаты отражают фактические запуски с возможным межзапусковым provider cache, не гарантированно cold-cache сравнение.',
            '', '## 4. Первый target turn и переносимый контекст',
            'Ниже каждый T1/T2/T3: input самого первого запроса из ledger, pre-task history, locally constructed request после task prompt '
            'и максимальный размер history после ответа. Формат chars совпадает с `len(json.dumps(native_history))` runner. '
            'History включает tool outputs, native reasoning/opaque data и прочие сообщения; payload также содержит инструменты/системные параметры. '
            'Это наблюдаемые размеры, **не токенизация chars/4 и не причинная доля расходов памяти**. '
            'Сумма state_chars в JSON многократно считает одинаковые префиксы и пригодна только как нагрузка повторной сериализации.', '']
    rows = []
    for r in s['tasks']:
        f = r['first_target_turn']
        if not f:
            continue
        n = f['tokens'] or {}
        pre = f.get('pre_task_history') or {}
        req = f.get('first_request_history_after_task_prompt') or {}
        rows.append([r['job'], r['task'], n.get('input_total', '—'), n.get('input_cache_read', '—'),
                     pct(n.get('cache_read_fraction')), pre.get('json_chars_runner_format', '—'),
                     req.get('json_chars_runner_format', '—'),
                     r['cost_and_tokens']['state_history_after_response_chars']['max'], f['memory_before_chars']])
    out += [table(['Job', 'Target', 'Первый input', 'Первый cached', 'Hit', 'Pre history chars', 'Request history chars', 'Max state_chars', 'Memory before chars'], rows),
            '', 'Managed notes не добавляются автоматически: их содержимое входит в контекст только через выполненный shell read. '
            'Больший первый ICL input описывает перенос истории, но разницу цен нельзя целиком приписать памяти: меняются действия, output, cache и ошибки.',
            '', '## 5. Native reasoning: retention и offline replay',
            'Для каждого доступного pre/post/error checkpoint проверены точный round-trip `from_state → export_state` и чистое построение `_payload()`. '
            'Ни `_headers()`, ни `step()` не вызываются. Anthropic добавляет cache_control на последний user block, OpenRouter удаляет response-only '
            '`tool_calls[].index`, Codex передаёт весь native input. Равенство проверяется с учётом только этих преобразований; подписи/encrypted data '
            'сравниваются в памяти, но не выводятся. Сохранённый pre проверяется как prefix post; trace с native responses и tool results реконструируется и '
            'сравнивается с post. Это проверяет реально сохранённые блоки, а не только декларацию кода.', '']
    for p, d in s['native_history_retention'].items():
        out.append(f'- **{p}**: новые native-блоки/поля в доступных post (без повторного суммирования inherited prefixes): '
                   f'`{json.dumps(d["new_native_reasoning_blocks_in_available_post_history"], ensure_ascii=False)}`. '
                   f'Prefix: {d["prefix_checks"]}; trace reconstruction: {d["trace_reconstruction_checks"]}; payload projection: {d["payload_projection_checks"]}.')
    out += ['', 'В JSON есть межзадачные проверки ICL (`previous post == next pre`), подтверждение reset для остальных arms и точные совпадения '
            'pre-history диагностических replay с исходным checkpoint. Не утверждается, что сервер обязательно использовал каждый opaque block, '
            'сохранил скрытое внутреннее состояние или что audit отправил повторный запрос. Криптографическая валидность подписей также не проверялась.',
            '', '## 6. Структура действий: эвристика, а не токен-атрибуция',
            '`action_categories.csv/json` содержат **каждую shell-команду**, её полный текст (с защитным redaction), адрес job/task/turn/command, '
            'результат, timing, пересекающиеся labels и причины классификации. '
            'Категории: схема/README/registry и ориентация; аналитика и подготовка ответа; memory file IO; следующий шаг после наблюдённой ошибки. '
            'IO разделён на discovery/read/write candidates; обращение к несуществующему memory path не считается доказанным чтением заметки.', '']
    rows = [[r['job'], r['phase'], r['commands'], *[r['category_counts_nonexclusive'][c] for c in CATEGORIES], r['mixed_commands'], r['commands_with_observed_error']] for r in a['by_job_phase'] if r['phase'] != 'all']
    out += [table(['Job', 'Фаза', 'Commands', 'Schema', 'Analytical', 'Memory IO', 'Recovery', 'Other', 'Mixed', 'С ошибкой'], rows), '',
            '**Оговорка аудита:** labels non-exclusive; суммы превышают число команд. Одна команда может читать README, schema, memory и выполнять SQL. '
            'Regex не строит shell AST, не доказывает исполнение ветвей `&&` и может видеть SQL внутри записываемого текста. '
            '«Recovery» — следующий command после exit/SQL/error-text, не доказанное исправление причины. '
            'На эти категории **не распределяются токены, USD или wall time**; нет выдуманной стоимости исследования схемы/памяти. '
            'Это прозрачный индекс для ручной проверки команд, а не точная оценка query count.',
            '', '## 7. Wall time и дорогие SQL-вызовы',
            'Model wall — latency `session.step()`, failed request wall — отдельно из checkpoint failure. Shell wall — всё выполнение bash; '
            'CLI SQL wall — внутренний замер subprocess sqlite3 и уже входит в shell. **Не складывать SQL+shell.** '
            'Суммы разных jobs не равны длительности всего исследования: jobs работали параллельно. '
            'Python `sqlite3` не обёрнут таймером; inline/ранее записанные scripts определяются лишь эвристически. '
            'Отсутствие CLI timer не доказывает отсутствие SQL (Python, подавленный stderr, убитая wrapper). '
            'Один CLI invocation может исполнять много SQL statements; timeout/kill не всегда оставляет timer.', '']
    rows = []
    for j in s['jobs']:
        t = j['all']['timing']
        rows.append([j['job'], f'{t["model_wall_success_s"]:.2f}', f'{t["model_wall_failed_observed_s"]:.2f}', f'{t["shell_wall_s"]:.2f}',
                     t['sql_cli_invocations'], f'{t["sql_cli_wall_s"]:.2f}', t['sql_cli_over_1s'],
                     t['shell_over_1s'], t['python_command_candidates'], t['python_sqlite_candidates']])
    out += [table(['Job', 'Model success s', 'Model failed s', 'Shell s', 'CLI invocations', 'CLI s', 'CLI >1s', 'Shell >1s', 'Python candidates', 'Python SQLite candidates'], rows),
            '', f'### Все реально наблюдённые SQL CLI invocations >1 s ({len(s["long_sql_cli_invocations_over_1s"])})',
            'Ниже полный список, а не только максимум. Wrapper сохраняет порядок таймеров, но не argv: для смешанной команды публикуется '
            'родительская команда целиком, без выдуманной привязки времени к отдельному SQL statement.', '']
    for l in s['long_sql_cli_invocations_over_1s']:
        out += [f'#### `{l["command_id"]}` — CLI #{l["sql_cli_timing_ordinal_1based"]}',
                f'CLI **{l["sql_cli_wall_s"]:.6f} s**, SQL exit `{l["sql_exit_code"]}`; shell {l["shell_wall_s"]:.6f} s, '
                f'shell exit `{l["shell_exit_code"]}`; группа `{l["cohort"]}`.', '', '````bash', l['parent_command'], '````', '']
    out += ['Список **всех shell >1 s**, включая Python без отдельного SQL timer, находится в `cost_summary.json → long_shell_commands_over_1s`; '
            'полные команды и durations также доступны в action CSV. Nonzero exit при длинном запросе — затраченное время, не успешный результат. '
            'Причину kill нельзя уверенно вывести лишь из exit code.',
            '', '## 8. Access / native smoke — отдельные известные затраты',
            'Не смешиваются с ledger исследования. Используются только сохранённые `usage` из доступных `access*.json` и `native_smoke.json`. '
            'Haiku оценён по тем же настроенным тарифам (smoke изначально мог иметь cost=null без rates); OR — `usage.cost`; Codex неизвестен. '
            'Каталоги, access summary, OAuth и ошибки без usage не превращаются в выдуманные $0 или предполагаемые inference-токены. '
            'Сохранённые данные не доказывают полноту всех исторических probes.', '']
    rows = []
    for e in s['access_probe_costs_separate']['entries']:
        n = e['tokens']
        rows.append([e['file'], e['provider'], e['turn_1based'] or '—', n['input_total'], n['output'], n['reasoning'], usd(e['cost_usd']), e['cost_source']])
    out += [table(['Файл', 'Provider', 'Turn', 'Input', 'Output', 'Reasoning', 'USD', 'Источник'], rows), '',
            table(['Provider', 'Известный probe subtotal USD', 'Полный USD', 'Записей usage'], [[p, usd(d['money']['known_usd_subtotal']), usd(d['money']['total_usd']), d['money']['entries']] for p, d in s['access_probe_costs_separate']['by_provider'].items()]),
            '', '## 9. Выводы и границы интерпретации',
            '- Денежный итог нужно брать из ledger с failed responses: сумма успешных traces занижает оплаченные расходы при output guard.',
            '- Reasoning у Haiku действительно наблюдается; исходный ноль — дефект локальной нормализации, а не отсутствие thinking.',
            '- Full-context ICL измеримо переносит историю; кэш уменьшает оплачиваемую нагрузку неодинаково по вызовам. Cache read и полный input — разные метрики.',
            '- Managed memory требует фактического чтения/записи. Категория directory discovery сама по себе не доказывает перенос полезной информации.',
            '- Большинство SQL CLI timings и shell timings следует читать раздельно; редкие долгие и неуспешные запросы могут заметно увеличить tool wall. Python SQL покрыт лишь частично.',
            '- Одна последовательность и выбранные постфактум диагностики не дают оснований объявлять причинную «цену памяти», универсальное преимущество arm или стоимость category в токенах.',
            '', '### Локальные источники',
            '- [`../providers.py`](../providers.py): `_tokens`, `_payload`, `_extract`, `from_state` и сохранение native history.',
            '- [`../run_study.py`](../run_study.py): `cost`, ledger, порядок сохранения turns, task/session lifecycle и state_chars.',
            '- [`../sandbox.py`](../sandbox.py): SQL CLI timing wrapper, shell wall, limits и частичное покрытие Python.',
            '- [`../provider_config.json`](../provider_config.json), [`../ledger.jsonl`](../ledger.jsonl), `../runs/*/{manifest.json,*/trace.json}`.',
            '- Private `pre_state/post_state/error_state` используются только для локальных сравнений; содержимое не публикуется.',
            '- [`amendments.md`](amendments.md), [`protocol.md`](protocol.md): исключение pilot v1 и отдельные диагностики.',
            '- [`../public_results/cost_summary.json`](../public_results/cost_summary.json), [`../public_results/action_categories.csv`](../public_results/action_categories.csv): воспроизводимые детали.', '']
    by_job = {j['job']: j for j in s['jobs']}
    findings = []
    def job_cost(j, ph='all'):
        row = by_job[j]
        return (row['all'] if ph == 'all' else row['phases'][ph])['ledger_all']['money']['total_usd']
    if all(j in by_job for j in ('main-glm-stateless', 'main-glm-icl', 'main-glm-managed')):
        findings.append(f"- **GLM, основные пять задач:** stateless ${job_cost('main-glm-stateless'):.6f}, ICL ${job_cost('main-glm-icl'):.6f}, managed ${job_cost('main-glm-managed'):.6f}. "
                        f"На T1–T3: ${job_cost('main-glm-stateless', 'target_T1T2T3'):.6f} / ${job_cost('main-glm-icl', 'target_T1T2T3'):.6f} / ${job_cost('main-glm-managed', 'target_T1T2T3'):.6f}. "
                        "Это observed cost, не стоимость достижения одинаковой точности.")
    if all(j in by_job for j in ('main-haiku-icl', 'main-haiku-managed', 'main-haiku-stateless', 'main-haiku-stateless-cont')):
        findings.append(f"- **Haiku:** ICL ${job_cost('main-haiku-icl'):.6f}, managed ${job_cost('main-haiku-managed'):.6f}. "
                        f"Исходный stateless с неуспешным T1 ${job_cost('main-haiku-stateless'):.6f}; продолжение T2/T3 ${job_cost('main-haiku-stateless-cont'):.6f}. "
                        f"Их бухгалтерская сумма ${job_cost('main-haiku-stateless')+job_cost('main-haiku-stateless-cont'):.6f} не превращает T1 в успешное решение; диагностический T1 оплачивается отдельно.")
    for p, prefix in [('Haiku', 'main-haiku'), ('GLM', 'main-glm'), ('Codex', 'pilot2-luna')]:
        ts = {r['arm']: r for r in s['tasks'] if r['task'] == 'T1' and r['job'].startswith(prefix) and r['cohort'] == 'primary'}
        if 'icl' in ts and 'stateless' in ts and all(ts[x]['first_target_turn'] and ts[x]['first_target_turn']['tokens'] for x in ('icl','stateless')):
            i = ts['icl']['first_target_turn']['tokens']; b = ts['stateless']['first_target_turn']['tokens']
            findings.append(f"- **Первый T1 input, {p}:** ICL {i['input_total']:,} против stateless {b['input_total']:,}; cached соответственно {i['input_cache_read']:,} и {b['input_cache_read']:,}. Это полный input, не выделенная цена inherited history.")
    aparts = s['provider_ledger_subtotals']['anthropic'].get('configured_price_components_all', {})
    asum = sum(aparts.values())
    if asum:
        findings.append(f"- **Структура известных Haiku USD:** output {100*aparts.get('output_usd',0)/asum:.1f}%, cache write {100*(aparts.get('cache_write_5m_usd',0)+aparts.get('cache_write_1h_usd',0))/asum:.1f}%, cache read {100*aparts.get('cache_read_usd',0)/asum:.1f}%. Reasoning уже внутри output.")
    out[4:4] = ['## Краткие численные результаты', '', *findings, '']
    return '\n'.join(out)


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+f'.{os.getpid()}.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    summary, actions = build(args.root.resolve())
    root = args.root.resolve()
    atomic_write(root/'public_results/cost_summary.json', json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    atomic_write(root/'public_results/action_categories.json', json.dumps(actions, ensure_ascii=False, indent=2)+'\n')
    buf = io.StringIO(newline='')
    fields = list(actions['commands'][0]) if actions['commands'] else ['command_id', 'command', 'categories']
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for row in actions['commands']:
        writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})
    atomic_write(root/'public_results/action_categories.csv', buf.getvalue())
    atomic_write(root/'analysis/cost_audit.md', report(summary, actions))
    print(json.dumps({'jobs': len(summary['jobs']), 'tasks': len(summary['tasks']), 'commands': len(actions['commands']),
                      'long_sql_cli': len(summary['long_sql_cli_invocations_over_1s']),
                      'provider_ledger_usd': {p: d['entire_ledger']['money']['total_usd'] for p, d in summary['provider_ledger_subtotals'].items()},
                      'reconciliation': summary['ledger_trace_reconciliation'],
                      'outputs': ['public_results/cost_summary.json', 'public_results/action_categories.json', 'public_results/action_categories.csv', 'analysis/cost_audit.md']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
