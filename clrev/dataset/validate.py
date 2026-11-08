"""Validation of the generated artefacts.

(a) run every gt_sql on its database and record the answer + wall time;
(b) recompute a subset of answers independently with pandas on the in-memory frames;
(c) run the 'naive' variants and check that they differ from the ground truth;
plus a few structural sanity checks of the planted stories.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .common import Dataset, iso_week_label, parse_ts
from .facts import merchants_in_group
from .questions import Question
from .reference import RC_V1, RC_V2_CHANGES
from .stories import BAD_DEPLOY, MOVE, OPERATOR_STORY, OUTAGE, RC_V2_FROM, SEASONAL_GROUP


def _scalar(con: sqlite3.Connection, sql: str):
    rows = con.execute(sql).fetchall()
    if not rows or rows[0][0] is None:
        return None
    v = rows[0][0]
    return v


def run_ground_truth(questions: list[Question], cons: dict[str, sqlite3.Connection]) -> list[dict]:
    """Execute gt_sql for every question, store the answer and return timing records."""
    out = []
    for q in questions:
        con = cons[q.db]
        t0 = time.perf_counter()
        val = _scalar(con, q.gt_sql)
        ms = (time.perf_counter() - t0) * 1000
        if q.type == "int":
            val = int(round(val))
        elif q.type == "float":
            val = float(val)
        else:
            val = str(val)
        q.answer = val
        out.append(dict(id=q.id, db=q.db, ms=round(ms, 1), answer=val))
    return out


def matches(q: Question, value) -> bool:
    """Grading rule of the SPEC: abs tolerance for numbers, case/space-insensitive for strings."""
    if value is None:
        return False
    if q.type in ("int", "float"):
        try:
            return abs(float(value) - float(q.answer)) <= q.tolerance
        except (TypeError, ValueError):
            return False
    return str(value).strip().lower().replace(" ", "") == str(q.answer).strip().lower().replace(" ", "")


def run_naive(questions: list[Question], cons: dict[str, sqlite3.Connection]) -> list[dict]:
    """Run every naive variant; a variant 'distinguishes' if it would be graded INCORRECT."""
    out = []
    for q in questions:
        for label, sql in q.naive.items():
            try:
                val = _scalar(cons[q.db], sql)
            except sqlite3.Error as e:            # pragma: no cover - would be a bug in the naive SQL
                val = f"SQL error: {e}"
            out.append(dict(id=q.id, label=label, naive=val, correct=q.answer, distinguishes=not matches(q, val)))
    return out


# ------------------------------------------------------------------ (b) independent re-computation with pandas
def _merchant_at_txn(ds: Dataset, txn: pd.DataFrame) -> pd.Series:
    """merchant_id valid at each transaction's timestamp (pandas interval join on the assignment table)."""
    ta = ds["terminal_assignment"]
    m = txn[["txn_id", "terminal_id", "ts_utc"]].merge(ta, on="terminal_id")
    m = m[(m.ts_utc >= m.valid_from) & (m.valid_to.isna() | (m.ts_utc < m.valid_to))]
    assert m.txn_id.is_unique and len(m) == len(txn), "assignment intervals must cover every txn exactly once"
    return m.set_index("txn_id").merchant_id.reindex(txn.txn_id).to_numpy()


def _eur(ds: Dataset, df: pd.DataFrame, date_col: str) -> np.ndarray:
    cur = ds["dim_currency"].set_index("currency_id").exponent
    fx = ds["fx_rate"].rename(columns={"rate_date": "_d"})
    m = df.assign(_d=df[date_col].str[:10]).merge(fx, on=["currency_id", "_d"], how="left")
    assert m.rate_to_eur.notna().all()
    return (m.amount_minor.to_numpy() / 10.0 ** cur.loc[m.currency_id].to_numpy()) * m.rate_to_eur.to_numpy()


def _rc_flags(ds: Dataset, codes: pd.Series, ts: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """(is_decline, is_timeout) from the static dictionaries, version by timestamp (v1 database semantics)."""
    v2 = {**RC_V1, **RC_V2_CHANGES}
    dec = np.array([(v2 if t >= RC_V2_FROM else RC_V1)[c][1] for c, t in zip(codes, ts)])
    to = np.array([(v2 if t >= RC_V2_FROM else RC_V1)[c][2] for c, t in zip(codes, ts)])
    return dec, to


def independent_checks(ds: Dataset, questions: list[Question]) -> list[dict]:
    """Recompute q01, q02, q03, q09, q10, q11, q16, q20 with pandas and compare with the SQL answers."""
    qs = {q.id: q for q in questions}
    txn = ds["txn"]
    captured = int(ds["txn_status_dict"].loc[ds["txn_status_dict"].code == "CAPTURED", "status_id"].iloc[0])
    results = []

    def record(qid, value):
        q = qs[qid]
        results.append(dict(id=qid, pandas=value, sql=q.answer, ok=matches(q, value)))

    # q01: one day, fx + exponent
    d = txn[(txn.ts_utc >= "2025-03-14 00:00:00") & (txn.ts_utc < "2025-03-15 00:00:00") & (txn.status_id == captured)]
    record("q01", round(float(_eur(ds, d, "ts_utc").sum()), 2))

    # q02 / q03 / q06-like: merchant at txn time + hierarchy
    merchant = _merchant_at_txn(ds, txn)
    seasonal = merchants_in_group(ds, SEASONAL_GROUP["group"])
    sel = txn[np.isin(merchant, list(seasonal))]
    weeks = pd.Series([iso_week_label(datetime.strptime(s[:10], "%Y-%m-%d").date()) for s in sel.ts_utc])
    record("q02", weeks.value_counts().idxmax())
    aurora = merchants_in_group(ds, "Aurora Hospitality")
    sel = txn[np.isin(merchant, list(aurora)) & (txn.status_id == captured) & (txn.ts_utc < "2025-07-01 00:00:00")]
    record("q03", round(float(_eur(ds, sel, "ts_utc").sum()), 2))

    # q09: timeouts on the outage acquirer's routes during the incident window, versioned dictionary
    inc = ds["incident"]
    code = ds.meta["incident_by_tag"]["outage"]
    row = inc[inc.code == code].iloc[0]
    acq = int(ds["dim_acquirer"].loc[ds["dim_acquirer"].name == OUTAGE["acquirer"], "acquirer_id"].iloc[0])
    routes = set(ds["route"].loc[ds["route"].acquirer_id == acq, "route_id"])
    sel = txn[txn.route_id.isin(routes) & (txn.ts_utc >= row.opened_at) & (txn.ts_utc < row.closed_at)]
    _, to = _rc_flags(ds, sel.response_code, sel.ts_utc)
    record("q09", round(float(to.mean()), 4))

    # q10: operator with most incidents within 60 minutes after their changes
    dep = ds["deployment"].rename(columns={"deployed_at": "change_ts"})[["component_id", "operator_id", "change_ts"]]
    cfg = ds["config_change"].rename(columns={"changed_at": "change_ts"})[["component_id", "operator_id", "change_ts"]]
    changes = pd.concat([dep, cfg])
    hits = set()
    for i in inc.itertuples():
        o = parse_ts(i.opened_at)
        lo = (o - timedelta(minutes=60)).strftime("%Y-%m-%d %H:%M:%S")
        sub = changes[(changes.component_id == i.component_id) & (changes.change_ts >= lo) & (changes.change_ts <= i.opened_at)]
        for op in sub.operator_id.unique():
            hits.add((int(op), int(i.incident_id)))
    counts = pd.Series([h[0] for h in hits]).value_counts()
    login = dict(zip(ds["operator"].operator_id, ds["operator"].login))
    assert counts.iloc[0] > counts.iloc[1], f"operator story not unique: {counts}"
    record("q10", login[int(counts.index[0])])
    ds.meta["operator_counts"] = {login[int(k)]: int(v) for k, v in counts.items()}

    # q11: settlements whose applied rate deviates > 0.5 % from the rate of the settlement date
    st = ds["settlement"].merge(txn[["txn_id", "currency_id"]], on="txn_id")
    fx = ds["fx_rate"].rename(columns={"rate_date": "_d"})
    st = st.assign(_d=st.settled_at.str[:10]).merge(fx, on=["currency_id", "_d"], how="left")
    dev = (st.fx_rate_applied - st.rate_to_eur).abs() / st.rate_to_eur
    record("q11", int((dev > 0.005).sum()))

    # q16: ISO week with most auth-router ERROR events (whole year)
    se = ds["service_event"]
    cid = int(ds["dim_component"].loc[ds["dim_component"].name == BAD_DEPLOY["component"], "component_id"].iloc[0])
    sel = se[(se.component_id == cid) & (se.level == "ERROR")]
    weeks = pd.Series([iso_week_label(datetime.strptime(s[:10], "%Y-%m-%d").date()) for s in sel.ts_utc])
    record("q16", weeks.value_counts().idxmax())

    # q20: distinct terminals linked to Borealis merchants during May 2025
    borealis = merchants_in_group(ds, "Borealis Retail AG")
    ta = ds["terminal_assignment"]
    sel = ta[ta.merchant_id.isin(borealis) & (ta.valid_from < "2025-06-01 00:00:00") &
             (ta.valid_to.isna() | (ta.valid_to > "2025-05-01 00:00:00"))]
    record("q20", int(sel.terminal_id.nunique()))
    return results


# ------------------------------------------------------------------ story statistics for STORIES.md
def story_stats(ds: Dataset, con: sqlite3.Connection) -> dict:
    """Numbers quoted in STORIES.md, all computed from the v1 database."""
    s: dict = {}
    rid = ds.meta["bad_route_id"]
    s["deploy_window"] = con.execute(
        f"""SELECT COUNT(*), ROUND(AVG(latency_ms)), ROUND(AVG(response_code = 'Z1'), 3) FROM txn
            WHERE route_id = {rid} AND ts_utc >= '{BAD_DEPLOY['effect_from']}' AND ts_utc < '{BAD_DEPLOY['effect_to']}'""").fetchone()
    s["deploy_before"] = con.execute(
        f"""SELECT COUNT(*), ROUND(AVG(latency_ms)), ROUND(AVG(response_code = 'Z1'), 3) FROM txn
            WHERE route_id = {rid} AND ts_utc >= datetime('{BAD_DEPLOY['effect_from']}', '-145 minutes') AND ts_utc < '{BAD_DEPLOY['effect_from']}'""").fetchone()
    s["deploy_errors"] = con.execute(
        """SELECT COUNT(*) FROM service_event e JOIN incident_link l ON l.correlation_id = e.correlation_id
           JOIN incident i ON i.incident_id = l.incident_id WHERE i.code = ? AND e.level = 'ERROR'""",
        (ds.meta["incident_by_tag"]["bad_deploy"],)).fetchone()[0]
    s["outage"] = con.execute(
        f"""SELECT COUNT(*), ROUND(AVG(response_code IN ('Z3','91','96')), 4), ROUND(AVG(response_code IN ('Z3','91')), 4)
            FROM txn t JOIN route r ON r.route_id = t.route_id JOIN dim_acquirer a ON a.acquirer_id = r.acquirer_id
            WHERE a.name = '{OUTAGE['acquirer']}' AND t.ts_utc >= '{OUTAGE['from_ts']}' AND t.ts_utc < '{OUTAGE['to_ts']}'""").fetchone()
    s["outage_incident_window"] = con.execute(
        f"""SELECT COUNT(*), ROUND(AVG(response_code IN ('Z3','91','96')), 4), ROUND(AVG(response_code IN ('Z3','91')), 4)
            FROM txn t JOIN route r ON r.route_id = t.route_id JOIN dim_acquirer a ON a.acquirer_id = r.acquirer_id
            JOIN incident i ON i.code = '{ds.meta['incident_by_tag']['outage']}'
            WHERE a.name = '{OUTAGE['acquirer']}' AND t.ts_utc >= i.opened_at AND t.ts_utc < i.closed_at""").fetchone()
    s["firmware_monthly"] = con.execute(
        """SELECT strftime('%Y-%m', t.ts_utc) m, ROUND(AVG(rc.is_decline), 4), COUNT(*) FROM txn t
           JOIN dim_terminal d ON d.terminal_id = t.terminal_id JOIN dim_terminal_model mo ON mo.model_id = d.model_id
           JOIN response_code_dict rc ON rc.code = t.response_code AND t.ts_utc >= rc.valid_from AND (rc.valid_to IS NULL OR t.ts_utc < rc.valid_to)
           WHERE mo.firmware_family = 'OSX-3' GROUP BY m ORDER BY m""").fetchall()
    s["family_q4"] = con.execute(
        """SELECT mo.firmware_family, ROUND(AVG(rc.is_decline), 4), COUNT(*) FROM txn t
           JOIN dim_terminal d ON d.terminal_id = t.terminal_id JOIN dim_terminal_model mo ON mo.model_id = d.model_id
           JOIN response_code_dict rc ON rc.code = t.response_code AND t.ts_utc >= rc.valid_from AND (rc.valid_to IS NULL OR t.ts_utc < rc.valid_to)
           WHERE t.ts_utc >= '2025-10-01 00:00:00' GROUP BY 1 ORDER BY 2 DESC""").fetchall()
    s["seasonal_weeks"] = con.execute(
        f"""WITH RECURSIVE grp(group_id) AS (SELECT group_id FROM dim_merchant_group WHERE name = '{SEASONAL_GROUP['group']}'
              UNION ALL SELECT g.group_id FROM dim_merchant_group g JOIN grp ON g.parent_group_id = grp.group_id),
            thu AS (SELECT date(t.ts_utc, '-' || ((strftime('%w', t.ts_utc) + 6) % 7) || ' days', '+3 days') AS th FROM txn t
              JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id AND t.ts_utc >= ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc < ta.valid_to)
              JOIN dim_merchant m ON m.merchant_id = ta.merchant_id JOIN grp ON grp.group_id = m.group_id)
            SELECT strftime('%Y', th) || '-W' || printf('%02d', (strftime('%j', th) - 1) / 7 + 1) wk, COUNT(*) n FROM thu GROUP BY wk ORDER BY n DESC LIMIT 4""").fetchall()
    s["seasonal_monthly"] = con.execute(
        f"""WITH RECURSIVE grp(group_id) AS (SELECT group_id FROM dim_merchant_group WHERE name = '{SEASONAL_GROUP['group']}'
              UNION ALL SELECT g.group_id FROM dim_merchant_group g JOIN grp ON g.parent_group_id = grp.group_id)
            SELECT strftime('%Y-%m', t.ts_utc) m, ROUND(SUM(t.amount_minor / power(10, c.exponent) * f.rate_to_eur)) FROM txn t
            JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id AND t.ts_utc >= ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc < ta.valid_to)
            JOIN dim_merchant m ON m.merchant_id = ta.merchant_id JOIN grp ON grp.group_id = m.group_id
            JOIN dim_currency c ON c.currency_id = t.currency_id JOIN fx_rate f ON f.currency_id = t.currency_id AND f.rate_date = substr(t.ts_utc, 1, 10)
            JOIN txn_status_dict s ON s.status_id = t.status_id WHERE s.code = 'CAPTURED' GROUP BY m ORDER BY m""").fetchall()
    s["stale_by_day"] = con.execute(
        """SELECT substr(s.settled_at, 1, 10) d, COUNT(*), SUM(ABS(s.fx_rate_applied - f.rate_to_eur) / f.rate_to_eur > 0.005)
           FROM settlement s JOIN txn t ON t.txn_id = s.txn_id
           JOIN fx_rate f ON f.currency_id = t.currency_id AND f.rate_date = substr(s.settled_at, 1, 10)
           WHERE s.fx_rate_applied <> f.rate_to_eur GROUP BY d ORDER BY d""").fetchall()
    s["moved"] = con.execute(
        """SELECT COUNT(*) FROM terminal_assignment WHERE valid_to = ?""", (MOVE["move_ts"],)).fetchone()[0]
    s["coffee_h1_eur"] = con.execute(
        """WITH RECURSIVE grp(group_id) AS (SELECT group_id FROM dim_merchant_group WHERE name = 'Aurora Coffee Chain')
           SELECT ROUND(SUM(t.amount_minor / power(10, c.exponent) * f.rate_to_eur), 2) FROM txn t
           JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id AND t.ts_utc >= ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc < ta.valid_to)
           JOIN dim_merchant m ON m.merchant_id = ta.merchant_id JOIN grp ON grp.group_id = m.group_id
           JOIN dim_currency c ON c.currency_id = t.currency_id JOIN fx_rate f ON f.currency_id = t.currency_id AND f.rate_date = substr(t.ts_utc, 1, 10)
           JOIN txn_status_dict s ON s.status_id = t.status_id WHERE s.code = 'CAPTURED'""").fetchone()[0]
    s["incidents"] = con.execute(
        """SELECT i.code, i.opened_at, i.closed_at, sv.code, c.name, rc.code, i.summary,
                  (SELECT COUNT(*) FROM incident_link l WHERE l.incident_id = i.incident_id)
           FROM incident i JOIN dim_severity sv ON sv.severity_id = i.severity_id
           JOIN dim_component c ON c.component_id = i.component_id
           LEFT JOIN dim_root_cause rc ON rc.root_cause_id = i.root_cause_id ORDER BY i.opened_at""").fetchall()
    s["auth_router_error_weeks"] = con.execute(
        """WITH thu AS (SELECT date(e.ts_utc, '-' || ((strftime('%w', e.ts_utc) + 6) % 7) || ' days', '+3 days') AS th
             FROM service_event e JOIN dim_component c ON c.component_id = e.component_id WHERE c.name = 'auth-router' AND e.level = 'ERROR')
           SELECT strftime('%Y', th) || '-W' || printf('%02d', (strftime('%j', th) - 1) / 7 + 1) wk, COUNT(*) n FROM thu GROUP BY wk ORDER BY n DESC LIMIT 3""").fetchall()
    return s


def sanity_checks(ds: Dataset, con: sqlite3.Connection) -> None:
    """Hard assertions that the planted structure is intact."""
    # every transaction has exactly one assignment covering its timestamp
    n_txn = con.execute("SELECT COUNT(*) FROM txn").fetchone()[0]
    n_cov = con.execute("""SELECT COUNT(*) FROM txn t JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id
                           AND t.ts_utc >= ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc < ta.valid_to)""").fetchone()[0]
    assert n_txn == n_cov, (n_txn, n_cov)
    # every response code is in every dictionary version
    missing = con.execute("""SELECT COUNT(*) FROM txn t LEFT JOIN response_code_dict rc ON rc.code = t.response_code
                             AND t.ts_utc >= rc.valid_from AND (rc.valid_to IS NULL OR t.ts_utc < rc.valid_to) WHERE rc.rc_id IS NULL""").fetchone()[0]
    assert missing == 0
    # every settlement finds a rate for its date
    missing = con.execute("""SELECT COUNT(*) FROM settlement s JOIN txn t ON t.txn_id = s.txn_id
                             LEFT JOIN fx_rate f ON f.currency_id = t.currency_id AND f.rate_date = substr(s.settled_at, 1, 10) WHERE f.fx_rate_id IS NULL""").fetchone()[0]
    assert missing == 0
    # operator story
    counts = ds.meta["operator_counts"]
    top = max(counts, key=counts.get)
    assert top == OPERATOR_STORY["operator"] and counts[top] == OPERATOR_STORY["n_incidents"], counts


# ============================================================================ v2 catalogue (questions_v2.json)
def run_naive_variants(questions: list[Question], cons: dict[str, sqlite3.Connection]) -> list[dict]:
    """Run every ``naive_variants`` entry, fill in its answer and whether it would be graded INCORRECT."""
    out = []
    for q in questions:
        for v in q.naive_variants:
            try:
                val = _scalar(cons[q.db], v["sql"])
            except sqlite3.Error as e:            # pragma: no cover - would be a bug in the naive SQL
                val = f"SQL error: {e}"
            if isinstance(val, float) and q.type == "float":
                val = float(val)
            v["answer"] = val
            v["discriminative"] = not matches(q, val)
            out.append(dict(id=q.id, label=v["description"], naive=val, correct=q.answer, distinguishes=v["discriminative"]))
    return out


def _fmt_metric(v) -> str:
    if isinstance(v, float):
        return f"{v:,.4f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.2f}"
    return str(v)


def compute_margins(questions: list[Question], cons: dict[str, sqlite3.Connection]) -> list[dict]:
    """For 'which X' questions run ``candidates_sql`` (best-first rows of (candidate, metric)), check that the
    winner is the ground-truth answer and append the margin to the runner-up to the rationale."""
    out = []
    for q in questions:
        if not q.candidates_sql:
            continue
        rows = cons[q.db].execute(q.candidates_sql).fetchall()
        assert len(rows) >= 2, (q.id, rows)
        (c1, m1), (c2, m2) = rows[0][:2], rows[1][:2]
        ans = str(q.answer)
        assert str(c1) == ans or str(c1).split(" ")[0] == ans, f"{q.id}: top candidate {c1!r} != answer {ans!r}"
        rel = (m1 - m2) / abs(m1) if m1 else None
        q.margin = dict(top=str(c1), top_metric=m1, second=str(c2), second_metric=m2,
                        abs_margin=m1 - m2, rel_margin=rel)
        q.rationale = (q.rationale.rstrip() + f" Margin: '{c1}' = {_fmt_metric(m1)} vs runner-up '{c2}' = "
                       f"{_fmt_metric(m2)}" + (f" ({rel:.0%} of the winner's value)." if rel is not None else "."))
        out.append(dict(id=q.id, **q.margin))
    return out


def _iso_weeks(ts: pd.Series) -> pd.Series:
    """Vectorised 'YYYY-Www' labels."""
    ic = pd.to_datetime(ts).dt.isocalendar()
    return ic.year.astype(str) + "-W" + ic.week.astype(int).map("{:02d}".format)


def independent_checks_v2(ds: Dataset, questions_v2: list[Question], questions_v1: list[Question]) -> list[dict]:
    """(a) q01..q20 of the v2 catalogue must have exactly the v1 answers; (b) q21..q26 recomputed with pandas."""
    v1 = {q.id: q for q in questions_v1}
    qs = {q.id: q for q in questions_v2}
    results = []
    for qid, q1 in v1.items():
        q2 = qs[qid]
        assert q2.answer == q1.answer, (qid, q2.answer, q1.answer)
        assert q2.gt_sql == q1.gt_sql and q2.type == q1.type and q2.tolerance == q1.tolerance, qid

    def record(qid, value):
        q = qs[qid]
        results.append(dict(id=qid, pandas=value, sql=q.answer, ok=matches(q, value)))

    txn = ds["txn"]
    se = ds["service_event"]
    err = se[se.level == "ERROR"]

    # q21: rolled-back deployments, ERROR events of the component while live
    dep = ds["deployment"]
    rb = dep[dep.rolled_back_at.notna()]
    counts = {}
    for d in rb.itertuples():
        m = (err.component_id == d.component_id) & (err.ts_utc >= d.deployed_at) & (err.ts_utc < d.rolled_back_at)
        counts[int(d.deployment_id)] = int(m.sum())
    best = max(counts, key=counts.get)
    record("q21", best)

    # q22: OLS slope of weekly counts per division (hierarchy roll-up, assignment valid at txn time, zero-filled weeks)
    merchant = _merchant_at_txn(ds, txn)
    g = ds["dim_merchant_group"]
    parent = {int(r.group_id): (None if pd.isna(r.parent_group_id) else int(r.parent_group_id)) for r in g.itertuples()}
    names = dict(zip(g.group_id, g.name))
    divisions = {gid for gid, p in parent.items() if p is not None and parent[p] is None}

    def division_of(gid):
        while gid is not None:
            if gid in divisions:
                return gid
            gid = parent[gid]
        return None
    m_div = {int(r.merchant_id): division_of(int(r.group_id)) for r in ds["dim_merchant"].itertuples()}
    div_of_txn = pd.Series(merchant).map(m_div)
    weeks = _iso_weeks(txn.ts_utc)
    wnum = weeks.str[6:8].astype(int)
    in_year = weeks.str.startswith("2025-")
    df = pd.DataFrame({"div": div_of_txn.to_numpy(), "w": wnum.to_numpy()})[in_year.to_numpy()].dropna()
    slopes = {}
    x = np.arange(1, 53)
    for d, grp in df.groupby("div"):
        y = grp.w.value_counts().reindex(x, fill_value=0).to_numpy(dtype=float)
        slopes[int(d)] = float(np.polyfit(x, y, 1)[0])
    top = max(slopes, key=slopes.get)
    record("q22", names[top])
    ds.meta["q22_slopes"] = {names[k]: round(v, 3) for k, v in sorted(slopes.items(), key=lambda kv: -kv[1])}

    # q23: timed-out transactions on 2025-09-18 followed by another txn on the same terminal within 90 s
    day = txn[(txn.ts_utc >= "2025-09-18 00:00:00") & (txn.ts_utc < "2025-09-19 00:00:00")].copy()
    _, to = _rc_flags(ds, day.response_code, day.ts_utc)
    day["is_timeout"] = to
    day["t"] = pd.to_datetime(day.ts_utc)
    pairs = day[day.is_timeout == 1][["txn_id", "terminal_id", "t"]].merge(day[["terminal_id", "t"]], on="terminal_id", suffixes=("", "_b"))
    delta = (pairs.t_b - pairs.t).dt.total_seconds()
    record("q23", int(pairs[(delta > 0) & (delta <= 90)].txn_id.nunique()))

    # q24: config change followed by the most ERROR events of its component within 60 minutes
    cc = ds["config_change"]
    counts = {}
    for c in cc.itertuples():
        hi = (parse_ts(c.changed_at) + timedelta(minutes=60)).strftime("%Y-%m-%d %H:%M:%S")
        m = (err.component_id == c.component_id) & (err.ts_utc >= c.changed_at) & (err.ts_utc < hi)
        counts[int(c.change_id)] = int(m.sum())
    record("q24", max(counts, key=counts.get))

    # q25: ISO week with most ERROR events platform-wide
    record("q25", _iso_weeks(err.ts_utc).value_counts().idxmax())

    # q26: leaf group with the largest H1 - H2 transaction count
    children = {p for p in parent.values() if p is not None}
    leaf_of_m = {int(r.merchant_id): (int(r.group_id) if int(r.group_id) not in children else None)
                 for r in ds["dim_merchant"].itertuples()}
    leaf = pd.Series(merchant).map(leaf_of_m)
    h1 = (txn.ts_utc < "2025-07-01 00:00:00").to_numpy()
    df = pd.DataFrame({"leaf": leaf.to_numpy(), "h1": h1}).dropna()
    loss = df.groupby("leaf").h1.apply(lambda s: int(s.sum()) - int((~s).sum()))
    record("q26", names[int(loss.idxmax())])
    return results
