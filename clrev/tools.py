"""Tools exposed to the model: ``run_sql``, ``bash`` (memory mode) and ``submit_answer``.

* :class:`SqlTool` — read-only SQLite access (``PRAGMA query_only`` + authorizer that
  allows only SELECT/READ/functions/recursive CTEs and a whitelist of read-only PRAGMAs),
  statement timeout via progress handler, row/char caps, aligned text rendering, wall-clock
  timing and a ``slow`` flag (> ``SLOW_MS``).
* :class:`BashTool` — ``bash -lc`` as the unprivileged user ``memuser`` via ``runuser``,
  cwd = memory dir, ``HOME`` = memory dir, 30 s timeout, combined stdout+stderr capped.
* :func:`tool_specs` — provider-agnostic :class:`ToolSpec` list (identical for all models).

The ``submit_answer`` tool has no execution logic here: the runner grades it (see
``clrev.grade``) and returns the feedback text as the tool result.
"""

from __future__ import annotations

import os
import pwd
import select
import shutil
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clrev.providers.base import ToolSpec

__all__ = [
    "ROW_CAP",
    "CHAR_CAP",
    "SQL_TIMEOUT_S",
    "SLOW_MS",
    "BASH_TIMEOUT_S",
    "BASH_OUTPUT_CAP",
    "MEM_USER",
    "SqlResult",
    "SqlTool",
    "BashResult",
    "BashTool",
    "ensure_memuser",
    "make_db_working_copy",
    "tool_specs",
    "RUN_SQL_SPEC",
    "SUBMIT_ANSWER_SPEC",
    "BASH_SPEC",
]

ROW_CAP = 300
CHAR_CAP = 24_000
SQL_TIMEOUT_S = 30.0
SLOW_MS = 1000.0
COUNT_BUDGET_S = 2.0
CELL_CAP = 200

BASH_TIMEOUT_S = 30.0
BASH_OUTPUT_CAP = 16_000
MEM_USER = "memuser"

# ---------------------------------------------------------------------------
# Tool specifications (neutral, identical across models)
# ---------------------------------------------------------------------------

RUN_SQL_SPEC = ToolSpec(
    name="run_sql",
    description=(
        "Run one read-only SQL statement against the SQLite database and return the "
        "result as text (header plus up to 300 rows; longer results are truncated and "
        "marked). Use sqlite_master and PRAGMA table_info(...) to explore the schema."
    ),
    parameters={
        "type": "object",
        "properties": {"sql": {"type": "string", "description": "A single SQL statement."}},
        "required": ["sql"],
        "additionalProperties": False,
    },
)

SUBMIT_ANSWER_SPEC = ToolSpec(
    name="submit_answer",
    description=(
        "Submit the final answer to the current question. Pass only the value, in the "
        "format the question asks for. Returns whether the answer was correct."
    ),
    parameters={
        "type": "object",
        "properties": {"answer": {"type": "string", "description": "The final answer value."}},
        "required": ["answer"],
        "additionalProperties": False,
    },
)

BASH_SPEC = ToolSpec(
    name="bash",
    description=(
        "Run a bash command in the persistent working directory. Returns combined "
        "stdout and stderr (truncated at 16000 characters) and the exit code. "
        "Timeout 30 seconds."
    ),
    parameters={
        "type": "object",
        "properties": {"command": {"type": "string", "description": "The command to run with bash."}},
        "required": ["command"],
        "additionalProperties": False,
    },
)


def tool_specs(mode: str) -> list[ToolSpec]:
    """Return the tool list for a run mode (``bash`` only in ``memory`` mode)."""
    specs = [RUN_SQL_SPEC]
    if mode == "memory":
        specs.append(BASH_SPEC)
    specs.append(SUBMIT_ANSWER_SPEC)
    return specs


# ---------------------------------------------------------------------------
# SQL tool
# ---------------------------------------------------------------------------

# Read-only pragmas that take a table/index argument.
_PRAGMA_WITH_ARG = {
    "table_info", "table_xinfo", "index_list", "index_info", "index_xinfo",
    "foreign_key_list", "table_list",
}
# Read-only pragmas allowed without an assignment.
_PRAGMA_READ_ONLY = {
    "database_list", "collation_list", "function_list", "module_list", "pragma_list",
    "compile_options", "page_count", "page_size", "freelist_count", "schema_version",
    "user_version", "encoding", "journal_mode", "foreign_keys", "query_only",
    "application_id", "data_version", "integrity_check", "quick_check", "stats",
}

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}


def _authorizer(action: int, arg1: str | None, arg2: str | None, _db: str | None, _trigger: str | None) -> int:
    """SQLite authorizer: allow SELECT/READ/functions/recursive CTEs and read-only pragmas."""
    if action in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA:
        name = (arg1 or "").lower()
        if name in _PRAGMA_WITH_ARG:
            return sqlite3.SQLITE_OK
        if name in _PRAGMA_READ_ONLY and arg2 is None:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_DENY


@dataclass
class SqlResult:
    """Result of one ``run_sql`` call."""

    sql: str
    text: str
    ms: float
    rows_returned: int = 0
    rows_total: int | None = None  # None when unknown ("more")
    truncated: bool = False
    error: str | None = None

    @property
    def slow(self) -> bool:
        return self.ms > SLOW_MS

    def to_dict(self) -> dict[str, Any]:
        return {
            "sql": self.sql,
            "ms": round(self.ms, 1),
            "rows_returned": self.rows_returned,
            "rows_total": self.rows_total,
            "truncated": self.truncated,
            "error": self.error,
            "slow": self.slow,
        }


def _fmt_cell(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<blob {len(value)} bytes>"
    if isinstance(value, float):
        s = repr(value)
    else:
        s = str(value)
    s = s.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    if len(s) > CELL_CAP:
        s = s[: CELL_CAP - 1] + "…"
    return s


def render_table(headers: list[str], rows: list[tuple[Any, ...]]) -> str:
    """Render rows as an aligned text table (numbers right-aligned)."""
    cells = [[_fmt_cell(v) for v in row] for row in rows]
    numeric = []
    for ci in range(len(headers)):
        col = [row[ci] for row in rows] if rows else []
        numeric.append(bool(col) and all(v is None or isinstance(v, (int, float)) and not isinstance(v, bool) for v in col))
    widths = [len(h) for h in headers]
    for row in cells:
        for ci, c in enumerate(row):
            widths[ci] = max(widths[ci], len(c))
    def line(parts: list[str]) -> str:
        out = []
        for ci, p in enumerate(parts):
            out.append(p.rjust(widths[ci]) if numeric[ci] else p.ljust(widths[ci]))
        return " | ".join(out).rstrip()
    lines = [line(headers), "-+-".join("-" * w for w in widths)]
    lines.extend(line(row) for row in cells)
    return "\n".join(lines)


class SqlTool:
    """Read-only SQLite executor over a private working copy of the database.

    Use as a context manager or call :meth:`open` / :meth:`close` explicitly.
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        row_cap: int = ROW_CAP,
        char_cap: int = CHAR_CAP,
        timeout_s: float = SQL_TIMEOUT_S,
    ) -> None:
        self.db_path = Path(db_path)
        self.row_cap = row_cap
        self.char_cap = char_cap
        self.timeout_s = timeout_s
        self._conn: sqlite3.Connection | None = None
        self._deadline: float = 0.0
        self.calls: list[SqlResult] = []

    # -- lifecycle ---------------------------------------------------------
    def open(self) -> "SqlTool":
        if self._conn is None:
            uri = f"file:{self.db_path.as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, check_same_thread=False, isolation_level=None)
            conn.execute("PRAGMA query_only = 1")
            conn.set_progress_handler(self._progress, 2000)
            conn.set_authorizer(_authorizer)
            self._conn = conn
        return self

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "SqlTool":
        return self.open()

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _progress(self) -> int:
        return 1 if time.monotonic() > self._deadline else 0

    # -- execution ---------------------------------------------------------
    def run(self, sql: str) -> SqlResult:
        """Execute one statement; never raises for SQL errors (returns them as text)."""
        conn = self.open()._conn
        assert conn is not None
        sql_text = "" if sql is None else str(sql)
        t0 = time.monotonic()
        self._deadline = t0 + self.timeout_s
        try:
            if not sql_text.strip():
                raise sqlite3.ProgrammingError("empty SQL statement")
            cur = conn.execute(sql_text)
            headers = [d[0] for d in (cur.description or [])]
            rows = cur.fetchmany(self.row_cap + 1) if cur.description else []
            truncated = len(rows) > self.row_cap
            rows = rows[: self.row_cap]
            ms = (time.monotonic() - t0) * 1000.0
            total: int | None = len(rows)
            if truncated:
                total = self._count_total(sql_text, cur, len(rows) + 1)
            res = SqlResult(sql=sql_text, text="", ms=ms, rows_returned=len(rows), rows_total=total, truncated=truncated)
            res.text = self._render(headers, rows, res)
        except sqlite3.OperationalError as e:
            ms = (time.monotonic() - t0) * 1000.0
            msg = str(e)
            if "interrupted" in msg.lower() and ms >= self.timeout_s * 1000.0 * 0.9:
                msg = f"statement timed out after {self.timeout_s:g} s and was cancelled"
            res = SqlResult(sql=sql_text, text=f"Error: {msg}\n({ms:.0f} ms)", ms=ms, error=msg)
        except (sqlite3.Error, ValueError) as e:  # ProgrammingError (multi-statement), DatabaseError, …
            ms = (time.monotonic() - t0) * 1000.0
            msg = str(e)
            res = SqlResult(sql=sql_text, text=f"Error: {msg}\n({ms:.0f} ms)", ms=ms, error=msg)
        self.calls.append(res)
        return res

    def _count_total(self, sql_text: str, cur: sqlite3.Cursor, seen: int) -> int | None:
        """Total row count when cheap (wrapped COUNT(*), else draining the cursor within a
        small time budget); None means "more"."""
        conn = self._conn
        assert conn is not None
        inner = sql_text.strip().rstrip(";").strip()
        saved = self._deadline
        self._deadline = time.monotonic() + COUNT_BUDGET_S
        try:
            if inner.lower().startswith(("select", "with")):
                try:
                    row = conn.execute(f"SELECT COUNT(*) FROM ({inner}) AS _clrev_sub").fetchone()
                    if row:
                        return int(row[0])
                except sqlite3.Error:
                    pass
            total = seen
            try:
                while True:
                    chunk = cur.fetchmany(5000)
                    if not chunk:
                        return total
                    total += len(chunk)
            except sqlite3.Error:
                return None
        finally:
            self._deadline = saved

    def _render(self, headers: list[str], rows: list[tuple[Any, ...]], res: SqlResult) -> str:
        body = render_table(headers, rows) if headers else "(statement returned no columns)"
        if len(body) > self.char_cap:
            body = body[: self.char_cap] + f"\n... [output truncated at {self.char_cap} chars]"
        if res.truncated:
            total = str(res.rows_total) if res.rows_total is not None else "more"
            footer = f"(showing first {res.rows_returned} of {total} rows, {res.ms:.0f} ms)"
        elif res.rows_returned == 0:
            footer = f"(no rows, {res.ms:.0f} ms)"
        else:
            footer = f"({res.rows_returned} row{'s' if res.rows_returned != 1 else ''}, {res.ms:.0f} ms)"
        return f"{body}\n{footer}"


def make_db_working_copy(src: str | Path, dst: str | Path) -> Path:
    """Copy a SQLite DB into a private working copy (consistent even if src is WAL) and chmod 600."""
    src_p, dst_p = Path(src), Path(dst)
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    for stale in (dst_p, Path(str(dst_p) + "-wal"), Path(str(dst_p) + "-shm"), Path(str(dst_p) + "-journal")):
        if stale.exists():
            stale.unlink()
    with sqlite3.connect(f"file:{src_p.as_posix()}?mode=ro", uri=True) as s, sqlite3.connect(dst_p) as d:
        s.backup(d)
        d.execute("PRAGMA journal_mode = DELETE")
    os.chmod(dst_p, 0o600)
    return dst_p


# ---------------------------------------------------------------------------
# Bash tool (memory mode)
# ---------------------------------------------------------------------------


@dataclass
class BashResult:
    """Result of one ``bash`` call."""

    command: str
    text: str
    exit_code: int | None
    ms: float
    timed_out: bool = False
    truncated: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "ms": round(self.ms, 1),
            "timed_out": self.timed_out,
            "truncated": self.truncated,
            "error": self.error,
        }


def ensure_memuser(user: str = MEM_USER) -> bool:
    """Create the unprivileged sandbox user if missing. Returns True if usable.

    Requires root; returns False (no sandboxing) otherwise.
    """
    if os.geteuid() != 0:
        return False
    try:
        pwd.getpwnam(user)
        return True
    except KeyError:
        pass
    if shutil.which("useradd") is None:
        return False
    proc = subprocess.run(
        ["useradd", "--system", "--no-create-home", "--shell", "/bin/bash", user],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return False
    try:
        pwd.getpwnam(user)
        return True
    except KeyError:
        return False


def chown_tree(path: str | Path, user: str) -> None:
    """Recursively chown ``path`` to ``user`` (no-op when not root)."""
    if os.geteuid() != 0:
        return
    pw = pwd.getpwnam(user)
    for root, dirs, files in os.walk(path):
        os.chown(root, pw.pw_uid, pw.pw_gid)
        for name in dirs + files:
            p = os.path.join(root, name)
            if not os.path.islink(p):
                os.chown(p, pw.pw_uid, pw.pw_gid)
    os.chown(path, pw.pw_uid, pw.pw_gid)


class BashTool:
    """``bash -lc`` in a persistent memory directory as ``memuser``.

    When not running as root (or ``runuser`` is unavailable) the command runs as the current
    user with ``sandboxed=False`` — tests may still exercise the protocol, but the runner
    records this in the config.
    """

    def __init__(
        self,
        memory_dir: str | Path,
        *,
        user: str = MEM_USER,
        timeout_s: float = BASH_TIMEOUT_S,
        output_cap: int = BASH_OUTPUT_CAP,
    ) -> None:
        self.memory_dir = Path(memory_dir)
        self.user = user
        self.timeout_s = timeout_s
        self.output_cap = output_cap
        self.calls: list[BashResult] = []
        self.sandboxed = False

    def setup(self) -> "BashTool":
        """Create the memory dir, ensure the sandbox user exists and owns it."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        (self.memory_dir / ".tmp").mkdir(exist_ok=True)  # private TMPDIR for the sandboxed shell
        self.sandboxed = bool(shutil.which("runuser")) and ensure_memuser(self.user)
        if self.sandboxed:
            chown_tree(self.memory_dir, self.user)
            os.chmod(self.memory_dir, 0o700)
            # Keep the shared /tmp out of reach of the sandbox user (other processes in the
            # container may drop artefacts there). Best effort; mount namespaces are unavailable.
            try:
                if os.geteuid() == 0:
                    os.chmod("/tmp", 0o1770)
            except OSError:
                pass
        return self

    def _argv(self, command: str) -> list[str]:
        env_cmd = [
            "/usr/bin/env", "-i",
            f"HOME={self.memory_dir}",
            f"TMPDIR={self.memory_dir}/.tmp",
            "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG=C.UTF-8", "LC_ALL=C.UTF-8", "TERM=dumb",
            f"USER={self.user if self.sandboxed else os.environ.get('USER', 'user')}",
            f"LOGNAME={self.user if self.sandboxed else os.environ.get('USER', 'user')}",
            "/bin/bash", "-lc", command,
        ]
        if self.sandboxed:
            return ["runuser", "-u", self.user, "--", *env_cmd]
        return env_cmd

    def run(self, command: str) -> BashResult:
        """Run ``command``; returns combined output, exit code, timing. Never raises."""
        cmd = "" if command is None else str(command)
        t0 = time.monotonic()
        deadline = t0 + self.timeout_s
        chunks: list[bytes] = []
        size = 0
        timed_out = False
        truncated = False
        error: str | None = None
        exit_code: int | None = None
        try:
            proc = subprocess.Popen(
                self._argv(cmd),
                cwd=str(self.memory_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as e:
            ms = (time.monotonic() - t0) * 1000.0
            res = BashResult(cmd, f"Error: could not start bash: {e}", None, ms, error=str(e))
            self.calls.append(res)
            return res
        assert proc.stdout is not None
        fd = proc.stdout.fileno()
        hard_cap = self.output_cap * 4  # bytes; generous for multibyte text
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                ready, _, _ = select.select([fd], [], [], min(remaining, 0.5))
                if not ready:
                    continue
                data = os.read(fd, 65536)
                if not data:
                    break
                if size < hard_cap:
                    chunks.append(data)
                    size += len(data)
                else:
                    truncated = True
                    break
        finally:
            if proc.poll() is None:
                self._kill(proc)
            try:
                exit_code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                exit_code = None
            proc.stdout.close()
        ms = (time.monotonic() - t0) * 1000.0
        text = b"".join(chunks).decode("utf-8", errors="replace")
        if len(text) > self.output_cap:
            text = text[: self.output_cap]
            truncated = True
        notes = []
        if truncated:
            notes.append(f"[output truncated at {self.output_cap} chars]")
        if timed_out:
            notes.append(f"[timed out after {self.timeout_s:g} s; process killed]")
        elif exit_code not in (0, None):
            notes.append(f"[exit code {exit_code}]")
        elif exit_code is None:
            notes.append("[process killed]")
        out = text.rstrip("\n")
        if notes:
            out = (out + "\n" if out else "") + "\n".join(notes)
        if not out:
            out = "[no output, exit code 0]"
        res = BashResult(cmd, out, exit_code, ms, timed_out=timed_out, truncated=truncated, error=error)
        self.calls.append(res)
        return res

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        import signal

        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass

    # -- memory dir helpers -------------------------------------------------
    def dir_stats(self) -> dict[str, Any]:
        """Size in bytes, file count and a capped listing of the memory dir."""
        total = 0
        files: list[dict[str, Any]] = []
        for root, _dirs, names in os.walk(self.memory_dir):
            for name in names:
                p = Path(root) / name
                try:
                    st = p.lstat()
                except OSError:
                    continue
                total += st.st_size
                if len(files) < 200:
                    files.append({"path": p.relative_to(self.memory_dir).as_posix(), "bytes": st.st_size})
        return {"bytes": total, "n_files": sum(1 for _ in _iter_files(self.memory_dir)), "files": files}


def _iter_files(root: Path):
    for r, _d, names in os.walk(root):
        for n in names:
            yield Path(r) / n
