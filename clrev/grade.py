"""Answer grading for the memory-modes experiment (CL-Bench style).

Ground truth (GT) records carry ``answer``, ``type`` (``int`` | ``float`` | ``str``) and
``tolerance`` (absolute, numbers only).  Rules:

* ``int`` / ``float`` — the submitted text is parsed as a number after stripping
  currency symbols, thousands separators, percent signs and surrounding noise;
  correct iff ``abs(answer - gt) <= tolerance`` (default tolerance 0 for ``int``,
  1e-6 for ``float``).
* ``str`` — case- and whitespace-insensitive exact match after light normalisation
  (quotes/trailing punctuation stripped).  ``YYYY-Www`` and ``YYYY-MM`` values are
  plain strings; ISO week numbers are zero-padded before comparison so ``2025-W3``
  equals ``2025-W03``.

No GT SQL is ever revealed in feedback.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

__all__ = ["GradeResult", "grade_answer", "feedback_text", "parse_number", "normalize_str"]

_CURRENCY_RE = re.compile(r"[€$£¥₽₴₩₹₺₣฿]|\b(?:EUR|USD|GBP|JPY|KWD|CHF|RUB|UAH|PLN|CZK|SEK|NOK|DKK|HUF|RON|BGN|TRY|AUD|CAD|NZD|CNY|INR|BRL|MXN|ZAR|SGD|HKD|KRW)\b", re.I)
_NOISE_PREFIX_RE = re.compile(r"^[\s≈~=:\"'`*]+|[\s\"'`*.;,]+$")
_THOUSANDS_COMMA_RE = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")
_THOUSANDS_DOT_RE = re.compile(r"^-?\d{1,3}(?:(?:\.\d{3}){2,}|(?:\.\d{3})+,\d+)$")
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_ISO_WEEK_RE = re.compile(r"^(\d{4})-?w(\d{1,2})$")
_ISO_MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})$")


@dataclass(frozen=True)
class GradeResult:
    """Outcome of grading one submitted answer."""

    correct: bool
    submitted: str
    normalized: str | None
    gt: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "correct": self.correct,
            "submitted": self.submitted,
            "normalized": self.normalized,
            "gt": self.gt,
            "reason": self.reason,
        }


def parse_number(text: str) -> float | None:
    """Parse a free-form numeric answer.

    Handles ``1,234,567``, ``1.234.567,89``, ``1 234 567``, ``€ 12,345.67``, ``12.5%``,
    ``≈ 42``, ``1_000``, ``-3.5e3`` and plain numbers.  Returns ``None`` when the text does
    not look like a single number.
    """
    if text is None:
        return None
    s = str(text).strip()
    s = _CURRENCY_RE.sub("", s)
    s = _NOISE_PREFIX_RE.sub("", s)
    s = s.replace("%", "").replace("\u2212", "-").strip().lstrip("+")
    # apostrophe / underscore / space / nbsp thousands separators
    s = re.sub(r"(?<=\d)[\s'\u00a0\u202f_](?=\d{3}\b)", "", s)
    s = s.strip()
    if not s:
        return None
    if _THOUSANDS_COMMA_RE.match(s):
        s = s.replace(",", "")
    elif _THOUSANDS_DOT_RE.match(s):
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." in s:
        # mixed separators: the last one is the decimal mark
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # single comma: decimal comma ("3,5") unless it is clearly a thousands group
        s = s.replace(",", ".") if s.count(",") == 1 else s.replace(",", "")
    m = _NUMBER_RE.fullmatch(s)
    if not m:
        return None
    try:
        value = float(s)
    except ValueError:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def normalize_str(text: str) -> str:
    """Case/whitespace-insensitive normalisation for string answers."""
    s = str(text).strip()
    s = _NOISE_PREFIX_RE.sub("", s)
    s = re.sub(r"\s+", "", s).lower()
    m = _ISO_WEEK_RE.match(s)
    if m:
        return f"{m.group(1)}-w{int(m.group(2)):02d}"
    m = _ISO_MONTH_RE.match(s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    return s


def _default_tolerance(gt_type: str) -> float:
    return 1e-6 if gt_type == "float" else 0.0


def grade_answer(answer: Any, gt: dict[str, Any]) -> GradeResult:
    """Grade ``answer`` against a GT record ``{answer, type, tolerance}``."""
    gt_type = str(gt.get("type", "str")).lower()
    gt_answer = gt.get("answer")
    gt_text = str(gt_answer)
    submitted = "" if answer is None else str(answer)

    if gt_type in ("int", "float", "number"):
        tol = gt.get("tolerance")
        tol = _default_tolerance(gt_type) if tol is None else float(tol)
        got = parse_number(submitted)
        want = parse_number(gt_text) if not isinstance(gt_answer, (int, float)) else float(gt_answer)
        if want is None:
            return GradeResult(False, submitted, None, gt_text, "gt-not-numeric")
        if got is None:
            return GradeResult(False, submitted, None, gt_text, "not-a-number")
        ok = abs(got - want) <= tol + 1e-12
        return GradeResult(ok, submitted, repr(got), gt_text, "numeric-match" if ok else "numeric-mismatch")

    norm_got = normalize_str(submitted)
    norm_want = normalize_str(gt_text)
    ok = norm_got == norm_want and norm_got != ""
    return GradeResult(ok, submitted, norm_got, gt_text, "str-match" if ok else "str-mismatch")


def feedback_text(result: GradeResult) -> str:
    """CL-Bench style feedback returned by ``submit_answer``."""
    if result.correct:
        return "CORRECT"
    return f"INCORRECT. Correct answer: {result.gt}"
