"""Experiment runner for the memory-modes comparison (see SPEC.md).

CLI::

    python -m clrev.runner run --model {luna,haiku,glm} --mode {stateless,icl,memory} \
        --questions data/questions.json --db data/payops.db --db-v2 data/payops_v2.db \
        --drift-after N --out runs/<run_id> [--only q01,q05] [--max-turns 40] \
        [--post-submit-turns 8] [--parallel-questions K] [--resume]

    python -m clrev.runner replay --run runs/<run_id> --question qNN --from-snapshot \
        --repeats 3 [--memory-dir-override PATH]

Modes
-----
* ``stateless`` — fresh conversation per question; the episode ends right after the
  ``submit_answer`` feedback.
* ``icl`` — one conversation for the whole sequence; after the feedback tool result the
  next user message is the next question (no extra assistant turn unless
  ``--icl-post-submit-turns`` > 0).  ``export_state()`` snapshot after each question.
* ``memory`` — fresh conversation per question plus a ``bash`` tool in a persistent memory
  directory; after feedback the model may keep calling tools for up to
  ``--post-submit-turns`` turns.  tar.gz snapshot of the memory dir after each question.

A silent schema migration swaps the DB file after question ``--drift-after`` (position in
the full question list).  Every question gets its own private working copy of the DB.

Outputs: ``runs/<run_id>/config.json``, ``episodes/qNN.json.gz`` (full ``history_view`` and
per-turn log), ``snapshots/``, ``raw/`` (provider raw logs), ``summary.json``, ``replays/``.

Usage token convention (documented for the cost estimate): ``Usage.input_tokens`` is the
*total* prompt size including ``cached_input_tokens`` and ``cache_write_tokens``;
``output_tokens`` includes ``reasoning_tokens``.  If a provider reports
``cached + cache_write > input`` the runner treats ``input_tokens`` as the uncached part.
"""

from __future__ import annotations

import argparse
import dataclasses
import gzip
import inspect
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from clrev import grade as grading
from clrev.providers.base import Conversation, Provider, ToolCall, TurnResult, Usage
from clrev.tools import (
    BASH_TIMEOUT_S,
    CHAR_CAP,
    ROW_CAP,
    SQL_TIMEOUT_S,
    BashTool,
    SqlTool,
    make_db_working_copy,
    tool_specs,
)

log = logging.getLogger("clrev.runner")

HARNESS_VERSION = "2026.11.1"
MODES = ("stateless", "icl", "memory")
MODELS = ("luna", "haiku", "glm")

ProviderFactory = Callable[[str, Path], Provider]

# ---------------------------------------------------------------------------
# Prompts (identical across models)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_BASE = (
    "You are a data analyst agent with read-only SQL access to a SQLite database. The schema "
    "is not provided — explore it with SQL (sqlite_master, PRAGMA table_info, sampling). "
    "Answer the question by running queries with `run_sql`, then call `submit_answer` with the "
    "final value only, in the format the question asks for. You may run as many queries as you "
    "need. After submitting you will be told whether the answer was correct."
)
ICL_ADDENDUM = (
    "You will be asked a series of questions about the same database in this conversation."
)
MEMORY_ADDENDUM = (
    "You also have a `bash` tool. It runs in a persistent working directory that is kept "
    "between sessions (each question is a separate session with no conversation history). "
    "Anything you write there is available in later sessions, and anything from earlier "
    "sessions is already there. Using it is optional; what to keep, if anything, is up to you."
)
NUDGE_MESSAGE = "Please call `submit_answer` with your final answer."


def system_prompt(mode: str) -> str:
    """System prompt for a mode."""
    if mode == "stateless":
        return SYSTEM_PROMPT_BASE
    if mode == "icl":
        return f"{SYSTEM_PROMPT_BASE} {ICL_ADDENDUM}"
    if mode == "memory":
        return f"{SYSTEM_PROMPT_BASE} {MEMORY_ADDENDUM}"
    raise ValueError(f"unknown mode {mode!r}")


def question_message(q: dict[str, Any], k: int, n: int) -> str:
    """User message for question ``k`` of ``n`` (never mentions DB changes)."""
    text = str(q.get("text") or q.get("question") or "").strip()
    fmt = None
    for key in ("answer_format", "expected_format", "format"):
        if q.get(key):
            fmt = str(q[key]).strip()
            break
    if fmt and fmt.lower() not in text.lower():
        text = f"{text}\n\nAnswer format: {fmt}"
    return f"Question {k} of {n}.\n\n{text}"


# ---------------------------------------------------------------------------
# Pricing (USD per 1M tokens) — used only when the provider gives no cost
# ---------------------------------------------------------------------------

PRICES: dict[str, Any] = {
    "luna": {"input": 0.10, "cached": 0.01, "cache_write": 0.125, "output": 0.50},
    "haiku": {  # tiered by total prompt size; ``up_to`` None = unbounded
        "tiers": [
            {"up_to": 100_000, "input": 0.10, "cached": 0.01, "cache_write": 0.125, "output": 0.50},
            {"up_to": None, "input": 0.50, "cached": 0.05, "cache_write": 0.625, "output": 2.50},
        ]
    },
    "glm": {"input": 0.0335, "cached": 0.0335, "cache_write": 0.0335, "output": 0.083},
}


def split_input_tokens(u: Usage) -> tuple[int, int, int]:
    """Return (uncached, cached, cache_write) input tokens under the documented convention."""
    inp = int(u.input_tokens or 0)
    cached = int(u.cached_input_tokens or 0)
    cw = int(u.cache_write_tokens or 0)
    if cached + cw > inp:  # provider reports exclusive input_tokens (Anthropic raw style)
        return inp, cached, cw
    return max(0, inp - cached - cw), cached, cw


def estimate_cost(model_key: str, u: Usage) -> float | None:
    """Estimate USD cost of one turn from the price table; None for unknown models."""
    table = PRICES.get(model_key)
    if table is None:
        return None
    uncached, cached, cw = split_input_tokens(u)
    prompt_total = uncached + cached + cw
    if "tiers" in table:
        prices = next(p for p in table["tiers"] if p["up_to"] is None or prompt_total <= p["up_to"])
    else:
        prices = table
    out = int(u.output_tokens or 0)
    cost = (
        uncached * prices["input"] + cached * prices["cached"] + cw * prices["cache_write"] + out * prices["output"]
    ) / 1_000_000.0
    return round(cost, 8)


def usage_to_dict(u: Usage | None) -> dict[str, Any]:
    if u is None:
        return {"input_tokens": 0, "cached_input_tokens": 0, "cache_write_tokens": 0, "output_tokens": 0,
                "reasoning_tokens": 0, "cost_usd": None, "raw": {}}
    try:
        d = dataclasses.asdict(u)
    except TypeError:
        d = {k: getattr(u, k, None) for k in ("input_tokens", "cached_input_tokens", "cache_write_tokens",
                                                "output_tokens", "reasoning_tokens", "cost_usd", "raw")}
    return d


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class RunConfig:
    """All parameters of a run (serialised to ``config.json``)."""

    run_id: str
    model: str
    mode: str
    questions: str
    db: str
    db_v2: str | None
    drift_after: int | None
    out: str
    only: list[str] | None = None
    max_turns: int = 40
    post_submit_turns: int = 8
    icl_post_submit_turns: int = 0
    parallel_questions: int = 1
    max_nudges: int = 1
    sql_timeout_s: float = SQL_TIMEOUT_S
    bash_timeout_s: float = BASH_TIMEOUT_S
    row_cap: int = ROW_CAP
    char_cap: int = CHAR_CAP
    memory_dir: str | None = None
    resume: bool = False
    retry_errors: bool = False
    # filled by the runner
    question_ids: list[str] = field(default_factory=list)
    n_questions: int = 0
    system_prompt: str = ""
    tools: list[dict[str, Any]] = field(default_factory=list)
    harness_version: str = HARNESS_VERSION
    created_at: str = ""
    hostname: str = ""
    git_commit: str | None = None
    sandboxed_bash: bool | None = None
    usage_convention: str = "input_tokens includes cached and cache_write; output_tokens includes reasoning"
    prices: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RunConfig":
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    @property
    def run_dir(self) -> Path:
        return Path(self.out)


# ---------------------------------------------------------------------------
# Small IO helpers (atomic, Ctrl-C safe)
# ---------------------------------------------------------------------------


def _json_default(o: Any) -> Any:
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return dataclasses.asdict(o)
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, (bytes, bytearray)):
        return f"<{len(o)} bytes>"
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    return repr(o)


def dump_json(obj: Any, indent: int | None = 2) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=indent, default=_json_default)


def write_json_atomic(path: str | Path, obj: Any, *, gz: bool | None = None) -> Path:
    """Write JSON to ``path`` atomically (tmp file + rename); gzip if ``path`` ends with .gz."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    gz = p.suffix == ".gz" if gz is None else gz
    data = dump_json(obj).encode("utf-8")
    tmp = p.with_name(p.name + f".tmp{os.getpid()}.{threading.get_ident()}")
    try:
        if gz:
            with gzip.open(tmp, "wb", compresslevel=6) as f:
                f.write(data)
        else:
            tmp.write_bytes(data)
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            tmp.unlink()
    return p


def read_json(path: str | Path) -> Any:
    p = Path(path)
    if p.suffix == ".gz":
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(p.read_text(encoding="utf-8"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_commit(repo: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


def load_questions(path: str | Path) -> list[dict[str, Any]]:
    """Load ``questions.json`` (a list, or ``{"questions": [...]}``)."""
    data = read_json(path)
    if isinstance(data, dict):
        data = data.get("questions", data.get("items"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a list of questions")
    out = []
    for i, q in enumerate(data, 1):
        q = dict(q)
        q.setdefault("id", f"q{i:02d}")
        q["_index"] = i  # 1-based position in the full list (drift uses this)
        out.append(q)
    return out


def select_questions(questions: list[dict[str, Any]], only: Iterable[str] | None) -> list[dict[str, Any]]:
    if not only:
        return list(questions)
    wanted: list[str] = []
    for item in only:
        for part in str(item).split(","):
            part = part.strip()
            if not part:
                continue
            if part.isdigit():
                part = f"q{int(part):02d}"
            wanted.append(part)
    by_id = {q["id"]: q for q in questions}
    missing = [w for w in wanted if w not in by_id]
    if missing:
        raise SystemExit(f"unknown question ids: {missing}")
    return [by_id[w] for w in wanted]


def gt_record(q: dict[str, Any]) -> dict[str, Any]:
    return {"answer": q.get("answer"), "type": q.get("type", "str"), "tolerance": q.get("tolerance")}


def db_variant_for(cfg: RunConfig, q: dict[str, Any]) -> tuple[str, str]:
    """(variant, db path) for a question: v2 after ``drift_after`` when ``db_v2`` is set."""
    idx = int(q.get("_index", 0))
    if cfg.db_v2 and cfg.drift_after is not None and cfg.drift_after >= 0 and idx > cfg.drift_after:
        return "v2", cfg.db_v2
    return "v1", cfg.db


# ---------------------------------------------------------------------------
# Episode execution
# ---------------------------------------------------------------------------


@dataclass
class EpisodeState:
    """Mutable state shared by the tool executor during one episode."""

    gt: dict[str, Any]
    sql: SqlTool
    bash: BashTool | None
    n_sql: int = 0
    n_bash: int = 0
    slow_sql: list[dict[str, Any]] = field(default_factory=list)
    submitted: str | None = None
    grade: grading.GradeResult | None = None
    feedback: str | None = None


def _coerce_args(args: Any) -> dict[str, Any]:
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        try:
            v = json.loads(args)
            return v if isinstance(v, dict) else {"value": v}
        except json.JSONDecodeError:
            return {"value": args}
    return {}


def execute_tool(call: ToolCall, st: EpisodeState) -> tuple[str, dict[str, Any]]:
    """Execute one tool call; returns (result text for the model, log record)."""
    args = _coerce_args(call.arguments)
    rec: dict[str, Any] = {"id": call.id, "name": call.name, "args": args, "ms": 0.0}
    t0 = time.monotonic()
    if call.name == "run_sql":
        sql = args.get("sql", args.get("query", args.get("value")))
        if not isinstance(sql, str) or not sql.strip():
            out = "Error: missing 'sql' argument."
            rec["error"] = out
        else:
            r = st.sql.run(sql)
            st.n_sql += 1
            if r.slow:
                st.slow_sql.append({"sql": sql, "ms": round(r.ms, 1)})
            out = r.text
            rec.update({"ms": round(r.ms, 1), "rows": r.rows_returned, "rows_total": r.rows_total,
                        "truncated": r.truncated, "error": r.error, "slow": r.slow})
    elif call.name == "bash":
        if st.bash is None:
            out = "Error: tool 'bash' is not available."
            rec["error"] = out
        else:
            command = args.get("command", args.get("cmd", args.get("value")))
            if not isinstance(command, str):
                out = "Error: missing 'command' argument."
                rec["error"] = out
            else:
                r = st.bash.run(command)
                st.n_bash += 1
                out = r.text
                rec.update({"ms": round(r.ms, 1), "exit_code": r.exit_code, "timed_out": r.timed_out,
                            "truncated": r.truncated})
    elif call.name == "submit_answer":
        answer = args.get("answer", args.get("value"))
        answer_text = "" if answer is None else (answer if isinstance(answer, str) else json.dumps(answer))
        if st.submitted is None:
            st.submitted = answer_text
            st.grade = grading.grade_answer(answer_text, st.gt)
            st.feedback = grading.feedback_text(st.grade)
            out = st.feedback
            rec["grade"] = st.grade.to_dict()
        else:
            out = f"An answer was already submitted for this question. {st.feedback}"
            rec["ignored"] = True
    else:
        out = f"Error: unknown tool '{call.name}'."
        rec["error"] = out
    if not rec.get("ms"):
        rec["ms"] = round((time.monotonic() - t0) * 1000.0, 1)
    rec["result_preview"] = out[:600] + ("…" if len(out) > 600 else "")
    rec["result_chars"] = len(out)
    return out, rec


def turn_record(tr: TurnResult, phase: str, model_key: str) -> dict[str, Any]:
    usage = usage_to_dict(getattr(tr, "usage", None))
    cost = usage.get("cost_usd")
    source = "provider"
    if cost is None and getattr(tr, "usage", None) is not None:
        cost = estimate_cost(model_key, tr.usage)
        source = "estimated" if cost is not None else "unknown"
    return {
        "phase": phase,
        "text": tr.text,
        "reasoning_summary": tr.reasoning_summary,
        "tool_calls": [],
        "usage": usage,
        "cost_usd": cost,
        "cost_source": source,
        "stop_reason": tr.stop_reason,
        "latency_s": round(float(tr.latency_s or 0.0), 3),
    }


def sum_totals(turns: list[dict[str, Any]], wall_s: float) -> dict[str, Any]:
    tot = {"input": 0, "cached": 0, "cache_write": 0, "uncached": 0, "output": 0, "reasoning": 0,
           "cost_usd": 0.0, "cost_known": True, "wall_s": round(wall_s, 3), "n_turns": len(turns),
           "latency_s": 0.0}
    for t in turns:
        u = t.get("usage") or {}
        inp = int(u.get("input_tokens") or 0)
        cached = int(u.get("cached_input_tokens") or 0)
        cw = int(u.get("cache_write_tokens") or 0)
        tot["input"] += inp
        tot["cached"] += cached
        tot["cache_write"] += cw
        tot["uncached"] += inp if cached + cw > inp else max(0, inp - cached - cw)
        tot["output"] += int(u.get("output_tokens") or 0)
        tot["reasoning"] += int(u.get("reasoning_tokens") or 0)
        tot["latency_s"] += float(t.get("latency_s") or 0.0)
        if t.get("cost_usd") is None:
            tot["cost_known"] = False
        else:
            tot["cost_usd"] += float(t["cost_usd"])
    tot["cost_usd"] = round(tot["cost_usd"], 6)
    tot["latency_s"] = round(tot["latency_s"], 3)
    return tot


def run_episode(
    conv: Conversation,
    q: dict[str, Any],
    k: int,
    n: int,
    cfg: RunConfig,
    sql_tool: SqlTool,
    bash_tool: BashTool | None,
    *,
    db_variant: str,
) -> dict[str, Any]:
    """Run one question inside ``conv`` and return the episode record.

    Never raises for provider errors (recorded in ``episode["error"]``); KeyboardInterrupt
    propagates.
    """
    mode = cfg.mode
    post_limit = {"memory": cfg.post_submit_turns, "icl": cfg.icl_post_submit_turns}.get(mode, 0)
    st = EpisodeState(gt=gt_record(q), sql=sql_tool, bash=bash_tool)
    turns: list[dict[str, Any]] = []
    started = utc_now()
    t0 = time.monotonic()
    error: str | None = None
    tb: str | None = None
    stop = "unknown"
    nudges = 0
    answer_turns = 0
    post_turns = 0
    try:
        conv.add_user(question_message(q, k, n))
        while True:
            if st.submitted is None and answer_turns >= cfg.max_turns:
                stop = "max_turns"
                break
            if st.submitted is not None and post_turns >= post_limit:
                stop = "post_submit_limit"
                break
            tr = conv.step()
            phase = "answer" if st.submitted is None else "post_submit"
            rec = turn_record(tr, phase, cfg.model)
            turns.append(rec)
            calls = list(tr.tool_calls or [])
            if not calls:
                if st.submitted is None and nudges < cfg.max_nudges:
                    nudges += 1
                    rec["nudged"] = True
                    conv.add_user(NUDGE_MESSAGE)
                    continue
                stop = "no_answer" if st.submitted is None else "done"
                break
            if phase == "answer":
                answer_turns += 1
            else:
                post_turns += 1
            results: list[tuple[str, str]] = []
            for call in calls:
                out, crec = execute_tool(call, st)
                rec["tool_calls"].append(crec)
                results.append((call.id, out))
            conv.add_tool_results(results)
            if st.submitted is not None and phase == "answer" and post_limit == 0:
                stop = "submitted"
                break
    except KeyboardInterrupt:
        raise
    except Exception as e:  # provider / tool failure: record, continue the sequence
        error = f"{type(e).__name__}: {e}"
        tb = traceback.format_exc()
        stop = "error"
        log.error("%s: episode error: %s", q.get("id"), error)
    wall = time.monotonic() - t0

    def _safe(fn: Callable[[], Any], default: Any) -> Any:
        try:
            return fn()
        except Exception as e:  # pragma: no cover - defensive
            log.warning("%s: %s failed: %s", q.get("id"), getattr(fn, "__name__", "call"), e)
            return default

    ep: dict[str, Any] = {
        "question_id": q["id"],
        "index": q.get("_index"),
        "seq_index": k,
        "n_in_sequence": n,
        "mode": mode,
        "model": cfg.model,
        "db_variant": db_variant,
        "question_text": q.get("text"),
        "correct": bool(st.grade.correct) if st.grade is not None else False,
        "answer": st.submitted,
        "gt": st.gt["answer"],
        "gt_type": st.gt["type"],
        "tolerance": st.gt["tolerance"],
        "grade": st.grade.to_dict() if st.grade is not None else None,
        "feedback": st.feedback,
        "n_sql": st.n_sql,
        "n_bash": st.n_bash,
        "slow_sql": st.slow_sql,
        "n_turns": len(turns),
        "n_answer_turns": answer_turns,
        "n_post_submit_turns": post_turns,
        "nudges": nudges,
        "stop_reason": stop,
        "turns": turns,
        "totals": sum_totals(turns, wall),
        "context_tokens_end": _safe(conv.context_tokens_estimate, None),
        "error": error,
        "traceback": tb,
        "started_at": started,
        "finished_at": utc_now(),
        "knowledge_tags": q.get("knowledge_tags"),
        "difficulty": q.get("difficulty"),
    }
    if bash_tool is not None:
        ep["memory"] = _safe(bash_tool.dir_stats, None)
    ep["history_view"] = _safe(conv.history_view, None)
    return ep


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


def snapshot_state_path(run_dir: Path, qid: str) -> Path:
    return run_dir / "snapshots" / f"{qid}_state.json.gz"


def snapshot_memory_path(run_dir: Path, qid: str) -> Path:
    return run_dir / "snapshots" / f"{qid}_memory.tar.gz"


def tar_dir(src: Path, dst: Path) -> Path:
    """tar.gz the contents of ``src`` (paths relative to ``src``) atomically."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp")
    with tarfile.open(tmp, "w:gz") as tar:
        tar.add(src, arcname=".")
    os.replace(tmp, dst)
    return dst


def untar_dir(archive: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        try:
            tar.extractall(dst, filter="data")
        except TypeError:  # Python < 3.12
            tar.extractall(dst)


def clear_dir(path: Path) -> None:
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def copy_tree_contents(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        target = dst / child.name
        if child.is_dir() and not child.is_symlink():
            shutil.copytree(child, target, symlinks=True)
        else:
            shutil.copy2(child, target, follow_symlinks=False)


# ---------------------------------------------------------------------------
# Permission hardening for memory mode (root only; see report for what is NOT isolated)
# ---------------------------------------------------------------------------


def harden_permissions(cfg: RunConfig, run_dir: Path) -> None:
    """Hide GT/DB files from ``memuser``: chmod 600 DB files, 700 data dir and run sub-dirs.

    Tracked text files are not chmod-ed (would show up as git mode changes); directory modes
    are not tracked by git.  No-op when not root.
    """
    if os.geteuid() != 0:
        return
    for db in (cfg.db, cfg.db_v2):
        if db and Path(db).exists():
            try:
                os.chmod(db, 0o600)
            except OSError as e:
                log.warning("chmod %s failed: %s", db, e)
    data_dir = Path(cfg.questions).resolve().parent
    for d in {data_dir, Path(cfg.db).resolve().parent}:
        if d.exists() and d != Path("/"):
            try:
                os.chmod(d, 0o700)
            except OSError as e:
                log.warning("chmod %s failed: %s", d, e)
    for sub in ("episodes", "raw", "snapshots", "work", "replays"):
        p = run_dir / sub
        p.mkdir(parents=True, exist_ok=True)
        os.chmod(p, 0o700)
    for d in (run_dir, run_dir.parent):
        try:
            os.chmod(d, 0o711)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def default_provider_factory(model_key: str, raw_log_path: Path) -> Provider:
    """Build a real provider via ``clrev.providers.make_provider`` (lazy import).

    Passes ``raw_log_path=<str>`` when the factory accepts it (named or ``**kwargs``);
    otherwise sets the provider's ``raw_log_path`` attribute after construction.
    """
    from clrev.providers import make_provider  # type: ignore[attr-defined]

    raw_log_path.parent.mkdir(parents=True, exist_ok=True)
    path = str(raw_log_path)
    try:
        params = inspect.signature(make_provider).parameters
    except (TypeError, ValueError):
        params = {}
    accepts_kwargs = any(p.kind == p.VAR_KEYWORD for p in params.values())
    if "raw_log_path" in params or accepts_kwargs:
        return make_provider(model_key, raw_log_path=path)
    provider = make_provider(model_key)
    try:
        provider.raw_log_path = path  # type: ignore[attr-defined]
    except Exception as e:  # pragma: no cover - defensive
        log.warning("could not set raw_log_path on provider: %s", e)
    return provider


class Runner:
    """Runs a sequence of questions in one mode and writes all artefacts."""

    def __init__(self, cfg: RunConfig, provider_factory: ProviderFactory = default_provider_factory) -> None:
        self.cfg = cfg
        self.provider_factory = provider_factory
        self.run_dir = Path(cfg.out)
        self.questions_all = load_questions(cfg.questions)
        self.sequence = select_questions(self.questions_all, cfg.only)
        self.episodes: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._provider: Provider | None = None
        self._t_start = time.monotonic()

    # -- paths ------------------------------------------------------------------
    @property
    def episodes_dir(self) -> Path:
        return self.run_dir / "episodes"

    def episode_path(self, qid: str) -> Path:
        return self.episodes_dir / f"{qid}.json.gz"

    @property
    def memory_dir(self) -> Path:
        return Path(self.cfg.memory_dir) if self.cfg.memory_dir else self.run_dir / "memory"

    @property
    def provider(self) -> Provider:
        with self._lock:
            if self._provider is None:
                raw = self.run_dir / "raw" / f"{self.cfg.model}_{self.cfg.mode}.jsonl"
                self._provider = self.provider_factory(self.cfg.model, raw)
            return self._provider

    # -- setup ------------------------------------------------------------------
    def prepare(self) -> None:
        cfg = self.cfg
        if cfg.mode not in MODES:
            raise SystemExit(f"unknown mode {cfg.mode!r}")
        if cfg.parallel_questions > 1 and cfg.mode != "stateless":
            log.warning("--parallel-questions is only used in stateless mode; ignoring")
            cfg.parallel_questions = 1
        existing = sorted(self.episodes_dir.glob("q*.json.gz")) if self.episodes_dir.exists() else []
        if existing and not cfg.resume:
            raise SystemExit(f"{self.run_dir} already has {len(existing)} episodes; use --resume or a new --out")
        for sub in ("episodes", "raw", "snapshots", "work"):
            (self.run_dir / sub).mkdir(parents=True, exist_ok=True)
        cfg.question_ids = [q["id"] for q in self.sequence]
        cfg.n_questions = len(self.sequence)
        cfg.system_prompt = system_prompt(cfg.mode)
        cfg.tools = [dataclasses.asdict(t) for t in tool_specs(cfg.mode)]
        cfg.created_at = cfg.created_at or utc_now()
        cfg.hostname = socket.gethostname()
        cfg.git_commit = git_commit(Path(__file__).resolve().parent.parent)
        cfg.prices = PRICES.get(cfg.model, {})
        if cfg.db_v2 and cfg.drift_after is None:
            log.warning("--db-v2 given without --drift-after: the migrated DB will never be used")
        if cfg.drift_after is not None and not cfg.db_v2:
            log.warning("--drift-after given without --db-v2: no DB swap will happen")
        if cfg.mode == "memory":
            self.memory_dir.mkdir(parents=True, exist_ok=True)
            harden_permissions(cfg, self.run_dir)
        for p in existing:
            try:
                ep = read_json(p)
                self.episodes[ep["question_id"]] = ep
            except Exception as e:  # corrupt file → treat as missing
                log.warning("could not read %s: %s", p, e)
        write_json_atomic(self.run_dir / "config.json", cfg.to_dict())

    # -- helpers ----------------------------------------------------------------
    def _is_done(self, qid: str) -> bool:
        ep = self.episodes.get(qid)
        if ep is None:
            return False
        if self.cfg.retry_errors and ep.get("error"):
            return False
        return True

    def _resume_point(self) -> int:
        """Index into ``self.sequence`` of the first question to run (sequence modes)."""
        last = -1
        for i, q in enumerate(self.sequence):
            if q["id"] in self.episodes:
                last = i
        while last >= 0 and self.cfg.retry_errors and self.episodes[self.sequence[last]["id"]].get("error"):
            last -= 1
        return last + 1

    def _save_episode(self, ep: dict[str, Any]) -> None:
        write_json_atomic(self.episode_path(ep["question_id"]), ep)
        with self._lock:
            self.episodes[ep["question_id"]] = ep
        t = ep["totals"]
        mark = "✓" if ep["correct"] else ("ERR" if ep.get("error") else "✗")
        log.info(
            "%s %s answer=%r gt=%r sql=%d slow=%d bash=%d turns=%d in=%d cached=%d out=%d cost=%s wall=%.1fs ctx=%s",
            ep["question_id"], mark, ep.get("answer"), ep.get("gt"), ep["n_sql"], len(ep["slow_sql"]),
            ep["n_bash"], ep["n_turns"], t["input"], t["cached"], t["output"],
            f"${t['cost_usd']:.4f}" if t["cost_known"] else "?", t["wall_s"], ep.get("context_tokens_end"),
        )

    def _work_db(self, q: dict[str, Any], tag: str = "") -> tuple[Path, str]:
        variant, src = db_variant_for(self.cfg, q)
        dst = self.run_dir / "work" / f"{q['id']}{tag}.db"
        make_db_working_copy(src, dst)
        return dst, variant

    @staticmethod
    def _drop_work_db(path: Path) -> None:
        for p in (path, Path(str(path) + "-journal"), Path(str(path) + "-wal"), Path(str(path) + "-shm")):
            try:
                p.unlink()
            except FileNotFoundError:
                pass

    def _conv_id(self, qid: str | None = None) -> str:
        base = f"{self.cfg.run_id}:{self.cfg.mode}"
        return f"{base}:{qid}" if qid else base

    # -- modes ------------------------------------------------------------------
    def run(self) -> dict[str, Any]:
        """Run the sequence (honouring --resume) and write ``summary.json``."""
        self.prepare()
        interrupted = False
        try:
            if any(not self._is_done(q["id"]) for q in self.sequence):
                _ = self.provider  # fail early (auth/config) and before worker threads start
            if self.cfg.mode == "stateless":
                self._run_stateless()
            elif self.cfg.mode == "icl":
                self._run_icl()
            else:
                self._run_memory()
        except KeyboardInterrupt:
            interrupted = True
            log.warning("interrupted — writing summary for completed episodes")
            raise
        finally:
            summary = self.write_summary(interrupted=interrupted)
        return summary

    def _run_stateless(self) -> None:
        todo = [(i + 1, q) for i, q in enumerate(self.sequence) if not self._is_done(q["id"])]
        n = len(self.sequence)
        if self.cfg.parallel_questions <= 1 or len(todo) <= 1:
            for k, q in todo:
                self._stateless_one(q, k, n)
            return
        with ThreadPoolExecutor(max_workers=self.cfg.parallel_questions, thread_name_prefix="q") as pool:
            futures: dict[Future, str] = {pool.submit(self._stateless_one, q, k, n): q["id"] for k, q in todo}
            pending = set(futures)
            try:
                while pending:
                    done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                    for f in done:
                        f.result()
            except KeyboardInterrupt:
                for f in pending:
                    f.cancel()
                pool.shutdown(wait=False, cancel_futures=True)
                raise

    def _stateless_one(self, q: dict[str, Any], k: int, n: int) -> dict[str, Any]:
        work, variant = self._work_db(q)
        conv = self.provider.new_conversation(system_prompt("stateless"), tool_specs("stateless"), self._conv_id(q["id"]))
        try:
            with SqlTool(work, row_cap=self.cfg.row_cap, char_cap=self.cfg.char_cap, timeout_s=self.cfg.sql_timeout_s) as sql:
                ep = run_episode(conv, q, k, n, self.cfg, sql, None, db_variant=variant)
        finally:
            self._drop_work_db(work)
        self._save_episode(ep)
        return ep

    def _run_icl(self) -> None:
        start = self._resume_point()
        n = len(self.sequence)
        if start >= n:
            log.info("nothing to do (all %d episodes present)", n)
            return
        if start > 0:
            prev = self.sequence[start - 1]["id"]
            snap = snapshot_state_path(self.run_dir, prev)
            if not snap.exists():
                raise SystemExit(f"cannot resume icl: missing snapshot {snap}")
            conv = self.provider.restore_conversation(read_json(snap))
            log.info("resumed icl conversation from %s", snap)
        else:
            conv = self.provider.new_conversation(system_prompt("icl"), tool_specs("icl"), self._conv_id())
        for i in range(start, n):
            q = self.sequence[i]
            k = i + 1
            try:
                state_before = conv.export_state()
            except Exception as e:  # pragma: no cover - defensive
                log.warning("export_state before %s failed: %s", q["id"], e)
                state_before = None
            work, variant = self._work_db(q)
            try:
                with SqlTool(work, row_cap=self.cfg.row_cap, char_cap=self.cfg.char_cap, timeout_s=self.cfg.sql_timeout_s) as sql:
                    ep = run_episode(conv, q, k, n, self.cfg, sql, None, db_variant=variant)
            finally:
                self._drop_work_db(work)
            if ep.get("error") and state_before is not None:
                # drop the broken question from the conversation and carry on
                conv = self.provider.restore_conversation(state_before)
                ep["recovered_from_state_before"] = True
            try:
                write_json_atomic(snapshot_state_path(self.run_dir, q["id"]), conv.export_state())
            except Exception as e:  # pragma: no cover - defensive
                log.warning("snapshot after %s failed: %s", q["id"], e)
            self._save_episode(ep)

    def _run_memory(self) -> None:
        start = self._resume_point()
        n = len(self.sequence)
        if start >= n:
            log.info("nothing to do (all %d episodes present)", n)
            return
        bash = BashTool(self.memory_dir, timeout_s=self.cfg.bash_timeout_s).setup()
        self.cfg.sandboxed_bash = bash.sandboxed
        write_json_atomic(self.run_dir / "config.json", self.cfg.to_dict())
        if not bash.sandboxed:
            log.warning("bash tool is NOT sandboxed (not root or runuser/useradd unavailable)")
        if start > 0:
            prev = self.sequence[start - 1]["id"]
            snap = snapshot_memory_path(self.run_dir, prev)
            if not snap.exists():
                raise SystemExit(f"cannot resume memory: missing snapshot {snap}")
            clear_dir(self.memory_dir)
            untar_dir(snap, self.memory_dir)
            bash.setup()
            log.info("restored memory dir from %s", snap)
        for i in range(start, n):
            q = self.sequence[i]
            k = i + 1
            work, variant = self._work_db(q)
            conv = self.provider.new_conversation(system_prompt("memory"), tool_specs("memory"), self._conv_id(q["id"]))
            try:
                with SqlTool(work, row_cap=self.cfg.row_cap, char_cap=self.cfg.char_cap, timeout_s=self.cfg.sql_timeout_s) as sql:
                    ep = run_episode(conv, q, k, n, self.cfg, sql, bash, db_variant=variant)
            finally:
                self._drop_work_db(work)
            try:
                tar_dir(self.memory_dir, snapshot_memory_path(self.run_dir, q["id"]))
            except Exception as e:  # pragma: no cover - defensive
                log.warning("memory snapshot after %s failed: %s", q["id"], e)
            self._save_episode(ep)

    # -- summary ----------------------------------------------------------------
    def write_summary(self, *, interrupted: bool = False) -> dict[str, Any]:
        eps = [self.episodes[q["id"]] for q in self.sequence if q["id"] in self.episodes]
        summary = build_summary(self.cfg, eps, run_wall_s=time.monotonic() - self._t_start, interrupted=interrupted)
        write_json_atomic(self.run_dir / "summary.json", summary)
        return summary


def episode_row(ep: dict[str, Any]) -> dict[str, Any]:
    """Compact per-question row used in summary.json and analyze."""
    t = ep.get("totals") or {}
    mem = ep.get("memory") or {}
    return {
        "question_id": ep["question_id"],
        "index": ep.get("index"),
        "seq_index": ep.get("seq_index"),
        "db_variant": ep.get("db_variant"),
        "correct": bool(ep.get("correct")),
        "answer": ep.get("answer"),
        "gt": ep.get("gt"),
        "error": ep.get("error"),
        "stop_reason": ep.get("stop_reason"),
        "n_sql": ep.get("n_sql", 0),
        "slow_sql": len(ep.get("slow_sql") or []),
        "n_bash": ep.get("n_bash", 0),
        "n_turns": ep.get("n_turns", 0),
        "input": t.get("input", 0),
        "uncached": t.get("uncached", 0),
        "cached": t.get("cached", 0),
        "cache_write": t.get("cache_write", 0),
        "output": t.get("output", 0),
        "reasoning": t.get("reasoning", 0),
        "cost_usd": t.get("cost_usd", 0.0),
        "cost_known": t.get("cost_known", False),
        "wall_s": t.get("wall_s", 0.0),
        "context_tokens_end": ep.get("context_tokens_end"),
        "memory_bytes": mem.get("bytes"),
        "memory_files": mem.get("n_files"),
    }


def build_summary(cfg: RunConfig, episodes: list[dict[str, Any]], *, run_wall_s: float | None = None,
                  interrupted: bool = False) -> dict[str, Any]:
    rows = [episode_row(ep) for ep in episodes]
    drift = cfg.drift_after
    pre = [r for r in rows if drift is None or (r["index"] or 0) <= drift]
    post = [r for r in rows if drift is not None and (r["index"] or 0) > drift]

    def acc(rs: list[dict[str, Any]]) -> float | None:
        return round(sum(1 for r in rs if r["correct"]) / len(rs), 4) if rs else None

    keys = ("input", "uncached", "cached", "cache_write", "output", "reasoning", "n_sql", "slow_sql", "n_bash", "n_turns")
    totals: dict[str, Any] = {k: sum(int(r[k] or 0) for r in rows) for k in keys}
    totals["cost_usd"] = round(sum(float(r["cost_usd"] or 0.0) for r in rows), 6)
    totals["cost_known"] = all(r["cost_known"] for r in rows) if rows else False
    totals["wall_s"] = round(sum(float(r["wall_s"] or 0.0) for r in rows), 3)
    totals["errors"] = sum(1 for r in rows if r["error"])
    totals["no_answer"] = sum(1 for r in rows if r["answer"] is None and not r["error"])
    return {
        "run_id": cfg.run_id,
        "model": cfg.model,
        "mode": cfg.mode,
        "drift_after": drift,
        "n_questions": cfg.n_questions or len(cfg.question_ids),
        "n_done": len(rows),
        "n_correct": sum(1 for r in rows if r["correct"]),
        "accuracy": acc(rows),
        "accuracy_pre_drift": acc(pre),
        "accuracy_post_drift": acc(post),
        "totals": totals,
        "context_tokens_end": rows[-1]["context_tokens_end"] if rows else None,
        "run_wall_s": round(run_wall_s, 1) if run_wall_s is not None else None,
        "interrupted": interrupted,
        "updated_at": utc_now(),
        "per_question": rows,
    }


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


def replay(
    run_dir: str | Path,
    question_id: str,
    *,
    from_snapshot: bool = True,
    repeats: int = 1,
    memory_dir_override: str | Path | None = None,
    provider_factory: ProviderFactory = default_provider_factory,
) -> list[dict[str, Any]]:
    """Re-run one question of a finished run from its snapshot, ``repeats`` times independently.

    * icl: restores ``export_state()`` taken after the previous question (fresh conversation
      for the first question or without ``--from-snapshot``).
    * memory: extracts the memory tar.gz taken after the previous question into a fresh
      directory per repeat (``--memory-dir-override`` copies an edited directory instead).
    * stateless: plain re-run.

    Episodes go to ``<run>/replays/<qid>_r<K>.json.gz`` (+ ``_memory.tar.gz`` for memory; the
    live replay memory dirs are ``<run>/replay_memory/<qid>_r<K>/``).
    """
    run_dir = Path(run_dir)
    cfg = RunConfig.from_dict(read_json(run_dir / "config.json"))
    cfg.out = str(run_dir)
    questions = load_questions(cfg.questions)
    seq_ids = cfg.question_ids or [q["id"] for q in select_questions(questions, cfg.only)]
    if question_id.isdigit():
        question_id = f"q{int(question_id):02d}"
    if question_id not in seq_ids:
        raise SystemExit(f"{question_id} is not in the run sequence {seq_ids}")
    k = seq_ids.index(question_id) + 1
    n = len(seq_ids)
    q = next(x for x in questions if x["id"] == question_id)
    prev_id = seq_ids[k - 2] if k > 1 else None
    replays_dir = run_dir / "replays"
    replays_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "work").mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    for r in range(1, repeats + 1):
        tag = f"{question_id}_r{r}"
        provider = provider_factory(cfg.model, run_dir / "raw" / f"replay_{tag}.jsonl")
        variant, src = db_variant_for(cfg, q)
        work = make_db_working_copy(src, run_dir / "work" / f"replay_{tag}.db")
        bash: BashTool | None = None
        source = "fresh"
        try:
            if cfg.mode == "icl":
                snap = snapshot_state_path(run_dir, prev_id) if (from_snapshot and prev_id) else None
                if snap is not None:
                    if not snap.exists():
                        raise SystemExit(f"missing snapshot {snap}")
                    conv = provider.restore_conversation(read_json(snap))
                    source = str(snap)
                else:
                    conv = provider.new_conversation(system_prompt("icl"), tool_specs("icl"), f"{cfg.run_id}:replay:{tag}")
            elif cfg.mode == "memory":
                mem_root = run_dir / "replay_memory"
                mem_root.mkdir(parents=True, exist_ok=True)
                if os.geteuid() == 0:
                    os.chmod(mem_root, 0o711)
                mem_dir = mem_root / tag
                if mem_dir.exists():
                    shutil.rmtree(mem_dir)
                mem_dir.mkdir(parents=True)
                if memory_dir_override:
                    copy_tree_contents(Path(memory_dir_override), mem_dir)
                    source = f"override:{memory_dir_override}"
                elif from_snapshot and prev_id:
                    snap = snapshot_memory_path(run_dir, prev_id)
                    if not snap.exists():
                        raise SystemExit(f"missing snapshot {snap}")
                    untar_dir(snap, mem_dir)
                    source = str(snap)
                bash = BashTool(mem_dir, timeout_s=cfg.bash_timeout_s).setup()
                conv = provider.new_conversation(system_prompt("memory"), tool_specs("memory"), f"{cfg.run_id}:replay:{tag}")
            else:
                conv = provider.new_conversation(system_prompt("stateless"), tool_specs("stateless"), f"{cfg.run_id}:replay:{tag}")
            with SqlTool(work, row_cap=cfg.row_cap, char_cap=cfg.char_cap, timeout_s=cfg.sql_timeout_s) as sql:
                ep = run_episode(conv, q, k, n, cfg, sql, bash, db_variant=variant)
        finally:
            Runner._drop_work_db(work)
        ep["replay"] = {"repeat": r, "of": repeats, "from_snapshot": from_snapshot, "source": source,
                        "memory_dir_override": str(memory_dir_override) if memory_dir_override else None}
        if bash is not None:
            tar_dir(bash.memory_dir, replays_dir / f"{tag}_memory.tar.gz")
        write_json_atomic(replays_dir / f"{tag}.json.gz", ep)
        t = ep["totals"]
        log.info("replay %s: %s answer=%r gt=%r sql=%d bash=%d cost=%s wall=%.1fs%s", tag,
                 "✓" if ep["correct"] else ("ERR" if ep.get("error") else "✗"), ep.get("answer"), ep.get("gt"),
                 ep["n_sql"], ep["n_bash"], f"${t['cost_usd']:.4f}" if t["cost_known"] else "?", t["wall_s"],
                 f" error={ep['error']}" if ep.get("error") else "")
        out.append(ep)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m clrev.runner", description=__doc__.split("\n\n")[0])
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a question sequence in one mode")
    r.add_argument("--model", required=True, help=f"model key ({', '.join(MODELS)}) or any key known to make_provider")
    r.add_argument("--mode", required=True, choices=MODES)
    r.add_argument("--questions", required=True)
    r.add_argument("--db", required=True)
    r.add_argument("--db-v2", default=None)
    r.add_argument("--drift-after", type=int, default=None, help="swap to --db-v2 after this question (position in the full list)")
    r.add_argument("--out", required=True, help="runs/<run_id>")
    r.add_argument("--run-id", default=None, help="defaults to basename of --out")
    r.add_argument("--only", default=None, help="comma-separated question ids, e.g. q01,q05")
    r.add_argument("--max-turns", type=int, default=40)
    r.add_argument("--post-submit-turns", type=int, default=8, help="memory mode: extra tool turns after feedback")
    r.add_argument("--icl-post-submit-turns", type=int, default=0, help="icl: extra tool turns after feedback (default 0)")
    r.add_argument("--parallel-questions", type=int, default=1, help="stateless only")
    r.add_argument("--max-nudges", type=int, default=1, help="text-only turns before submit answered with a reminder")
    r.add_argument("--sql-timeout", type=float, default=SQL_TIMEOUT_S)
    r.add_argument("--bash-timeout", type=float, default=BASH_TIMEOUT_S)
    r.add_argument("--row-cap", type=int, default=ROW_CAP)
    r.add_argument("--char-cap", type=int, default=CHAR_CAP)
    r.add_argument("--memory-dir", default=None, help="memory mode: persistent dir (default <out>/memory)")
    r.add_argument("--resume", action="store_true", help="skip questions that already have episodes")
    r.add_argument("--retry-errors", action="store_true", help="with --resume: redo episodes that ended in error")

    rp = sub.add_parser("replay", help="re-run one question from a snapshot")
    rp.add_argument("--run", required=True)
    rp.add_argument("--question", required=True)
    rp.add_argument("--from-snapshot", action="store_true")
    rp.add_argument("--repeats", type=int, default=1)
    rp.add_argument("--memory-dir-override", default=None)
    return p


def config_from_args(a: argparse.Namespace) -> RunConfig:
    out = Path(a.out)
    return RunConfig(
        run_id=a.run_id or out.name,
        model=a.model,
        mode=a.mode,
        questions=str(Path(a.questions).resolve()),
        db=str(Path(a.db).resolve()),
        db_v2=str(Path(a.db_v2).resolve()) if a.db_v2 else None,
        drift_after=a.drift_after,
        out=str(out),
        only=[s for s in a.only.split(",") if s.strip()] if a.only else None,
        max_turns=a.max_turns,
        post_submit_turns=a.post_submit_turns,
        icl_post_submit_turns=a.icl_post_submit_turns,
        parallel_questions=a.parallel_questions,
        max_nudges=a.max_nudges,
        sql_timeout_s=a.sql_timeout,
        bash_timeout_s=a.bash_timeout,
        row_cap=a.row_cap,
        char_cap=a.char_cap,
        memory_dir=a.memory_dir,
        resume=a.resume,
        retry_errors=a.retry_errors,
    )


def main(argv: list[str] | None = None, provider_factory: ProviderFactory = default_provider_factory) -> int:
    """CLI entry point; ``provider_factory`` is injectable for tests."""
    args = build_parser().parse_args(argv)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    try:
        if args.cmd == "run":
            cfg = config_from_args(args)
            summary = Runner(cfg, provider_factory).run()
            log.info("done: %d/%d correct (acc=%s) cost=$%.4f wall=%.0fs → %s/summary.json",
                     summary["n_correct"], summary["n_done"], summary["accuracy"],
                     summary["totals"]["cost_usd"], summary["totals"]["wall_s"], cfg.out)
            return 0
        if args.cmd == "replay":
            eps = replay(args.run, args.question, from_snapshot=args.from_snapshot, repeats=args.repeats,
                         memory_dir_override=args.memory_dir_override, provider_factory=provider_factory)
            n_ok = sum(1 for e in eps if e["correct"])
            log.info("replay done: %d/%d correct", n_ok, len(eps))
            return 0
    except KeyboardInterrupt:
        log.warning("interrupted")
        return 130
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
