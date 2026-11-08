"""Live smoke test for the three providers (budget: cents).

For each key (``luna`` / ``haiku`` / ``glm``):

1. system prompt + one tool ``get_time(tz)``; the model must call the tool,
   receive the result and answer with text;
2. ``export_state()`` -> ``restore_conversation()`` must reproduce the exact
   native history, and the reasoning carrier must be present in the state
   (Codex: ``reasoning`` items with ``encrypted_content``; Anthropic: ``thinking``
   blocks if the model produced any; OpenRouter: ``reasoning_details`` if any);
3. a third call on the restored conversation must succeed.

Run with pytest (``pytest -s tests/test_providers_live.py``) or directly::

    python tests/test_providers_live.py [luna] [haiku] [glm]

Secrets: ``ANTHROPIC_API_KEY``, ``OPENROUTER_API_KEY`` (env), Codex tokens file
(see ``clrev.providers.openai_codex``).  Raw logs go to ``runs/_live_test/raw/``.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sys
import uuid
import zoneinfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from clrev.providers import ToolSpec, TurnResult, Usage, make_provider  # noqa: E402

try:  # pytest is optional
    import pytest
except ImportError:  # pragma: no cover
    pytest = None  # type: ignore[assignment]

KEYS = ["luna", "haiku", "glm"]
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "runs", "_live_test", "raw")

SYSTEM_PROMPT = (
    "You are a terse assistant. For any question about the current time or date you MUST call the "
    "get_time tool (you have no clock of your own) and then answer in one short sentence."
)
GET_TIME = ToolSpec(
    name="get_time",
    description="Return the current date and time in the given IANA time zone.",
    parameters={
        "type": "object",
        "properties": {"tz": {"type": "string", "description": "IANA time zone name, e.g. 'Europe/Berlin'."}},
        "required": ["tz"],
    },
)
MAX_STEPS = 4


def get_time(tz: str) -> str:
    try:
        z = zoneinfo.ZoneInfo(tz)
    except Exception:  # noqa: BLE001
        return f"error: unknown time zone {tz!r}"
    return dt.datetime.now(z).strftime("%Y-%m-%d %H:%M:%S %Z (%z)")


def run_tools(conv, first: TurnResult, label: str) -> tuple[TurnResult, Usage, int]:
    """Execute tool calls until the model answers with text. Returns (final, usage_sum, n_calls)."""
    res, total, n_calls = first, first.usage, 0
    for _ in range(MAX_STEPS):
        if not res.tool_calls:
            break
        outs = []
        for call in res.tool_calls:
            assert call.name == "get_time", f"{label}: unexpected tool {call.name}"
            tz = call.arguments.get("tz") or call.arguments.get("timezone") or "UTC"
            outs.append((call.id, get_time(str(tz))))
            n_calls += 1
            print(f"  [{label}] tool call {call.name}({call.arguments}) -> {outs[-1][1]}")
        conv.add_tool_results(outs)
        res = conv.step()
        total = total + res.usage
        _print_turn(label, res)
    return res, total, n_calls


def _print_turn(label: str, r: TurnResult) -> None:
    u = r.usage
    print(f"  [{label}] stop={r.stop_reason} latency={r.latency_s:.1f}s text={r.text!r:.120} "
          f"tool_calls={[c.name for c in r.tool_calls]} reasoning_summary={(r.reasoning_summary or '')[:80]!r}")
    print(f"  [{label}] usage: in={u.input_tokens} cached={u.cached_input_tokens} cache_write={u.cache_write_tokens} "
          f"out={u.output_tokens} reasoning={u.reasoning_tokens} cost=${(u.cost_usd or 0):.6f}")


def reasoning_carriers(key: str, state: dict) -> int:
    """Count native reasoning carriers in an exported state."""
    if key == "luna":
        return sum(1 for it in state["items"] if it.get("type") == "reasoning" and it.get("encrypted_content"))
    if key == "haiku":
        return sum(1 for m in state["messages"] if m["role"] == "assistant"
                   for b in m["content"] if b.get("type") in ("thinking", "redacted_thinking"))
    if key == "glm":
        return sum(1 for m in state["messages"] if m.get("role") == "assistant"
                   and (m.get("reasoning_details") or m.get("reasoning")))
    raise KeyError(key)


def run_live(key: str) -> dict:
    os.makedirs(RAW_DIR, exist_ok=True)
    p = make_provider(key)
    p.raw_log_path = os.path.join(RAW_DIR, f"{key}.jsonl")
    conv_id = f"live-{key}-{uuid.uuid4().hex[:8]}"
    conv = p.new_conversation(SYSTEM_PROMPT, [GET_TIME], conv_id=conv_id)
    print(f"\n=== {key} ({p.model}) conv_id={conv_id}")

    # --- step 1: must call the tool, then answer ------------------------------
    conv.add_user("Call get_time for America/Los_Angeles and Asia/Kolkata. If a call is scheduled for 09:30 Los "
                  "Angeles time next Monday, what is the exact local date and time in Kolkata? Show the arithmetic "
                  "in one line.")
    r1 = conv.step()
    _print_turn(key, r1)
    assert r1.tool_calls, f"{key}: model did not call get_time on the first turn"
    assert r1.stop_reason == "tool_use"
    final1, usage1, n_calls1 = run_tools(conv, r1, key)
    assert final1.text, f"{key}: no text answer after tool result"
    assert not final1.tool_calls
    assert n_calls1 >= 1

    # Reasoning is adaptive on all three models.  For Codex we want the encrypted reasoning
    # round-trip exercised, so provoke a little arithmetic until a reasoning item appears.
    if key == "luna":
        for extra in range(2):
            if reasoning_carriers(key, conv.export_state()):
                break
            print(f"  [{key}] no reasoning item yet; one more provoking turn ({extra + 1}/2)")
            conv.add_user("Also: how many hours apart are Tokyo and Los Angeles right now? Call get_time for both "
                          "and compute the difference, showing the arithmetic.")
            rx = conv.step()
            _print_turn(key, rx)
            fx, ux, nx = run_tools(conv, rx, key)
            usage1, n_calls1 = usage1 + ux, n_calls1 + nx

    # --- step 2: export / restore round-trip -------------------------------------
    state = conv.export_state()
    blob = json.dumps(state)  # must be JSON-serialisable
    conv2 = p.restore_conversation(json.loads(blob))
    assert conv2.export_state() == state, f"{key}: restored state differs"
    assert conv2.history_view() == conv.history_view()
    carriers = reasoning_carriers(key, state)
    print(f"  [{key}] state: {len(blob)} bytes, reasoning carriers in history: {carriers}")
    if usage1.reasoning_tokens > 0 or key == "luna":
        # When the model did reason, its native carrier must be in the history so the next call replays it.
        assert carriers >= 1, f"{key}: model reasoned ({usage1.reasoning_tokens} tokens) but no carrier in state"
    elif carriers == 0:
        print(f"  [{key}] WARNING: model emitted no reasoning (adaptive); carrier check skipped")
    if key == "luna":
        sizes = [len(it["encrypted_content"]) for it in state["items"] if it.get("type") == "reasoning"]
        print(f"  [{key}] encrypted_content sizes (chars): {sizes}")
    view = conv.history_view()
    roles = [v["role"] for v in view]
    assert roles[0] == "user" and "assistant" in roles and "tool" in roles, roles
    assert conv2.context_tokens_estimate() == conv.context_tokens_estimate() > 0

    # --- step 3: third call on the restored conversation ------------------------
    conv2.add_user("Thanks. And what time is it right now in Tokyo? One sentence.")
    r3 = conv2.step()
    _print_turn(key, r3)
    final3, usage3, n_calls3 = run_tools(conv2, r3, key)
    assert final3.text, f"{key}: no text answer on the restored conversation"
    total = usage1 + usage3
    cached_any = total.cached_input_tokens > 0
    print(f"  [{key}] TOTAL: in={total.input_tokens} cached={total.cached_input_tokens} "
          f"cache_write={total.cache_write_tokens} out={total.output_tokens} reasoning={total.reasoning_tokens} "
          f"cost=${(total.cost_usd or 0):.6f} tool_calls={n_calls1 + n_calls3} cache_hit_seen={cached_any}")
    print(f"  [{key}] context_tokens_estimate={conv2.context_tokens_estimate()} "
          f"history_view roles={[v['role'] for v in conv2.history_view()]}")
    return {"key": key, "model": p.model, "usage": total.to_dict(), "tool_calls": n_calls1 + n_calls3,
            "reasoning_carriers": reasoning_carriers(key, conv2.export_state()), "answer1": final1.text,
            "answer3": final3.text}


if pytest is not None:

    @pytest.mark.parametrize("key", KEYS)
    def test_provider_live(key: str) -> None:
        run_live(key)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    keys = sys.argv[1:] or KEYS
    results = [run_live(k) for k in keys]
    print("\n=== summary")
    for r in results:
        u = r["usage"]
        print(f"{r['key']:>6} {r['model']:<22} in={u['input_tokens']:>6} cached={u['cached_input_tokens']:>6} "
              f"cw={u['cache_write_tokens']:>5} out={u['output_tokens']:>5} reasoning={u['reasoning_tokens']:>5} "
              f"cost=${u['cost_usd']:.6f} carriers={r['reasoning_carriers']}")
