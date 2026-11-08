"""Build the PayOps dataset: ``python -m clrev.dataset.build --out data/``.

Produces (deterministically, seed 20261108):
  payops.db          v1 schema            payops_v2.db   silently migrated schema
  questions.json     20 questions, explicit wording ("explicit" variant)
  questions_v2.json  26 questions: the same 20 with business wording (no schema-mechanics hints)
                     + 6 investigative questions; every question carries ``naive_variants``
  STORIES.md         private documentation of the planted phenomena (incl. a section on v2)
  schema_v1.sql / schema_v2.sql      DDL dumps
and prints a validation report.

``--skip-db`` keeps the existing database files (the generator is deterministic, so the
in-memory frames still match them) and only rebuilds the question catalogues / STORIES.md.
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
from .questions_v2 import DRIFT_AFTER, build_questions_v2
from .reference import build_reference
from .schema import dump_schema, migrate_v2, write_v1
from .stories_md import render, render_v2
from .validate import (
    compute_margins,
    independent_checks,
    independent_checks_v2,
    run_ground_truth,
    run_naive,
    run_naive_variants,
    sanity_checks,
    story_stats,
)

GT_LIMIT_MS = 5000


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
    ap.add_argument("--skip-db", action="store_true",
                    help="do not rewrite payops.db / payops_v2.db (must already exist in --out); rebuild questions only")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    v1, v2 = out / "payops.db", out / "payops_v2.db"

    print("[1/7] generating tables ...", flush=True)
    ds = generate()
    if args.skip_db:
        if not (v1.exists() and v2.exists()):
            print(f"ERROR: --skip-db but {v1} / {v2} missing", file=sys.stderr)
            return 2
        print("[2/7] [3/7] --skip-db: keeping existing payops.db / payops_v2.db", flush=True)
    else:
        print("[2/7] writing payops.db ...", flush=True)
        write_v1(ds, v1)
        print("[3/7] migrating to payops_v2.db ...", flush=True)
        migrate_v2(ds, v1, v2)
        dump_schema(v1, out / "schema_v1.sql")
        dump_schema(v2, out / "schema_v2.sql")

    print("[4/7] building questions (v1 catalogue) and running ground truth ...", flush=True)
    cons = {"v1": sqlite3.connect(f"file:{v1}?mode=ro", uri=True), "v2": sqlite3.connect(f"file:{v2}?mode=ro", uri=True)}
    questions = build_questions(ds, cons["v1"])
    timings = run_ground_truth(questions, cons)
    print("[5/7] validating v1 (naive variants, pandas re-computation, sanity checks) ...", flush=True)
    naive = run_naive(questions, cons)
    independent = independent_checks(ds, questions)
    sanity_checks(ds, cons["v1"])
    stats = story_stats(ds, cons["v1"])

    print("[6/7] building questions v2 (hard wording + investigative) and validating ...", flush=True)
    questions_v2 = build_questions_v2(ds, questions)
    timings_v2 = run_ground_truth(questions_v2, cons)
    naive_v2 = run_naive_variants(questions_v2, cons)
    compute_margins(questions_v2, cons)          # fills Question.margin and appends it to the rationale
    independent_v2 = independent_checks_v2(ds, questions_v2, questions)

    row_counts = {}
    for name in [r[0] for r in cons["v1"].execute("SELECT name FROM sqlite_master WHERE type='table' AND name <> 'sqlite_stat1' ORDER BY name")]:
        row_counts[name] = cons["v1"].execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    for c in cons.values():
        c.close()
    sizes = {"payops.db": v1.stat().st_size, "payops_v2.db": v2.stat().st_size}

    print("[7/7] writing questions.json, questions_v2.json and STORIES.md ...", flush=True)
    with open(out / "questions.json", "w", encoding="utf-8") as f:
        json.dump([q.export() for q in questions], f, ensure_ascii=False, indent=2)
    with open(out / "questions_v2.json", "w", encoding="utf-8") as f:
        json.dump([q.export(with_variants=True) for q in questions_v2], f, ensure_ascii=False, indent=2)
    with open(out / "STORIES.md", "w", encoding="utf-8") as f:
        f.write(render(ds, questions, stats, timings, naive, independent, row_counts, sizes))
        f.write("\n")
        f.write(render_v2(questions_v2, timings_v2, naive_v2, independent_v2, DRIFT_AFTER, ds.meta.get("q22_slopes")))

    # ---------------------------------------------------------------- report
    print(f"\n=== PayOps dataset report (built in {time.time() - t_start:.1f} s) ===")
    for k, v in sizes.items():
        print(f"{k}: {v / 1e6:.1f} MB")
    print("\nrows per table:")
    for k, v in row_counts.items():
        print(f"  {k:24s} {v:>9,}")
    status = 0
    for label, qs, tm, ind, nv in (("questions.json", questions, timings, independent, naive),
                                   ("questions_v2.json", questions_v2, timings_v2, independent_v2, naive_v2)):
        print(f"\n--- {label} ---")
        for q, t in zip(qs, tm):
            margin = ""
            if q.margin:
                rel = q.margin.get("rel_margin")
                margin = f"  margin={q.margin['abs_margin']:g}" + (f" ({rel:.0%})" if rel is not None else "")
            print(f"  {q.id} [{q.stage:4s} {q.db}] {q.difficulty:6s} {t['ms']:7.1f} ms  answer={q.answer!r:28}  "
                  f"tags={','.join(q.knowledge_tags)}{margin}")
        print("independent re-computation:")
        for r in ind:
            print(f"  {r['id']}: pandas={r['pandas']!r} sql={r['sql']!r} -> {'ok' if r['ok'] else 'MISMATCH'}")
        print("naive variants (DIFF = naive answer would be graded incorrect):")
        for r in nv:
            print(f"  {r['id']}: {r['label']!s:78.78s} naive={r['naive']!r:22} correct={r['correct']!r:20} "
                  f"{'DIFF' if r['distinguishes'] else 'same'}")
        slow = [t for t in tm if t["ms"] > GT_LIMIT_MS]
        bad = [r for r in ind if not r["ok"]]
        if slow:
            print(f"\nWARNING: slow GT queries in {label}: {slow}")
            status = 1
        if bad:
            print(f"\nERROR: independent checks failed in {label}: {bad}")
            status = 1
    if max(sizes.values()) > 80e6:
        print("\nWARNING: database larger than 80 MB")
        status = 1
    print("\nOK" if status == 0 else "\nFAILED")
    return status


if __name__ == "__main__":
    sys.exit(main())
