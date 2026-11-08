"""Small shared helpers for the dataset generator (time formatting, RNG, containers)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np
import pandas as pd

SEED = 20261108
YEAR = 2025
T0 = datetime(YEAR, 1, 1)                 # start of the data year (UTC)
T1 = datetime(YEAR + 1, 1, 1)             # exclusive end
N_DAYS = (T1 - T0).days                   # 365
TS_FMT = "%Y-%m-%d %H:%M:%S"


def ts(dt: datetime) -> str:
    """Format a datetime as the canonical 'YYYY-MM-DD HH:MM:SS' UTC text."""
    return dt.strftime(TS_FMT)


def parse_ts(s: str) -> datetime:
    """Inverse of :func:`ts`."""
    return datetime.strptime(s, TS_FMT)


def sec(dt: datetime) -> int:
    """Seconds since T0 (the generator's internal clock)."""
    return int((dt - T0).total_seconds())


def secs_to_ts(secs: np.ndarray) -> np.ndarray:
    """Vectorised seconds-since-T0 -> 'YYYY-MM-DD HH:MM:SS' strings."""
    base = np.datetime64(T0, "s")
    arr = (base + secs.astype("int64").astype("timedelta64[s]")).astype("datetime64[s]").astype(str)
    return np.char.replace(arr, "T", " ")


def day_of(secs: np.ndarray) -> np.ndarray:
    """Vectorised seconds-since-T0 -> day index (0..N_DAYS-1 inside the year)."""
    return (secs // 86400).astype(np.int64)


def iso_week_label(d: date) -> str:
    """'YYYY-Www' ISO-8601 week label of a date."""
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def rng_for(name: str) -> np.random.Generator:
    """Independent, reproducible RNG stream per generation stage.

    Using a named sub-stream keeps every stage deterministic even if another
    stage changes the number of random draws it consumes.
    """
    ss = np.random.SeedSequence([SEED, abs(hash_str(name)) % (2**31)])
    return np.random.default_rng(ss)


def hash_str(s: str) -> int:
    """Deterministic (process independent) string hash."""
    h = 1469598103934665603
    for ch in s.encode():
        h = ((h ^ ch) * 1099511628211) % (2**64)
    return h


@dataclass
class Dataset:
    """All generated tables as pandas DataFrames keyed by table name, plus look-ups."""

    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)   # ids/dates of planted phenomena, counts, etc.

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.tables[name]

    def __setitem__(self, name: str, df: pd.DataFrame) -> None:
        self.tables[name] = df
