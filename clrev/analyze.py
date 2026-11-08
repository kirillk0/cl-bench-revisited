"""Paired analysis of several runs (typically stateless / icl / memory for one model).

CLI::

    python -m clrev.analyze --runs runs/A runs/B runs/C --out reports/<name>.md

Writes ``<name>.md`` and ``<name>.json`` with:

* per-question correctness table across runs + divergence class
  (``all-correct`` / ``only-<mode>-wrong`` / ``only-<mode>-correct`` / ``all-wrong`` / ``mixed``),
* per-run per-question metrics (n_sql, slow SQL, bash calls, tokens, cost, wall, context),
* cost structure per run (uncached vs cached input, cache writes, output, reasoning, USD),
* icl: context growth by question; memory: memory dir size (from episode stats or snapshot
  archives) and bash calls by question.

Episodes are read from ``episodes/*.json.gz`` (``summary.json`` is only a fallback).
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import sys
import tarfile
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("clrev.analyze")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


@dataclass
class RunData:
    """One loaded run."""

    path: Path
    config: dict[str, Any]
    rows: "OrderedDict[str, dict[str, Any]]" = field(default_factory=OrderedDict)  # qid -> compact row
    summary: dict[str, Any] | None = None
    label: str = ""

    @property
    def mode(self) -> str:
        return str(self.config.get("mode", "?"))

    @property
    def model(self) -> str:
        return str(self.config.get("model", "?"))

    @property
    def drift_after(self) -> int | None:
        return self.config.get("drift_after")


def _read_json(path: Path) -> Any:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text(encoding="utf-8"))


def _row_from_episode(ep: dict[str, Any]) -> dict[str, Any]:
    from clrev.runner import episode_row  # local import keeps analyze importable standalone

    row = episode_row(ep)
    row["n_post_submit_turns"] = ep.get("n_post_submit_turns", 0)
    row["slow_sql_list"] = ep.get("slow_sql") or []
    row["knowledge_tags"] = ep.get("knowledge_tags")
    row["difficulty"] = ep.get("difficulty")
    return row


def _snapshot_memory_bytes(run_dir: Path, qid: str) -> tuple[int | None, int | None]:
    snap = run_dir / "snapshots" / f"{qid}_memory.tar.gz"
    if not snap.exists():
        return None, None
    total = 0
    n = 0
    try:
        with tarfile.open(snap, "r:gz") as tar:
            for m in tar.getmembers():
                if m.isfile():
                    total += m.size
                    n += 1
    except (tarfile.TarError, OSError):
        return None, None
    return total, n


def load_run(path: str | Path) -> RunData:
    """Load config + episodes (compact rows) of a run directory."""
    run_dir = Path(path)
    cfg_path = run_dir / "config.json"
    config = _read_json(cfg_path) if cfg_path.exists() else {}
    rd = RunData(path=run_dir, config=config)
    summary_path = run_dir / "summary.json"
    if summary_path.exists():
        try:
            rd.summary = _read_json(summary_path)
        except (OSError, json.JSONDecodeError) as e:
            log.warning("%s: bad summary.json: %s", run_dir, e)
    ep_dir = run_dir / "episodes"
    rows: list[dict[str, Any]] = []
    if ep_dir.exists():
        for p in sorted(ep_dir.glob("q*.json*")):
            try:
                rows.append(_row_from_episode(_read_json(p)))
            except Exception as e:
                log.warning("%s: cannot read %s: %s", run_dir, p.name, e)
    if not rows and rd.summary:
        rows = list(rd.summary.get("per_question", []))
    order = {qid: i for i, qid in enumerate(config.get("question_ids", []))}
    rows.sort(key=lambda r: (order.get(r["question_id"], 10_000), r.get("seq_index") or 0, r["question_id"]))
    for r in rows:
        if r.get("memory_bytes") is None and rd.mode == "memory":
            r["memory_bytes"], r["memory_files"] = _snapshot_memory_bytes(run_dir, r["question_id"])
        rd.rows[r["question_id"]] = r
    return rd


def label_runs(runs: list[RunData]) -> None:
    """Assign short unique labels: mode, or model/mode, or directory name."""
    modes = [r.mode for r in runs]
    if len(set(modes)) == len(runs):
        for r in runs:
            r.label = r.mode
        return
    combos = [f"{r.model}/{r.mode}" for r in runs]
    if len(set(combos)) == len(runs):
        for r, c in zip(runs, combos):
            r.label = c
        return
    for r in runs:
        r.label = r.path.name


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def classify(results: "OrderedDict[str, bool | None]") -> str:
    """Name the divergence pattern of one question across runs (None = missing/error → wrong)."""
    wrong = [lab for lab, ok in results.items() if not ok]
    right = [lab for lab, ok in results.items() if ok]
    if not wrong:
        return "all-correct"
    if not right:
        return "all-wrong"
    if len(wrong) == 1:
        return f"only-{wrong[0]}-wrong"
    if len(right) == 1:
        return f"only-{right[0]}-correct"
    return "mixed:" + "+".join(wrong) + "-wrong"


def _fmt_tokens(n: Any) -> str:
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        return "?"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 10_000:
        return f"{n / 1000:.0f}k"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _fmt_cost(c: Any, known: bool = True) -> str:
    if c is None or not known:
        return "?"
    return f"${float(c):.4f}"


def _mark(row: dict[str, Any] | None) -> str:
    if row is None:
        return "—"
    if row.get("error"):
        return "⚠"
    if row.get("answer") is None:
        return "∅"
    return "✓" if row.get("correct") else "✗"


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    def esc(v: Any) -> str:
        return str(v).replace("|", "\\|").replace("\n", " ")

    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(esc(v) for v in r) + " |")
    return "\n".join(out)


def _accuracy(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "—"
    ok = sum(1 for r in rows if r.get("correct"))
    return f"{ok}/{len(rows)} ({100.0 * ok / len(rows):.0f}%)"


def analyze(runs: list[RunData]) -> dict[str, Any]:
    """Build the JSON report structure."""
    label_runs(runs)
    drift = next((r.drift_after for r in runs if r.drift_after is not None), None)
    # union of question ids in sequence order (first run's order wins)
    qids: list[str] = []
    for r in runs:
        for qid in r.rows:
            if qid not in qids:
                qids.append(qid)
    index_of = {qid: next((r.rows[qid].get("index") for r in runs if qid in r.rows), None) for qid in qids}

    per_question = []
    class_counter: Counter[str] = Counter()
    class_members: dict[str, list[str]] = {}
    for qid in qids:
        res: "OrderedDict[str, bool | None]" = OrderedDict()
        answers = {}
        for r in runs:
            row = r.rows.get(qid)
            res[r.label] = (bool(row["correct"]) if row and not row.get("error") else None)
            answers[r.label] = row.get("answer") if row else None
        cls = classify(res)
        class_counter[cls] += 1
        class_members.setdefault(cls, []).append(qid)
        gt = next((r.rows[qid].get("gt") for r in runs if qid in r.rows), None)
        idx = index_of.get(qid)
        per_question.append({
            "question_id": qid,
            "index": idx,
            "phase": ("post-drift" if drift is not None and idx is not None and idx > drift else "pre-drift"),
            "gt": gt,
            "results": dict(res),
            "answers": answers,
            "class": cls,
        })

    run_reports = []
    for r in runs:
        rows = list(r.rows.values())
        pre = [x for x in rows if drift is None or (x.get("index") or 0) <= drift]
        post = [x for x in rows if drift is not None and (x.get("index") or 0) > drift]
        tot = {k: sum(int(x.get(k) or 0) for x in rows) for k in
               ("input", "uncached", "cached", "cache_write", "output", "reasoning", "n_sql", "slow_sql", "n_bash", "n_turns")}
        tot["cost_usd"] = round(sum(float(x.get("cost_usd") or 0.0) for x in rows), 6)
        tot["cost_known"] = all(x.get("cost_known", False) for x in rows) if rows else False
        tot["wall_s"] = round(sum(float(x.get("wall_s") or 0.0) for x in rows), 1)
        tot["errors"] = sum(1 for x in rows if x.get("error"))
        tot["no_answer"] = sum(1 for x in rows if x.get("answer") is None and not x.get("error"))
        inp = tot["input"] or 0
        run_reports.append({
            "label": r.label,
            "path": str(r.path),
            "model": r.model,
            "mode": r.mode,
            "n": len(rows),
            "n_correct": sum(1 for x in rows if x.get("correct")),
            "accuracy": (sum(1 for x in rows if x.get("correct")) / len(rows)) if rows else None,
            "accuracy_pre_drift": (sum(1 for x in pre if x.get("correct")) / len(pre)) if pre else None,
            "accuracy_post_drift": (sum(1 for x in post if x.get("correct")) / len(post)) if post else None,
            "totals": tot,
            "cached_share": (tot["cached"] / inp) if inp else None,
            "context_tokens_end": rows[-1].get("context_tokens_end") if rows else None,
            "per_question": rows,
            "sandboxed_bash": r.config.get("sandboxed_bash"),
        })

    icl_growth = [
        {"label": rr["label"], "points": [{"question_id": x["question_id"], "context_tokens_end": x.get("context_tokens_end"),
                                           "input": x.get("input"), "cached": x.get("cached")} for x in rr["per_question"]]}
        for rr in run_reports if rr["mode"] == "icl"
    ]
    memory_growth = [
        {"label": rr["label"], "points": [{"question_id": x["question_id"], "memory_bytes": x.get("memory_bytes"),
                                           "memory_files": x.get("memory_files"), "n_bash": x.get("n_bash"),
                                           "n_post_submit_turns": x.get("n_post_submit_turns")} for x in rr["per_question"]]}
        for rr in run_reports if rr["mode"] == "memory"
    ]
    return {
        "runs": run_reports,
        "drift_after": drift,
        "question_ids": qids,
        "per_question": per_question,
        "classes": {"counts": dict(class_counter), "members": class_members},
        "icl_context_growth": icl_growth,
        "memory_growth": memory_growth,
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def render_markdown(rep: dict[str, Any], title: str) -> str:
    runs = rep["runs"]
    labels = [r["label"] for r in runs]
    drift = rep["drift_after"]
    md: list[str] = [f"# {title}", ""]
    md.append("Runs: " + ", ".join(f"`{r['label']}` = {r['path']} ({r['model']}, {r['mode']})" for r in runs))
    md.append("")
    if drift is not None:
        md.append(f"Silent migration after question {drift} (index in the full list).")
        md.append("")

    md += ["## Overview", ""]
    md.append(_md_table(
        ["run", "model", "mode", "accuracy", "pre-drift", "post-drift", "errors", "no answer", "cost", "wall", "n_sql", "slow", "n_bash"],
        [[r["label"], r["model"], r["mode"],
          _accuracy(r["per_question"]),
          _accuracy([x for x in r["per_question"] if drift is None or (x.get("index") or 0) <= drift]),
          _accuracy([x for x in r["per_question"] if drift is not None and (x.get("index") or 0) > drift]) if drift is not None else "—",
          r["totals"]["errors"], r["totals"]["no_answer"], _fmt_cost(r["totals"]["cost_usd"], r["totals"]["cost_known"]),
          f"{r['totals']['wall_s']:.0f}s", r["totals"]["n_sql"], r["totals"]["slow_sql"], r["totals"]["n_bash"]] for r in runs],
    ))
    md.append("")

    md += ["## Per-question correctness", "", "✓ correct · ✗ wrong · ∅ no answer · ⚠ error · — missing", ""]
    rows = []
    for pq in rep["per_question"]:
        cells = []
        for r in runs:
            row = r["per_question"]
            x = next((y for y in row if y["question_id"] == pq["question_id"]), None)
            cells.append(_mark(x))
        rows.append([pq["question_id"], pq["phase"], pq["gt"], *cells, pq["class"]])
    md.append(_md_table(["q", "phase", "gt", *labels, "class"], rows))
    md.append("")

    md += ["## Divergence classes", ""]
    counts = rep["classes"]["counts"]
    members = rep["classes"]["members"]
    order = sorted(counts, key=lambda c: (-counts[c], c))
    md.append(_md_table(["class", "n", "questions"], [[c, counts[c], ", ".join(members[c])] for c in order]))
    md.append("")

    md += ["## Answers on divergent questions", ""]
    div = [pq for pq in rep["per_question"] if pq["class"] not in ("all-correct",)]
    if div:
        md.append(_md_table(["q", "gt", *labels], [[pq["question_id"], pq["gt"], *[pq["answers"].get(lab) for lab in labels]] for pq in div]))
    else:
        md.append("(none)")
    md.append("")

    md += ["## Cost structure by run", "", "Tokens: uncached input / cached input / cache writes / output (reasoning ⊂ output).", ""]
    md.append(_md_table(
        ["run", "uncached in", "cached in", "cache write", "cached share", "output", "reasoning", "cost", "cost src", "wall", "turns", "ctx end"],
        [[r["label"], _fmt_tokens(r["totals"]["uncached"]), _fmt_tokens(r["totals"]["cached"]), _fmt_tokens(r["totals"]["cache_write"]),
          f"{100 * r['cached_share']:.0f}%" if r["cached_share"] is not None else "—",
          _fmt_tokens(r["totals"]["output"]), _fmt_tokens(r["totals"]["reasoning"]),
          _fmt_cost(r["totals"]["cost_usd"], r["totals"]["cost_known"]), "known" if r["totals"]["cost_known"] else "partial/unknown",
          f"{r['totals']['wall_s']:.0f}s", r["totals"]["n_turns"], r["context_tokens_end"] if r["context_tokens_end"] is not None else "—"]
         for r in runs],
    ))
    md.append("")

    for r in runs:
        md += [f"## Per-question metrics — `{r['label']}`", ""]
        md.append(_md_table(
            ["q", "ok", "answer", "n_sql", "slow", "bash", "turns", "in", "cached", "out", "reason", "cost", "wall", "ctx end"],
            [[x["question_id"], _mark(x), x.get("answer"), x.get("n_sql"), x.get("slow_sql"), x.get("n_bash"), x.get("n_turns"),
              _fmt_tokens(x.get("input")), _fmt_tokens(x.get("cached")), _fmt_tokens(x.get("output")), _fmt_tokens(x.get("reasoning")),
              _fmt_cost(x.get("cost_usd"), x.get("cost_known", True)), f"{float(x.get('wall_s') or 0):.0f}s",
              x.get("context_tokens_end") if x.get("context_tokens_end") is not None else "—"] for x in r["per_question"]],
        ))
        slow = [(x["question_id"], s) for x in r["per_question"] for s in (x.get("slow_sql_list") or [])]
        if slow:
            md += ["", f"Slow SQL (> 1 s) in `{r['label']}`:", ""]
            for qid, s in slow[:30]:
                sql = " ".join(str(s.get("sql", "")).split())
                md.append(f"- {qid} ({s.get('ms', '?')} ms): `{sql[:300]}`")
        md.append("")

    if rep["icl_context_growth"]:
        md += ["## ICL: context growth by question", ""]
        for g in rep["icl_context_growth"]:
            md.append(f"`{g['label']}`")
            md.append("")
            md.append(_md_table(["q", "context tokens at end", "episode input tokens", "episode cached"],
                                [[p["question_id"], p["context_tokens_end"] if p["context_tokens_end"] is not None else "—",
                                  _fmt_tokens(p["input"]), _fmt_tokens(p["cached"])] for p in g["points"]]))
            md.append("")

    if rep["memory_growth"]:
        md += ["## Memory: memory dir size and bash calls by question", ""]
        for g in rep["memory_growth"]:
            md.append(f"`{g['label']}`")
            md.append("")
            md.append(_md_table(["q", "memory bytes", "files", "bash calls", "post-submit turns"],
                                [[p["question_id"], p["memory_bytes"] if p["memory_bytes"] is not None else "—",
                                  p["memory_files"] if p["memory_files"] is not None else "—", p["n_bash"],
                                  p["n_post_submit_turns"]] for p in g["points"]]))
            md.append("")
    return "\n".join(md).rstrip() + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m clrev.analyze", description="Paired analysis of runs")
    p.add_argument("--runs", nargs="+", required=True, help="run directories (runs/<run_id>)")
    p.add_argument("--out", required=True, help="reports/<name>.md (a .json twin is written too)")
    p.add_argument("--title", default=None)
    a = p.parse_args(argv)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    runs = [load_run(r) for r in a.runs]
    rep = analyze(runs)
    out_md = Path(a.out)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    title = a.title or f"Memory modes report — {out_md.stem}"
    out_md.write_text(render_markdown(rep, title), encoding="utf-8")
    out_json = out_md.with_suffix(".json")
    out_json.write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log.info("wrote %s and %s", out_md, out_json)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
