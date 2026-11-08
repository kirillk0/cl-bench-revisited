"""End-to-end tests of tools / grade / runner / analyze with a scripted FakeProvider.

The real providers live in ``clrev/providers`` (written separately).  If
``clrev.providers.base`` is not importable yet, a stub implementing the SPEC interface is
installed into ``sys.modules`` *for this test session only* — nothing is written into
``clrev/providers``.

Run: ``python -m pytest tests/test_runner_fake.py -q``
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time
import types
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Provider interface: real module or a stub matching SPEC.md
# ---------------------------------------------------------------------------


def _install_provider_stub() -> types.ModuleType:
    from dataclasses import dataclass, field

    mod = types.ModuleType("clrev.providers.base")

    @dataclass
    class ToolSpec:
        name: str
        description: str
        parameters: dict

    @dataclass
    class ToolCall:
        id: str
        name: str
        arguments: dict

    @dataclass
    class Usage:
        input_tokens: int = 0
        cached_input_tokens: int = 0
        cache_write_tokens: int = 0
        output_tokens: int = 0
        reasoning_tokens: int = 0
        cost_usd: float | None = None
        raw: dict = field(default_factory=dict)

    @dataclass
    class TurnResult:
        text: str | None
        tool_calls: list
        reasoning_summary: str | None
        usage: Usage
        stop_reason: str
        latency_s: float
        raw: dict = field(default_factory=dict)

    class Conversation:  # interface only
        def add_user(self, text: str) -> None: raise NotImplementedError
        def add_tool_results(self, results: list[tuple[str, str]]) -> None: raise NotImplementedError
        def step(self) -> "TurnResult": raise NotImplementedError
        def export_state(self) -> dict: raise NotImplementedError
        def history_view(self) -> list[dict]: raise NotImplementedError
        def context_tokens_estimate(self) -> int: raise NotImplementedError

    class Provider:
        key: str = ""
        model: str = ""
        def new_conversation(self, system_prompt: str, tools: list, conv_id: str) -> Conversation: raise NotImplementedError
        def restore_conversation(self, state: dict) -> Conversation: raise NotImplementedError

    for cls in (ToolSpec, ToolCall, Usage, TurnResult, Conversation, Provider):
        cls.__module__ = mod.__name__
        setattr(mod, cls.__name__, cls)
    pkg = sys.modules.get("clrev.providers")
    if pkg is None:
        pkg = types.ModuleType("clrev.providers")
        pkg.__path__ = []  # type: ignore[attr-defined]
        sys.modules["clrev.providers"] = pkg
    sys.modules["clrev.providers.base"] = mod
    setattr(pkg, "base", mod)
    return mod


try:
    import clrev.providers.base as base  # noqa: E402
    PROVIDER_STUBBED = False
except ImportError:
    base = _install_provider_stub()
    PROVIDER_STUBBED = True

from clrev import analyze, grade, runner, tools  # noqa: E402
from clrev.providers.base import Conversation, Provider, ToolCall, ToolSpec, TurnResult, Usage  # noqa: E402

IS_ROOT = os.geteuid() == 0
HAS_RUNUSER = shutil.which("runuser") is not None and shutil.which("useradd") is not None


# ---------------------------------------------------------------------------
# Fake provider
# ---------------------------------------------------------------------------

# Scripts keyed by a distinctive substring of the question text.
SCRIPTS: dict[str, dict[str, str]] = {
    "total amount": {"sql": "SELECT SUM(amount_minor) AS total FROM orders"},
    "day with the largest": {"sql": "SELECT day FROM orders ORDER BY amount_minor DESC LIMIT 1"},
    "rows in orders_v2": {"sql": "SELECT COUNT(*) AS n FROM orders_v2"},
}


def _first_cell(result_text: str) -> str:
    lines = result_text.splitlines()
    if len(lines) < 3 or lines[0].startswith("Error"):
        return "ERROR"
    return lines[2].split(" | ")[0].strip()


class FakeConversation(Conversation):
    """Scripted conversation: [bash cat notes] → run_sql → submit_answer → [bash append notes] → text."""

    def __init__(self, provider: "FakeProvider", system_prompt: str, tools_: list[ToolSpec], conv_id: str) -> None:
        self.provider = provider
        self.system_prompt = system_prompt
        self.tool_names = [t.name for t in tools_]
        self.conv_id = conv_id
        self.messages: list[dict[str, Any]] = []
        self.stage = 0
        self.key: str | None = None
        self.last_cell: str | None = None
        self.last_feedback: str | None = None
        self.last_prompt_tokens = 0
        self.pending: list[str] = []
        self.n_calls = 0

    # -- interface ----------------------------------------------------------
    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "text": text})
        if text.startswith("Question "):
            self.key = next((k for k in SCRIPTS if k in text), None)
            self.stage = 0
            self.last_cell = None
            self.last_feedback = None
        elif "submit_answer" in text:  # nudge
            self.stage = max(self.stage, 1)

    def add_tool_results(self, results: list[tuple[str, str]]) -> None:
        self.messages.append({"role": "tool", "tool_results": [{"id": cid, "output": out} for cid, out in results]})
        for cid, out in results:
            if cid.endswith(":sql"):
                self.last_cell = _first_cell(out)
            elif cid.endswith(":submit"):
                self.last_feedback = out

    def _usage(self) -> Usage:
        n = len(self.messages)
        self.last_prompt_tokens = 100 + 50 * n
        return Usage(input_tokens=self.last_prompt_tokens, cached_input_tokens=40 * max(0, n - 1),
                     cache_write_tokens=10, output_tokens=20, reasoning_tokens=5,
                     cost_usd=self.provider.cost_per_call, raw={"fake": True})

    def step(self) -> TurnResult:
        self.provider.n_steps += 1
        self.n_calls += 1
        self.provider.log({"conv": self.conv_id, "step": self.n_calls, "stage": self.stage, "key": self.key})
        if self.key in self.provider.raise_on and self.stage == 0:
            raise RuntimeError(f"fake provider failure on {self.key!r}")
        memory = "bash" in self.tool_names
        calls: list[ToolCall] = []
        text: str | None = None
        script = SCRIPTS.get(self.key or "", {"sql": "SELECT 1"})
        cid = f"c{self.n_calls}"
        if self.stage == 0 and self.provider.text_first and self.last_cell is None and not memory:
            text = "Let me think about this first."
            self.stage = 1  # a nudge (or anything) moves us on
        elif memory and self.stage == 0:
            calls = [ToolCall(f"{cid}:bash", "bash", {"command": "cat notes.md 2>/dev/null || echo NO_NOTES"})]
            self.stage = 1
        elif self.stage <= 1 and self.last_cell is None:
            calls = [ToolCall(f"{cid}:sql", "run_sql", {"sql": script["sql"]})]
            self.stage = 2
        elif self.stage <= 2 and self.last_feedback is None:
            answer = "999999" if self.key in self.provider.wrong_on else (self.last_cell or "ERROR")
            calls = [ToolCall(f"{cid}:submit", "submit_answer", {"answer": answer})]
            self.stage = 3
        elif memory and self.stage == 3:
            note = f"{self.key}: answer={self.last_cell} feedback={self.last_feedback}"
            calls = [ToolCall(f"{cid}:bash2", "bash", {"command": f"echo {json.dumps(note)} >> notes.md && wc -l notes.md"})]
            self.stage = 4
        else:
            text = "Done."
            self.stage = 5
        self.messages.append({"role": "assistant", "text": text, "reasoning_summary": f"stage {self.stage}",
                              "tool_calls": [dataclasses.asdict(c) for c in calls]})
        return TurnResult(text=text, tool_calls=calls, reasoning_summary=f"stage {self.stage}", usage=self._usage(),
                          stop_reason="tool_use" if calls else "end_turn", latency_s=0.01, raw={})

    def export_state(self) -> dict:
        return {"system_prompt": self.system_prompt, "tools": self.tool_names, "conv_id": self.conv_id,
                "messages": json.loads(json.dumps(self.messages)), "stage": self.stage, "key": self.key,
                "last_cell": self.last_cell, "last_feedback": self.last_feedback,
                "last_prompt_tokens": self.last_prompt_tokens, "n_calls": self.n_calls}

    def history_view(self) -> list[dict]:
        return json.loads(json.dumps(self.messages))

    def context_tokens_estimate(self) -> int:
        return self.last_prompt_tokens


class FakeProvider(Provider):
    """Deterministic provider; ``wrong_on`` / ``raise_on`` take script keys (see SCRIPTS)."""

    def __init__(self, raw_log_path: Path | None = None, *, wrong_on: set[str] | None = None,
                 raise_on: set[str] | None = None, text_first: bool = False, cost_per_call: float | None = 0.001) -> None:
        self.key = "fake"
        self.model = "fake-1"
        self.raw_log_path = Path(raw_log_path) if raw_log_path else None
        self.wrong_on = set(wrong_on or ())
        self.raise_on = set(raise_on or ())
        self.text_first = text_first
        self.cost_per_call = cost_per_call
        self.n_steps = 0

    def log(self, rec: dict[str, Any]) -> None:
        if self.raw_log_path:
            self.raw_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.raw_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")

    def new_conversation(self, system_prompt: str, tools_: list[ToolSpec], conv_id: str) -> FakeConversation:
        return FakeConversation(self, system_prompt, tools_, conv_id)

    def restore_conversation(self, state: dict) -> FakeConversation:
        conv = FakeConversation(self, state["system_prompt"], [ToolSpec(n, "", {}) for n in state["tools"]], state["conv_id"])
        conv.messages = json.loads(json.dumps(state["messages"]))
        conv.stage, conv.key = state["stage"], state["key"]
        conv.last_cell, conv.last_feedback = state["last_cell"], state["last_feedback"]
        conv.last_prompt_tokens, conv.n_calls = state["last_prompt_tokens"], state["n_calls"]
        return conv


def factory(**kw: Any):
    """Build a provider factory compatible with ``runner.main(..., provider_factory=...)``."""
    created: list[FakeProvider] = []

    def make(model_key: str, raw_log_path: Path) -> FakeProvider:
        p = FakeProvider(raw_log_path, **kw)
        created.append(p)
        return p

    make.created = created  # type: ignore[attr-defined]
    return make


# ---------------------------------------------------------------------------
# Fixtures: tiny DBs + 3 questions in a world-traversable temp dir
# ---------------------------------------------------------------------------

ROWS = [(1, 100, "2025-01-01"), (2, 250, "2025-01-02"), (3, 50, "2025-01-03")]
QUESTIONS = [
    {"id": "q01", "text": "What is the total amount_minor over all orders? Answer with an integer.",
     "answer": 400, "type": "int", "tolerance": 0, "answer_format": "integer", "knowledge_tags": ["sum"], "difficulty": 1},
    {"id": "q02", "text": "Which day with the largest single order? Answer as YYYY-MM-DD.",
     "answer": "2025-01-02", "type": "str", "tolerance": None, "knowledge_tags": ["order"], "difficulty": 1},
    {"id": "q03", "text": "How many rows in orders_v2? Answer with an integer.",
     "answer": 4, "type": "int", "tolerance": 0, "knowledge_tags": ["count"], "difficulty": 1},
]


@pytest.fixture(scope="module")
def ws() -> Path:
    """Temp workspace with data/{v1.db,v2.db,questions.json}; parents chmod 711 for memuser."""
    root = Path(tempfile.mkdtemp(prefix="clrev-test-", dir="/tmp"))
    os.chmod(root, 0o711)
    data = root / "data"
    data.mkdir()
    with sqlite3.connect(data / "v1.db") as c:
        c.execute("CREATE TABLE orders(id INTEGER PRIMARY KEY, amount_minor INTEGER, day TEXT)")
        c.executemany("INSERT INTO orders VALUES (?,?,?)", ROWS)
    with sqlite3.connect(data / "v2.db") as c:
        c.execute("CREATE TABLE orders_v2(id INTEGER PRIMARY KEY, amount_minor INTEGER, day TEXT)")
        c.executemany("INSERT INTO orders_v2 VALUES (?,?,?)", ROWS + [(4, 10, "2025-01-04")])
    (data / "questions.json").write_text(json.dumps(QUESTIONS, indent=1))
    (root / "runs").mkdir()
    os.chmod(root / "runs", 0o711)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def run_args(ws: Path, mode: str, out: str, *extra: str) -> list[str]:
    return ["run", "--model", "fake", "--mode", mode, "--questions", str(ws / "data/questions.json"),
            "--db", str(ws / "data/v1.db"), "--db-v2", str(ws / "data/v2.db"), "--drift-after", "2",
            "--out", str(ws / "runs" / out), *extra]


def load_eps(run_dir: Path) -> dict[str, dict[str, Any]]:
    return {p.name.split(".")[0]: runner.read_json(p) for p in sorted((run_dir / "episodes").glob("q*.json.gz"))}


# ---------------------------------------------------------------------------
# grade
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("answer,gt,ok", [
    ("1,234,567", {"answer": 1234567, "type": "int", "tolerance": 0}, True),
    ("€ 1 234 567.00", {"answer": 1234567, "type": "int", "tolerance": 0}, True),
    ("1.234.567,5", {"answer": 1234567.5, "type": "float", "tolerance": 0.01}, True),
    ("12.5%", {"answer": 12.49, "type": "float", "tolerance": 0.02}, True),
    ("≈ 42", {"answer": 42, "type": "int", "tolerance": 0}, True),
    ("1.234", {"answer": 1.234, "type": "float", "tolerance": 1e-9}, True),
    ("3,5", {"answer": 3.5, "type": "float", "tolerance": 0}, True),
    ("-3.5e3", {"answer": -3500, "type": "int", "tolerance": 0}, True),
    ("43", {"answer": 42, "type": "int", "tolerance": 0}, False),
    ("forty-two", {"answer": 42, "type": "int", "tolerance": 0}, False),
    ("", {"answer": 42, "type": "int", "tolerance": 0}, False),
    ("  2025-w23 ", {"answer": "2025-W23", "type": "str", "tolerance": None}, True),
    ("2025-W3", {"answer": "2025-W03", "type": "str", "tolerance": None}, True),
    ("2025-7", {"answer": "2025-07", "type": "str", "tolerance": None}, True),
    ("'Acme Corp'.", {"answer": "ACME corp", "type": "str", "tolerance": None}, True),
    ("INC-2025-0042", {"answer": "INC-2025-0043", "type": "str", "tolerance": None}, False),
    ("", {"answer": "x", "type": "str", "tolerance": None}, False),
])
def test_grade(answer: str, gt: dict[str, Any], ok: bool) -> None:
    res = grade.grade_answer(answer, gt)
    assert res.correct is ok, res
    fb = grade.feedback_text(res)
    assert fb == "CORRECT" if ok else fb == f"INCORRECT. Correct answer: {gt['answer']}"


def test_estimate_cost_tiers_and_convention() -> None:
    u = Usage(input_tokens=10_000, cached_input_tokens=8_000, cache_write_tokens=1_000, output_tokens=500, reasoning_tokens=100, cost_usd=None, raw={})
    cost = runner.estimate_cost("haiku", u)
    assert cost == pytest.approx((1_000 * 0.10 + 8_000 * 0.01 + 1_000 * 0.125 + 500 * 0.50) / 1e6)
    big = Usage(input_tokens=150_000, cached_input_tokens=0, cache_write_tokens=0, output_tokens=0, reasoning_tokens=0, cost_usd=None, raw={})
    assert runner.estimate_cost("haiku", big) == pytest.approx(150_000 * 0.50 / 1e6)
    # exclusive convention (cached > input) is detected
    excl = Usage(input_tokens=100, cached_input_tokens=5000, cache_write_tokens=0, output_tokens=0, reasoning_tokens=0, cost_usd=None, raw={})
    assert runner.split_input_tokens(excl) == (100, 5000, 0)
    assert runner.estimate_cost("unknown-model", u) is None


def test_question_message_and_prompts() -> None:
    msg = runner.question_message(QUESTIONS[0], 1, 3)
    assert msg.startswith("Question 1 of 3.\n\n")
    assert "Answer format:" not in msg  # format word already present in the text → not duplicated
    assert "chang" not in msg.lower()
    msg2 = runner.question_message({**QUESTIONS[1], "answer_format": "YYYY-Www"}, 2, 3)
    assert msg2.endswith("\n\nAnswer format: YYYY-Www")
    assert runner.system_prompt("icl").endswith(runner.ICL_ADDENDUM)
    assert runner.system_prompt("memory").endswith(runner.MEMORY_ADDENDUM)
    assert runner.system_prompt("stateless") == runner.SYSTEM_PROMPT_BASE
    assert [t.name for t in tools.tool_specs("memory")] == ["run_sql", "bash", "submit_answer"]
    assert [t.name for t in tools.tool_specs("icl")] == ["run_sql", "submit_answer"]


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------


def test_sql_tool_readonly_format_caps_timeout(ws: Path) -> None:
    work = tools.make_db_working_copy(ws / "data/v1.db", ws / "work_test.db")
    assert oct(work.stat().st_mode & 0o777) == "0o600"
    with tools.SqlTool(work, char_cap=120) as small:
        r = small.run("SELECT id, group_concat(hex(randomblob(60)), '') AS big FROM orders GROUP BY id")
        assert "[output truncated at 120 chars]" in r.text and r.error is None
    with tools.SqlTool(work, row_cap=2, char_cap=2000, timeout_s=0.3) as t:
        r = t.run("SELECT id, amount_minor, day FROM orders ORDER BY id")
        assert r.error is None and r.truncated and r.rows_returned == 2 and r.rows_total == 3
        lines = r.text.splitlines()
        assert lines[0].startswith("id | amount_minor | day") and lines[1].startswith("---+")
        assert "(showing first 2 of 3 rows" in lines[-1]
        r = t.run("SELECT SUM(amount_minor) AS total FROM orders")
        assert _first_cell(r.text) == "400" and "(1 row," in r.text and not r.slow
        for bad in ("INSERT INTO orders VALUES (9, 1, 'x')", "UPDATE orders SET amount_minor = 0",
                    "CREATE TABLE t(x)", "PRAGMA journal_mode = WAL", "ATTACH DATABASE '/tmp/x.db' AS y",
                    "SELECT 1; SELECT 2", "", "SELEC nonsense"):
            r = t.run(bad)
            assert r.error is not None and r.text.startswith("Error:"), (bad, r.text)
        assert t.run("SELECT COUNT(*) FROM orders").text.splitlines()[2].strip() == "3"  # nothing was written
        r = t.run("PRAGMA table_info(orders)")
        assert r.error is None and "amount_minor" in r.text and "(showing first 2 of 3 rows" in r.text
        r = t.run("SELECT name FROM sqlite_master WHERE type='table'")
        assert "orders" in r.text
        r = t.run("SELECT NULL AS a, 1.5 AS b, 'x\ny' AS c")
        assert "NULL" in r.text and "1.5" in r.text and "x\\ny" in r.text
        r = t.run("SELECT 'a' AS a FROM orders WHERE 0")
        assert "(no rows," in r.text
        t0 = time.monotonic()
        r = t.run("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c")
        assert r.error and "timed out" in r.text and time.monotonic() - t0 < 5
        assert r.ms >= 250
    assert len(t.calls) >= 10


@pytest.mark.skipif(not (IS_ROOT and HAS_RUNUSER), reason="bash sandbox needs root + runuser/useradd")
def test_bash_tool_sandbox(ws: Path) -> None:
    mem = ws / "mem_test"
    bt = tools.BashTool(mem, timeout_s=1.0, output_cap=500).setup()
    assert bt.sandboxed
    assert bt.run("whoami").text.strip() == tools.MEM_USER
    r = bt.run("echo hello > notes.md; cat notes.md; pwd; echo $HOME")
    assert r.exit_code == 0 and r.text.splitlines()[0] == "hello"
    assert r.text.splitlines()[1] == str(mem) == r.text.splitlines()[2]
    assert (mem / "notes.md").read_text() == "hello\n"
    assert (mem / "notes.md").stat().st_uid == __import__("pwd").getpwnam(tools.MEM_USER).pw_uid
    # DB working copy (600 root) is not readable from bash
    work = tools.make_db_working_copy(ws / "data/v1.db", ws / "work_bash.db")
    r = bt.run(f"cat {work} && echo READ_OK; sqlite3 {work} .tables 2>&1 || true")
    assert "READ_OK" not in r.text and ("Permission denied" in r.text or "unable to open" in r.text)
    assert r.exit_code not in (0, None) or "Permission denied" in r.text
    # timeout and output cap
    t0 = time.monotonic()
    r = bt.run("sleep 10; echo late")
    assert r.timed_out and "timed out" in r.text and time.monotonic() - t0 < 5 and "late" not in r.text
    r = bt.run("yes | head -c 100000")
    assert r.truncated and "[output truncated at 500 chars]" in r.text and len(r.text) < 700
    r = bt.run("exit 3")
    assert r.exit_code == 3 and "[exit code 3]" in r.text
    stats = bt.dir_stats()
    assert stats["n_files"] == 1 and stats["bytes"] == 6


# ---------------------------------------------------------------------------
# runner: all three modes
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def three_runs(ws: Path) -> dict[str, Path]:
    """stateless (wrong on q02, parallel), icl, memory — same questions, drift after q02."""
    runs = {}
    f_stateless = factory(wrong_on={"day with the largest"})
    assert runner.main(run_args(ws, "stateless", "fake_stateless", "--parallel-questions", "2"), provider_factory=f_stateless) == 0
    runs["stateless"] = ws / "runs/fake_stateless"
    f_icl = factory(text_first=True)
    assert runner.main(run_args(ws, "icl", "fake_icl"), provider_factory=f_icl) == 0
    runs["icl"] = ws / "runs/fake_icl"
    f_mem = factory()
    assert runner.main(run_args(ws, "memory", "fake_memory", "--post-submit-turns", "3"), provider_factory=f_mem) == 0
    runs["memory"] = ws / "runs/fake_memory"
    return runs


def test_stateless_run(three_runs: dict[str, Path]) -> None:
    rd = three_runs["stateless"]
    cfg = runner.read_json(rd / "config.json")
    assert cfg["mode"] == "stateless" and cfg["question_ids"] == ["q01", "q02", "q03"] and cfg["drift_after"] == 2
    eps = load_eps(rd)
    assert list(eps) == ["q01", "q02", "q03"]
    assert eps["q01"]["correct"] and eps["q01"]["answer"] == "400" and eps["q01"]["db_variant"] == "v1"
    assert not eps["q02"]["correct"] and eps["q02"]["answer"] == "999999" and eps["q02"]["feedback"] == "INCORRECT. Correct answer: 2025-01-02"
    assert eps["q03"]["correct"] and eps["q03"]["answer"] == "4" and eps["q03"]["db_variant"] == "v2"  # DB swapped silently
    for ep in eps.values():
        assert ep["n_sql"] == 1 and ep["n_bash"] == 0 and ep["n_turns"] == 2 and ep["stop_reason"] == "submitted"
        assert ep["error"] is None and ep["slow_sql"] == [] and ep["turns"][1]["tool_calls"][0]["name"] == "submit_answer"
        assert ep["history_view"][0]["role"] == "user" and ep["history_view"][0]["text"].startswith("Question ")
        assert ep["history_view"][-1]["role"] == "tool"  # feedback appended, then the episode ends
        assert ep["totals"]["cost_usd"] == pytest.approx(0.002) and ep["totals"]["cost_known"]
        assert ep["context_tokens_end"] == ep["turns"][-1]["usage"]["input_tokens"]
    summ = runner.read_json(rd / "summary.json")
    assert summ["n_correct"] == 2 and summ["accuracy"] == pytest.approx(2 / 3, abs=1e-3)
    assert summ["accuracy_pre_drift"] == pytest.approx(0.5) and summ["accuracy_post_drift"] == 1.0
    assert summ["totals"]["n_sql"] == 3 and summ["totals"]["cost_usd"] == pytest.approx(0.006)
    assert summ["totals"]["input"] == sum(r["input"] for r in summ["per_question"])
    assert (rd / "raw" / "fake_stateless.jsonl").exists()
    assert not list((rd / "work").glob("*.db"))  # working copies removed


def test_icl_run(three_runs: dict[str, Path]) -> None:
    rd = three_runs["icl"]
    eps = load_eps(rd)
    assert all(ep["correct"] for ep in eps.values()), {k: (e["answer"], e["gt"]) for k, e in eps.items()}
    # one conversation: history grows, each episode carries the full view
    assert len(eps["q01"]["history_view"]) < len(eps["q02"]["history_view"]) < len(eps["q03"]["history_view"])
    assert eps["q01"]["context_tokens_end"] < eps["q02"]["context_tokens_end"] < eps["q03"]["context_tokens_end"]
    # text-only first turn → one nudge, then SQL, then submit
    assert eps["q01"]["nudges"] == 1 and eps["q01"]["n_turns"] == 3 and eps["q01"]["turns"][0]["nudged"]
    hv = eps["q03"]["history_view"]
    # after the feedback tool result the very next message is the next question (no extra assistant turn)
    idx = [i for i, m in enumerate(hv) if m["role"] == "tool" and m["tool_results"][0]["output"].startswith(("CORRECT", "INCORRECT"))]
    assert len(idx) == 3
    assert hv[idx[0] + 1]["role"] == "user" and hv[idx[0] + 1]["text"].startswith("Question 2 of 3.")
    assert hv[idx[1] + 1]["role"] == "user" and hv[idx[1] + 1]["text"].startswith("Question 3 of 3.")
    assert eps["q03"]["db_variant"] == "v2"
    for qid in eps:
        snap = rd / "snapshots" / f"{qid}_state.json.gz"
        assert snap.exists()
    state = runner.read_json(rd / "snapshots/q01_state.json.gz")
    assert state["messages"][-1]["role"] == "tool" and state["messages"][-1]["tool_results"][0]["output"] == "CORRECT"


@pytest.mark.skipif(not (IS_ROOT and HAS_RUNUSER), reason="memory mode test needs the sandbox")
def test_memory_run(three_runs: dict[str, Path], ws: Path) -> None:
    rd = three_runs["memory"]
    cfg = runner.read_json(rd / "config.json")
    assert cfg["sandboxed_bash"] is True
    eps = load_eps(rd)
    assert all(ep["correct"] for ep in eps.values())
    for ep in eps.values():
        assert ep["n_bash"] == 2 and ep["n_sql"] == 1 and ep["n_post_submit_turns"] == 1 and ep["stop_reason"] == "done"
        assert ep["n_turns"] == 5  # bash, sql, submit, bash, text
        assert ep["memory"]["n_files"] == 1
    # notes persist across questions (fresh conversation each time)
    first_bash = eps["q01"]["turns"][0]["tool_calls"][0]
    assert first_bash["name"] == "bash" and "NO_NOTES" in first_bash["result_preview"]
    second = eps["q02"]["turns"][0]["tool_calls"][0]["result_preview"]
    assert "total amount: answer=400 feedback=CORRECT" in second and "day with" not in second
    third = eps["q03"]["turns"][0]["tool_calls"][0]["result_preview"]
    assert "day with the largest: answer=2025-01-02 feedback=CORRECT" in third
    assert eps["q01"]["memory"]["bytes"] < eps["q02"]["memory"]["bytes"] < eps["q03"]["memory"]["bytes"]
    # snapshots are tarballs of the memory dir after each question
    with tarfile.open(rd / "snapshots/q02_memory.tar.gz") as tar:
        names = [m.name for m in tar.getmembers() if m.isfile()]
        assert names == ["./notes.md"]
        content = tar.extractfile("./notes.md").read().decode()
        assert content.count("\n") == 2 and "rows in orders_v2" not in content
    notes = (rd / "memory" / "notes.md").read_text()
    assert notes.count("\n") == 3
    # hardening: data dir and run sub-dirs are hidden from memuser, memory dir belongs to memuser
    assert oct((ws / "data").stat().st_mode & 0o777) == "0o700"
    assert oct((ws / "data/v1.db").stat().st_mode & 0o777) == "0o600"
    assert oct((rd / "episodes").stat().st_mode & 0o777) == "0o700"
    bt = tools.BashTool(rd / "memory").setup()
    r = bt.run(f"ls {ws / 'data'} 2>&1; cat {rd / 'episodes/q01.json.gz'} 2>&1 | head -c 50; echo; cat {ws / 'data/questions.json'} 2>&1")
    assert "Permission denied" in r.text and '"answer"' not in r.text
    # every episode's history_view ends with the model's final text turn
    assert eps["q01"]["history_view"][-1]["role"] == "assistant" and eps["q01"]["history_view"][-1]["text"] == "Done."


def test_memory_post_submit_limit(ws: Path) -> None:
    """post-submit-turns=0 → the episode ends right after feedback even in memory mode."""
    f = factory()
    out = "fake_memory_ps0"
    assert runner.main(run_args(ws, "memory", out, "--only", "q01", "--post-submit-turns", "0"), provider_factory=f) == 0
    ep = load_eps(ws / "runs" / out)["q01"]
    assert ep["correct"] and ep["n_turns"] == 3 and ep["n_bash"] == 1 and ep["stop_reason"] == "submitted"
    assert ep["seq_index"] == 1 and ep["n_in_sequence"] == 1
    assert runner.read_json(ws / "runs" / out / "summary.json")["n_questions"] == 1


def test_icl_post_submit_turns_option(ws: Path) -> None:
    """--icl-post-submit-turns > 0 gives the model a turn after feedback; a text-only turn ends it."""
    out = "fake_icl_ps"
    assert runner.main(run_args(ws, "icl", out, "--only", "q01,q02", "--icl-post-submit-turns", "2"), provider_factory=factory()) == 0
    eps = load_eps(ws / "runs" / out)
    assert [e["seq_index"] for e in eps.values()] == [1, 2] and all(e["n_in_sequence"] == 2 for e in eps.values())
    for ep in eps.values():
        assert ep["correct"] and ep["n_turns"] == 3 and ep["stop_reason"] == "done" and ep["n_post_submit_turns"] == 0
        assert ep["turns"][-1]["phase"] == "post_submit" and ep["turns"][-1]["text"] == "Done."


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


def test_replay_icl_from_snapshot(three_runs: dict[str, Path]) -> None:
    rd = three_runs["icl"]
    f = factory()
    assert runner.main(["replay", "--run", str(rd), "--question", "q02", "--from-snapshot", "--repeats", "2"], provider_factory=f) == 0
    r1 = runner.read_json(rd / "replays/q02_r1.json.gz")
    r2 = runner.read_json(rd / "replays/q02_r2.json.gz")
    assert r1["correct"] and r2["correct"] and r1["replay"]["repeat"] == 1 and r2["replay"]["repeat"] == 2
    assert r1["replay"]["source"].endswith("q01_state.json.gz")
    # restored conversation contains q01 and then q02; repeats are independent (same length)
    texts = [m.get("text") or "" for m in r1["history_view"] if m["role"] == "user"]
    assert texts[0].startswith("Question 1 of 3.") and any(t.startswith("Question 2 of 3.") for t in texts)
    assert len(r1["history_view"]) == len(r2["history_view"])
    assert (rd / "raw/replay_q02_r1.jsonl").exists() and (rd / "raw/replay_q02_r2.jsonl").exists()
    # without --from-snapshot: fresh conversation containing only q02
    assert runner.main(["replay", "--run", str(rd), "--question", "q02", "--repeats", "1"], provider_factory=factory()) == 0
    fresh = runner.read_json(rd / "replays/q02_r1.json.gz")
    assert fresh["replay"]["source"] == "fresh" and fresh["history_view"][0]["text"].startswith("Question 2 of 3.")
    assert fresh["correct"]


@pytest.mark.skipif(not (IS_ROOT and HAS_RUNUSER), reason="memory replay needs the sandbox")
def test_replay_memory_snapshot_and_override(three_runs: dict[str, Path], ws: Path) -> None:
    rd = three_runs["memory"]
    assert runner.main(["replay", "--run", str(rd), "--question", "q03", "--from-snapshot"], provider_factory=factory()) == 0
    ep = runner.read_json(rd / "replays/q03_r1.json.gz")
    first = ep["turns"][0]["tool_calls"][0]["result_preview"]
    assert "total amount: answer=400" in first and "day with the largest" in first and "orders_v2" not in first
    assert ep["correct"] and ep["db_variant"] == "v2"
    assert (rd / "replays/q03_r1_memory.tar.gz").exists()
    # edited memory notes via --memory-dir-override
    override = ws / "edited_memory"
    override.mkdir(exist_ok=True)
    (override / "notes.md").write_text("EDITED NOTE: trust nobody\n")
    assert runner.main(["replay", "--run", str(rd), "--question", "q03", "--from-snapshot", "--repeats", "2",
                        "--memory-dir-override", str(override)], provider_factory=factory()) == 0
    for r in (1, 2):
        ep = runner.read_json(rd / f"replays/q03_r{r}.json.gz")
        first = ep["turns"][0]["tool_calls"][0]["result_preview"]
        assert "EDITED NOTE" in first and "total amount" not in first
        assert ep["replay"]["memory_dir_override"] == str(override)
    # the original memory dir / snapshots were not touched by replays
    assert (rd / "memory/notes.md").read_text().count("\n") == 3
    assert (override / "notes.md").read_text() == "EDITED NOTE: trust nobody\n"


# ---------------------------------------------------------------------------
# resilience: provider errors, resume, refuse-overwrite
# ---------------------------------------------------------------------------


def test_provider_error_icl_continues_and_resume_skips(ws: Path) -> None:
    f = factory(raise_on={"day with the largest"})
    out = "fake_icl_err"
    assert runner.main(run_args(ws, "icl", out), provider_factory=f) == 0
    eps = load_eps(ws / "runs" / out)
    assert eps["q01"]["correct"] and eps["q03"]["correct"]
    assert eps["q02"]["error"] and eps["q02"]["error"].startswith("RuntimeError") and eps["q02"]["correct"] is False
    assert eps["q02"]["stop_reason"] == "error" and eps["q02"].get("recovered_from_state_before")
    # the broken question was dropped from the conversation: q03's history has no "Question 2"
    texts = [m.get("text") or "" for m in eps["q03"]["history_view"] if m["role"] == "user"]
    assert not any(t.startswith("Question 2 of 3.") for t in texts)
    summ = runner.read_json(ws / "runs" / out / "summary.json")
    assert summ["totals"]["errors"] == 1 and summ["n_correct"] == 2
    # re-running without --resume refuses to overwrite
    with pytest.raises(SystemExit):
        runner.main(run_args(ws, "icl", out), provider_factory=factory())
    # --resume with everything done makes no provider calls
    f2 = factory()
    assert runner.main(run_args(ws, "icl", out, "--resume"), provider_factory=f2) == 0
    assert sum(p.n_steps for p in f2.created) == 0


def test_resume_partial_sequence_memory(ws: Path) -> None:
    """Delete the last memory episode and resume: memory dir is restored from the previous snapshot."""
    f = factory()
    out = "fake_memory_resume"
    assert runner.main(run_args(ws, "memory", out, "--post-submit-turns", "2"), provider_factory=f) == 0
    rd = ws / "runs" / out
    (rd / "episodes/q03.json.gz").unlink()
    (rd / "memory/notes.md").write_text("garbage left by an interrupted question\n")
    f2 = factory()
    assert runner.main(run_args(ws, "memory", out, "--resume", "--post-submit-turns", "2"), provider_factory=f2) == 0
    eps = load_eps(rd)
    assert set(eps) == {"q01", "q02", "q03"} and eps["q03"]["correct"]
    assert sum(p.n_steps for p in f2.created) == 5  # only q03 was re-run
    notes = (rd / "memory/notes.md").read_text()
    assert "garbage" not in notes and notes.count("\n") == 3


def test_resume_retry_errors_stateless(ws: Path) -> None:
    out = "fake_stateless_err"
    assert runner.main(run_args(ws, "stateless", out), provider_factory=factory(raise_on={"total amount"})) == 0
    eps = load_eps(ws / "runs" / out)
    assert eps["q01"]["error"] and eps["q02"]["correct"] and eps["q03"]["correct"]
    f2 = factory()
    assert runner.main(run_args(ws, "stateless", out, "--resume", "--retry-errors"), provider_factory=f2) == 0
    eps = load_eps(ws / "runs" / out)
    assert eps["q01"]["correct"] and eps["q01"]["error"] is None and sum(p.n_steps for p in f2.created) == 2


def test_max_turns_hard_stop(ws: Path) -> None:
    class LoopingProvider(FakeProvider):
        def new_conversation(self, system_prompt: str, tools_: list[ToolSpec], conv_id: str) -> FakeConversation:
            conv = super().new_conversation(system_prompt, tools_, conv_id)
            conv.step = lambda: TurnResult("…", [ToolCall("x", "run_sql", {"sql": "SELECT 1"})], None, conv._usage(), "tool_use", 0.0, {})  # type: ignore[method-assign]
            return conv

    out = "fake_loop"
    assert runner.main(run_args(ws, "stateless", out, "--only", "q01", "--max-turns", "4"),
                       provider_factory=lambda k, p: LoopingProvider(p)) == 0
    ep = load_eps(ws / "runs" / out)["q01"]
    assert ep["stop_reason"] == "max_turns" and ep["correct"] is False and ep["answer"] is None and ep["n_sql"] == 4
    summ = runner.read_json(ws / "runs" / out / "summary.json")
    assert summ["totals"]["no_answer"] == 1


def test_keyboard_interrupt_is_safe(ws: Path) -> None:
    """Ctrl-C during q02: exit code 130, summary written for q01 only, no partial q02 episode."""
    class InterruptingProvider(FakeProvider):
        def new_conversation(self, system_prompt: str, tools_: list[ToolSpec], conv_id: str) -> FakeConversation:
            conv = super().new_conversation(system_prompt, tools_, conv_id)
            orig = conv.step

            def step() -> TurnResult:
                if conv.key == "day with the largest":
                    raise KeyboardInterrupt
                return orig()

            conv.step = step  # type: ignore[method-assign]
            return conv

    out = "fake_interrupt"
    assert runner.main(run_args(ws, "icl", out), provider_factory=lambda k, p: InterruptingProvider(p)) == 130
    rd = ws / "runs" / out
    assert sorted(p.name for p in (rd / "episodes").iterdir()) == ["q01.json.gz"]
    summ = runner.read_json(rd / "summary.json")
    assert summ["interrupted"] is True and summ["n_done"] == 1 and summ["n_correct"] == 1
    assert not list(rd.glob("**/*.tmp*"))
    # resume continues from the q01 snapshot with a normal provider
    assert runner.main(run_args(ws, "icl", out, "--resume"), provider_factory=factory()) == 0
    eps = load_eps(rd)
    assert set(eps) == {"q01", "q02", "q03"} and all(e["correct"] for e in eps.values())
    assert runner.read_json(rd / "summary.json")["interrupted"] is False


def test_select_questions_only() -> None:
    qs = runner.load_questions.__wrapped__(QUESTIONS) if hasattr(runner.load_questions, "__wrapped__") else [
        {**q, "_index": i} for i, q in enumerate(QUESTIONS, 1)]
    assert [q["id"] for q in runner.select_questions(qs, ["q03,q01"])] == ["q03", "q01"]
    assert [q["id"] for q in runner.select_questions(qs, ["2"])] == ["q02"]
    with pytest.raises(SystemExit):
        runner.select_questions(qs, ["q99"])
    cfg = runner.RunConfig("r", "fake", "icl", "q.json", "v1.db", "v2.db", drift_after=2, out="runs/r")
    assert runner.db_variant_for(cfg, qs[1]) == ("v1", "v1.db") and runner.db_variant_for(cfg, qs[2]) == ("v2", "v2.db")
    cfg.db_v2 = None
    assert runner.db_variant_for(cfg, qs[2]) == ("v1", "v1.db")


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------


def test_analyze_report(three_runs: dict[str, Path], ws: Path) -> None:
    out_md = ws / "reports/fake.md"
    assert analyze.main(["--runs", *[str(p) for p in three_runs.values()], "--out", str(out_md)]) == 0
    rep = json.loads(out_md.with_suffix(".json").read_text())
    assert [r["label"] for r in rep["runs"]] == ["stateless", "icl", "memory"]
    classes = {pq["question_id"]: pq["class"] for pq in rep["per_question"]}
    assert classes == {"q01": "all-correct", "q02": "only-stateless-wrong", "q03": "all-correct"}
    assert rep["classes"]["counts"] == {"all-correct": 2, "only-stateless-wrong": 1}
    assert [pq["phase"] for pq in rep["per_question"]] == ["pre-drift", "pre-drift", "post-drift"]
    st = next(r for r in rep["runs"] if r["mode"] == "stateless")
    assert st["accuracy"] == pytest.approx(2 / 3) and st["totals"]["n_sql"] == 3 and st["totals"]["cost_known"]
    assert st["totals"]["uncached"] + st["totals"]["cached"] + st["totals"]["cache_write"] == st["totals"]["input"]
    icl = next(g for g in rep["icl_context_growth"])
    ctx = [p["context_tokens_end"] for p in icl["points"]]
    assert ctx == sorted(ctx) and len(ctx) == 3
    mem = next(g for g in rep["memory_growth"])
    assert all(p["n_bash"] == 2 for p in mem["points"])
    md = out_md.read_text()
    for heading in ("## Overview", "## Per-question correctness", "## Divergence classes", "## Cost structure by run",
                    "## ICL: context growth by question", "## Memory: memory dir size and bash calls by question"):
        assert heading in md
    assert "only-stateless-wrong" in md and "| q02 | pre-drift | 2025-01-02 | ✗ | ✓ | ✓ |" in md


def test_classify_patterns() -> None:
    from collections import OrderedDict
    assert analyze.classify(OrderedDict(a=True, b=True, c=True)) == "all-correct"
    assert analyze.classify(OrderedDict(a=False, b=False, c=None)) == "all-wrong"
    assert analyze.classify(OrderedDict(stateless=True, icl=False, memory=True)) == "only-icl-wrong"
    assert analyze.classify(OrderedDict(stateless=False, icl=False, memory=True)) == "only-memory-correct"
    assert analyze.classify(OrderedDict(a=True, b=False, c=False, d=True)) == "mixed:b+c-wrong"
