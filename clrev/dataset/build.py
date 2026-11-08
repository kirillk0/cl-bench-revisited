"""Build the PayOps dataset: ``python -m clrev.dataset.build --out data/``.

Produces (deterministically, seed 20261108):
  payops.db       v1 schema          payops_v2.db   silently migrated schema
  questions.json  20 questions       STORIES.md     private documentation of the planted phenomena
  schema_v1.sql / schema_v2.sql      DDL dumps
and prints a validation report.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

from .common import Dataset
from .facts import build_settlement, build_txn
from .ops import build_ops
from .questions import build_questions
from .reference import build_reference
from .schema import dump_schema, migrate_v2, write_v1
from .stories_md import render
from .validate import independent_checks, run_ground_truth, run_naive, sanity_checks, story_stats


def generate() -> Dataset:
    """Generate every table in memory."""
    ds = Dataset()
    build_reference(ds)
    build_txn(ds)
    build_settlement(ds)
    build_ops(ds)
    return ds


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data", help="output directory (default: data/)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    print("[1/6] generating tables ...", flush=True)
    ds = generate()
    print("[2/6] writing payops.db ...", flush=True)
    v1, v2 = out / "payops.db", out / "payops_v2.db"
    write_v1(ds, v1)
    print("[3/6] migrating to payops_v2.db ...", flush=True)
    migrate_v2(ds, v1, v2)
    dump_schema(v1, out / "schema_v1.sql")
    dump_schema(v2, out / "schema_v2.sql")

    print("[4/6] building questions and running ground truth ...", flush=True)
    cons = {"v1": sqlite3.connect(f"file:{v1}?mode=ro", uri=True), "v2": sqlite3.connect(f"file:{v2}?mode=ro", uri=True)}
    questions = build_questions(ds, cons["v1"])
    timings = run_ground_truth(questions, cons)
    print("[5/6] validating (naive variants, pandas re-computation, sanity checks) ...", flush=True)
    naive = run_naive(questions, cons)
    independent = independent_checks(ds, questions)
    sanity_checks(ds, cons["v1"])
    stats = story_stats(ds, cons["v1"])

    row_counts = {}
    for name in [r[0] for r in cons["v1"].execute("SELECT name FROM sqlite_master WHERE type='table' AND name <> 'sqlite_stat1' ORDER BY name")]:
        row_counts[name] = cons["v1"].execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    for c in cons.values():
        c.close()
    sizes = {"payops.db": v1.stat().st_size, "payops_v2.db": v2.stat().st_size}

    print("[6/6] writing questions.json and STORIES.md ...", flush=True)
    with open(out / "questions.json", "w", encoding="utf-8") as f:
        json.dump([q.export() for q in questions], f, ensure_ascii=False, indent=2)
    with open(out / "STORIES.md", "w", encoding="utf-8") as f:
        f.write(render(ds, questions, stats, timings, naive, independent, row_counts, sizes))

    # ---------------------------------------------------------------- report
    print(f"\n=== PayOps dataset report (built in {time.time() - t_start:.1f} s) ===")
    for k, v in sizes.items():
        print(f"{k}: {v / 1e6:.1f} MB")
    print("\nrows per table:")
    for k, v in row_counts.items():
        print(f"  {k:24s} {v:>9,}")
    print("\nquestions:")
    for q, t in zip(questions, timings):
        print(f"  {q.id} [{q.stage:4s} {q.db}] {q.difficulty:6s} {t['ms']:7.1f} ms  answer={q.answer!r:28}  tags={','.join(q.knowledge_tags)}")
    print("\nindependent re-computation:")
    for r in independent:
        print(f"  {r['id']}: pandas={r['pandas']!r} sql={r['sql']!r} -> {'ok' if r['ok'] else 'MISMATCH'}")
    print("\nnaive variants (distinguishes = naive answer would be graded incorrect):")
    for r in naive:
        print(f"  {r['id']}: {r['label']!s:70.70s} naive={r['naive']!r:20} correct={r['correct']!r:20} {'DIFF' if r['distinguishes'] else 'same'}")
    slow = [t for t in timings if t["ms"] > 5000]
    bad = [r for r in independent if not r["ok"]]
    status = 0
    if slow:
        print(f"\nWARNING: slow GT queries: {slow}")
        status = 1
    if bad:
        print(f"\nERROR: independent checks failed: {bad}")
        status = 1
    if max(sizes.values()) > 80e6:
        print("\nWARNING: database larger than 80 MB")
        status = 1
    print("\nOK" if status == 0 else "\nFAILED")
    return status


if __name__ == "__main__":
    sys.exit(main())
