"""Compact trajectory dump for qualitative review.

usage: python -m clrev.inspect_ep runs/<run>/episodes/q13.json.gz [--full] [--sql-only]
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path


def load(path: str | Path) -> dict:
    p = Path(path)
    opener = gzip.open if p.suffix == ".gz" else open
    with opener(p, "rt") as f:
        return json.load(f)


def dump(ep: dict, full: bool = False, sql_only: bool = False, width: int = 700) -> str:
    out = []
    t = ep.get("totals", {})
    out.append(f"== {ep.get('question_id')} mode={ep.get('mode')} model={ep.get('model')} "
               f"correct={ep.get('correct')} answer={ep.get('answer')!r} gt={ep.get('gt', {}).get('answer') if isinstance(ep.get('gt'), dict) else ep.get('gt')!r}")
    out.append(f"   n_sql={ep.get('n_sql')} n_bash={ep.get('n_bash')} slow={len(ep.get('slow_sql') or [])} "
               f"in={t.get('input')} cached={t.get('cached')} out={t.get('output')} reasoning={t.get('reasoning')} "
               f"cost=${t.get('cost_usd', 0):.4f} wall={t.get('wall_s')}s ctx_end={ep.get('context_tokens_end')}")
    if ep.get("error"):
        out.append(f"   ERROR: {str(ep['error'])[:300]}")
    for i, turn in enumerate(ep.get("turns", [])):
        if not sql_only:
            rs = turn.get("reasoning_summary")
            if rs:
                out.append(f"-- turn {i} reasoning: {rs if full else rs[:width]}")
            if turn.get("text"):
                out.append(f"-- turn {i} text: {turn['text'] if full else turn['text'][:width]}")
        for c in turn.get("tool_calls", []):
            name = c.get("name")
            args = c.get("args", {})
            if name == "run_sql":
                out.append(f"-- turn {i} SQL ({c.get('ms', 0):.0f} ms): {args.get('sql')}")
            elif name == "bash":
                out.append(f"-- turn {i} BASH: {args.get('command')}")
            else:
                out.append(f"-- turn {i} {name}: {json.dumps(args, ensure_ascii=False)}")
            if not sql_only:
                prev = str(c.get("result_preview", ""))
                out.append("   -> " + (prev if full else prev[:width]).replace("\n", "\n      "))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--sql-only", action="store_true")
    a = ap.parse_args(argv)
    for p in a.paths:
        print(dump(load(p), full=a.full, sql_only=a.sql_only))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
