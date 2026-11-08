"""Question catalogue: texts, ground-truth SQL (v1 or v2 schema), naive variants and metadata.

Dynamic parameters (incident codes, thresholds) are resolved from the generated
data so the texts are stable across runs of the deterministic generator.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, asdict

from .common import Dataset
from .stories import BAD_DEPLOY, FX_STORY, OUTAGE, SEASONAL_GROUP

# ---------------------------------------------------------------- SQL building blocks
ISO_WEEK = ("strftime('%Y', date({c}, '-' || ((strftime('%w', {c}) + 6) % 7) || ' days', '+3 days')) || '-W' || "
            "printf('%02d', (strftime('%j', date({c}, '-' || ((strftime('%w', {c}) + 6) % 7) || ' days', '+3 days')) - 1) / 7 + 1)")
NAIVE_WEEK = "strftime('%Y-W%W', {c})"


def hier(name: str) -> str:
    return (f"WITH RECURSIVE grp(group_id) AS (\n"
            f"  SELECT group_id FROM dim_merchant_group WHERE name = '{name}'\n"
            f"  UNION ALL\n"
            f"  SELECT g.group_id FROM dim_merchant_group g JOIN grp ON g.parent_group_id = grp.group_id\n)")


EUR_V1 = "t.amount_minor / power(10, c.exponent) * f.rate_to_eur"
EUR_V2 = "t.amount_minor / power(10, c.exponent) * f.eur_per_unit"
FX_V1 = "JOIN dim_currency c ON c.currency_id = t.currency_id\nJOIN fx_rate f ON f.currency_id = t.currency_id AND f.rate_date = substr(t.ts_utc, 1, 10)"
FX_V2 = "JOIN dim_currency c ON c.currency_id = t.currency_id\nJOIN fx_rate_daily f ON f.currency_id = t.currency_id AND f.rate_date = substr(t.ts_utc, 1, 10)"
ASSIGN_V1 = ("JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id\n"
             "  AND t.ts_utc >= ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc < ta.valid_to)\n"
             "JOIN dim_merchant m ON m.merchant_id = ta.merchant_id\nJOIN grp ON grp.group_id = m.group_id")
ASSIGN_V1_NAIVE = ("JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id AND ta.valid_to IS NULL\n"
                   "JOIN dim_merchant m ON m.merchant_id = ta.merchant_id\nJOIN grp ON grp.group_id = m.group_id")
ASSIGN_V2 = ("JOIN terminal_merchant_link tl ON tl.terminal_id = t.terminal_id\n"
             "  AND t.ts_utc >= tl.start_ts AND (tl.end_ts IS NULL OR t.ts_utc < tl.end_ts)\n"
             "JOIN dim_merchant m ON m.merchant_id = tl.merchant_id\nJOIN grp ON grp.group_id = m.merchant_group_id")
ASSIGN_V2_NAIVE = ("JOIN terminal_merchant_link tl ON tl.terminal_id = t.terminal_id AND tl.end_ts IS NULL\n"
                   "JOIN dim_merchant m ON m.merchant_id = tl.merchant_id\nJOIN grp ON grp.group_id = m.merchant_group_id")
RC_VERSIONED = ("JOIN response_code_dict rc ON rc.code = t.response_code\n"
                "  AND t.ts_utc >= rc.valid_from AND (rc.valid_to IS NULL OR t.ts_utc < rc.valid_to)")
CAPTURED = "JOIN txn_status_dict s ON s.status_id = t.status_id"
MODEL = "JOIN dim_terminal d ON d.terminal_id = t.terminal_id\nJOIN dim_terminal_model mo ON mo.model_id = d.model_id"


@dataclass
class Question:
    id: str
    stage: str                    # pre | post
    db: str                       # v1 | v2
    text: str
    gt_sql: str
    type: str                     # int | float | str
    tolerance: float
    knowledge_tags: list[str]
    difficulty: str               # medium | hard
    rationale: str
    answer_format: str
    answer: object = None
    naive: dict = field(default_factory=dict)   # label -> sql (v1 catalogue; not exported to questions.json)
    # v2 catalogue only (questions_v2.json): typical wrong approaches, each
    # {description, sql, answer, discriminative}; answers are filled in by validate.run_naive_variants.
    naive_variants: list[dict] = field(default_factory=list)
    # v2 catalogue only: SQL returning (candidate, metric) rows ordered best-first, used to record the
    # margin between the winning candidate and the runner-up (validate.compute_margins). Not exported.
    candidates_sql: str | None = None
    margin: dict | None = None

    def export(self, with_variants: bool = False) -> dict:
        """JSON record. ``with_variants=False`` reproduces the original questions.json layout exactly."""
        d = asdict(self)
        for k in ("naive", "candidates_sql", "margin", "naive_variants"):
            d.pop(k)
        if with_variants:
            d["naive_variants"] = [dict(v) for v in self.naive_variants]
        return d


def pick_threshold(con: sqlite3.Connection) -> tuple[int, str]:
    """Choose the EUR threshold for the 'first month exceeding X' question from the data.

    Picks the month (not Jan/Dec) with the widest relative margin on both sides
    and a round threshold half-way between the previous maximum and that month.
    """
    rows = con.execute(f"""{hier(SEASONAL_GROUP['group'])}
SELECT strftime('%Y-%m', t.ts_utc) AS month, SUM({EUR_V1}) AS eur
FROM txn t
{ASSIGN_V1}
{FX_V1}
{CAPTURED}
WHERE s.code = 'CAPTURED'
GROUP BY month ORDER BY month""").fetchall()
    best = None
    for k in range(1, len(rows) - 1):
        lo, hi = max(v for _, v in rows[:k]), rows[k][1]
        if hi <= lo:
            continue
        thr = int(round((lo + hi) / 2 / 5000.0) * 5000)
        margin = min(hi - thr, thr - lo) / thr
        if best is None or margin > best[0]:
            best = (margin, thr, rows[k][0])
    assert best is not None and best[0] > 0.03, f"no unambiguous threshold: {rows}"
    return best[1], best[2]


def build_questions(ds: Dataset, con_v1: sqlite3.Connection) -> list[Question]:
    """Return the 20 questions (14 pre-drift on v1, 6 post-drift on v2) with GT SQL."""
    inc = ds.meta["incident_by_tag"]
    inc_bad, inc_outage, inc_fx = inc["bad_deploy"], inc["outage"], inc["fx_stale"]
    inc_q18 = inc["random_16"]
    thr, _ = pick_threshold(con_v1)
    ds.meta["q06_threshold"] = thr
    Q: list[Question] = []

    Q.append(Question(
        id="q01", stage="pre", db="v1", difficulty="medium", type="float", tolerance=1.0,
        knowledge_tags=["FX_EXPONENT", "DATE_FILTER"], answer_format="number (EUR, 2 decimals)",
        text=("What was the total value in EUR of all transactions with status CAPTURED whose ts_utc falls on "
              "2025-03-14 UTC (2025-03-14 00:00:00 <= ts_utc < 2025-03-15 00:00:00)? Convert every transaction amount "
              "to EUR (major units) using the daily FX rate (EUR per unit of the transaction currency) for the "
              "transaction date. Answer with one number in EUR rounded to 2 decimals, e.g. 12345.67."),
        gt_sql=f"""SELECT ROUND(SUM({EUR_V1}), 2) AS eur_total
FROM txn t
{FX_V1}
{CAPTURED}
WHERE s.code = 'CAPTURED'
  AND t.ts_utc >= '2025-03-14 00:00:00' AND t.ts_utc < '2025-03-15 00:00:00'""",
        rationale="amount_minor must be scaled by 10^exponent per currency (JPY=0, KWD=3) before applying the daily rate; "
                  "dividing everything by 100 inflates JPY and deflates KWD amounts.",
        naive={"divide all amounts by 100 (ignore exponent)": f"""SELECT ROUND(SUM(t.amount_minor / 100.0 * f.rate_to_eur), 2)
FROM txn t
{FX_V1}
{CAPTURED}
WHERE s.code = 'CAPTURED' AND t.ts_utc >= '2025-03-14 00:00:00' AND t.ts_utc < '2025-03-15 00:00:00'"""}))

    Q.append(Question(
        id="q02", stage="pre", db="v1", difficulty="medium", type="str", tolerance=0,
        knowledge_tags=["HIERARCHY", "DATE_RANGE_JOIN", "ISO_WEEK"], answer_format="YYYY-Www",
        text=(f"Consider all transactions (any status) made on terminals that were assigned, at the time of each "
              f"transaction, to a merchant belonging to merchant group '{SEASONAL_GROUP['group']}' or to any of its "
              f"sub-groups (at any depth). Which ISO-8601 week had the largest number of such transactions in 2025? "
              f"Answer in the format YYYY-Www, e.g. 2025-W07."),
        gt_sql=f"""{hier(SEASONAL_GROUP['group'])}
SELECT {ISO_WEEK.format(c='t.ts_utc')} AS iso_week, COUNT(*) AS n
FROM txn t
{ASSIGN_V1}
GROUP BY iso_week ORDER BY n DESC LIMIT 1""",
        rationale="The group is a level-2 division; its merchants hang off level-3 chains, so a recursive roll-up is needed. "
                  "SQLite's %W is not the ISO week (off by one in 2025); growth + December bump put the peak in W51.",
        naive={"strftime('%W') instead of ISO week": f"""{hier(SEASONAL_GROUP['group'])}
SELECT {NAIVE_WEEK.format(c='t.ts_utc')} AS wk, COUNT(*) AS n FROM txn t
{ASSIGN_V1}
GROUP BY wk ORDER BY n DESC LIMIT 1""",
               "only merchants directly in the group (no hierarchy)": f"""SELECT {ISO_WEEK.format(c='t.ts_utc')} AS iso_week, COUNT(*) AS n
FROM txn t
JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id AND t.ts_utc >= ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc < ta.valid_to)
JOIN dim_merchant m ON m.merchant_id = ta.merchant_id
JOIN dim_merchant_group g ON g.group_id = m.group_id AND g.name = '{SEASONAL_GROUP['group']}'
GROUP BY iso_week ORDER BY n DESC LIMIT 1"""}))

    Q.append(Question(
        id="q03", stage="pre", db="v1", difficulty="hard", type="float", tolerance=500.0,
        knowledge_tags=["HIERARCHY", "DATE_RANGE_JOIN", "FX_EXPONENT"], answer_format="number (EUR, 2 decimals)",
        text=("What was the total value in EUR of CAPTURED transactions in the first half of 2025 "
              "(2025-01-01 00:00:00 <= ts_utc < 2025-07-01 00:00:00) made on terminals that were assigned, at the time "
              "of the transaction, to merchants of merchant group 'Aurora Hospitality' or any of its sub-groups? "
              "Convert amounts to EUR with the daily FX rate of the transaction date. Answer with one number in EUR "
              "rounded to 2 decimals."),
        gt_sql=f"""{hier('Aurora Hospitality')}
SELECT ROUND(SUM({EUR_V1}), 2) AS eur_total
FROM txn t
{ASSIGN_V1}
{FX_V1}
{CAPTURED}
WHERE s.code = 'CAPTURED'
  AND t.ts_utc >= '2025-01-01 00:00:00' AND t.ts_utc < '2025-07-01 00:00:00'""",
        rationale="The 'Aurora Coffee Chain' (a sub-group) sold its 44 terminals on 2025-06-16; they now belong to merchants "
                  "of another holding. Joining on the current assignment drops their H1 volume.",
        naive={"join on current assignment (valid_to IS NULL)": f"""{hier('Aurora Hospitality')}
SELECT ROUND(SUM({EUR_V1}), 2)
FROM txn t
{ASSIGN_V1_NAIVE}
{FX_V1}
{CAPTURED}
WHERE s.code = 'CAPTURED' AND t.ts_utc >= '2025-01-01 00:00:00' AND t.ts_utc < '2025-07-01 00:00:00'"""}))

    Q.append(Question(
        id="q04", stage="pre", db="v1", difficulty="medium", type="float", tolerance=0.0005,
        knowledge_tags=["CODE_DICT_VERSION", "TERMINAL_MODEL"], answer_format="decimal fraction, 4 decimals",
        text=("For terminal model 'P400', what was the decline rate in August 2025 "
              "(2025-08-01 00:00:00 <= ts_utc < 2025-09-01 00:00:00)? A transaction counts as declined if its "
              "response code is flagged as a decline in the response-code dictionary version that was valid at the "
              "transaction's timestamp. Decline rate = declined transactions / all transactions of that model in the "
              "month (any status). Answer as a decimal fraction rounded to 4 decimals, e.g. 0.0712."),
        gt_sql=f"""SELECT ROUND(AVG(rc.is_decline), 4) AS decline_rate
FROM txn t
{MODEL}
{RC_VERSIONED}
WHERE mo.model_name = 'P400'
  AND t.ts_utc >= '2025-08-01 00:00:00' AND t.ts_utc < '2025-09-01 00:00:00'""",
        rationale="Scheme version 2 (valid from 2025-07-01) re-classifies code 96 (decline -> timeout) and 68 (timeout -> "
                  "decline); August must be classified with version 2. P400 belongs to the OSX-3 family, whose declines "
                  "rose after the 2025-08-04 firmware rollout.",
        naive={"always use scheme_version 1": f"""SELECT ROUND(AVG(rc.is_decline), 4)
FROM txn t
{MODEL}
JOIN response_code_dict rc ON rc.code = t.response_code AND rc.scheme_version = 1
WHERE mo.model_name = 'P400' AND t.ts_utc >= '2025-08-01 00:00:00' AND t.ts_utc < '2025-09-01 00:00:00'""",
               "status = FAILED as 'declined'": f"""SELECT ROUND(AVG(s.code = 'FAILED'), 4)
FROM txn t
{MODEL}
{CAPTURED}
WHERE mo.model_name = 'P400' AND t.ts_utc >= '2025-08-01 00:00:00' AND t.ts_utc < '2025-09-01 00:00:00'"""}))

    Q.append(Question(
        id="q05", stage="pre", db="v1", difficulty="hard", type="str", tolerance=0,
        knowledge_tags=["CODE_DICT_VERSION", "TERMINAL_MODEL"], answer_format="firmware_family string",
        text=("Among terminal firmware families with at least 10,000 transactions in Q4 2025 "
              "(2025-10-01 00:00:00 <= ts_utc < 2026-01-01 00:00:00), which family had the highest decline rate? "
              "A transaction is declined if its response code is flagged as a decline in the response-code dictionary "
              "version valid at the transaction time; decline rate = declined / all transactions of the family in Q4. "
              "Answer with the firmware family name exactly as stored."),
        gt_sql=f"""SELECT mo.firmware_family
FROM txn t
{MODEL}
{RC_VERSIONED}
WHERE t.ts_utc >= '2025-10-01 00:00:00' AND t.ts_utc < '2026-01-01 00:00:00'
GROUP BY mo.firmware_family
HAVING COUNT(*) >= 10000
ORDER BY AVG(rc.is_decline) DESC LIMIT 1""",
        rationale="Firmware 3.7.2 of family OSX-3 (models V240m, P400) raised declines by ~4.5 pp from 2025-08-04; the other "
                  "families stay at ~6.5 %.",
        naive={"status = FAILED as 'declined'": f"""SELECT mo.firmware_family
FROM txn t
{MODEL}
{CAPTURED}
WHERE t.ts_utc >= '2025-10-01 00:00:00' AND t.ts_utc < '2026-01-01 00:00:00'
GROUP BY mo.firmware_family HAVING COUNT(*) >= 10000 ORDER BY AVG(s.code = 'FAILED') DESC LIMIT 1"""}))

    Q.append(Question(
        id="q06", stage="pre", db="v1", difficulty="medium", type="str", tolerance=0,
        knowledge_tags=["HIERARCHY", "DATE_RANGE_JOIN", "FX_EXPONENT", "TREND"], answer_format="YYYY-MM",
        text=(f"Consider CAPTURED transactions attributed (through the terminal assignment valid at the time of the "
              f"transaction) to merchants of merchant group '{SEASONAL_GROUP['group']}' or any of its sub-groups, "
              f"converted to EUR with the daily FX rate of the transaction date. What was the first calendar month of "
              f"2025 in which their total EUR value exceeded {thr:,} EUR? Answer in the format YYYY-MM."),
        gt_sql=f"""{hier(SEASONAL_GROUP['group'])}
SELECT month FROM (
  SELECT strftime('%Y-%m', t.ts_utc) AS month, SUM({EUR_V1}) AS eur
  FROM txn t
  {ASSIGN_V1}
  {FX_V1}
  {CAPTURED}
  WHERE s.code = 'CAPTURED'
  GROUP BY month
)
WHERE eur > {thr}
ORDER BY month LIMIT 1""",
        rationale=f"The group grows ~70 % over the year; the threshold {thr:,} EUR sits in the widest gap between a month "
                  f"and the maximum of all earlier months, so the answer is robust to rounding.",
        naive={"only merchants directly in the group (no hierarchy)": f"""SELECT month FROM (
  SELECT strftime('%Y-%m', t.ts_utc) AS month, SUM({EUR_V1}) AS eur
  FROM txn t
  JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id AND t.ts_utc >= ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc < ta.valid_to)
  JOIN dim_merchant m ON m.merchant_id = ta.merchant_id
  JOIN dim_merchant_group g ON g.group_id = m.group_id AND g.name = '{SEASONAL_GROUP['group']}'
  {FX_V1}
  {CAPTURED}
  WHERE s.code = 'CAPTURED' GROUP BY month)
WHERE eur > {thr} ORDER BY month LIMIT 1"""}))

    Q.append(Question(
        id="q07", stage="pre", db="v1", difficulty="hard", type="str", tolerance=0,
        knowledge_tags=["INCIDENT_LINK", "LOG_WINDOW", "DEPLOYMENT"], answer_format="version string",
        text=(f"Incident {inc_bad} is linked to service events through correlation ids. Find the earliest ERROR-level "
              f"service event linked to this incident. Which deployment of the incident's component was the most recent "
              f"one deployed strictly before that event? Answer with the deployment's version string exactly as stored."),
        gt_sql=f"""WITH inc AS (SELECT incident_id, component_id FROM incident WHERE code = '{inc_bad}'),
first_err AS (
  SELECT MIN(e.ts_utc) AS ts
  FROM service_event e
  JOIN incident_link l ON l.correlation_id = e.correlation_id
  JOIN inc ON inc.incident_id = l.incident_id
  WHERE e.level = 'ERROR')
SELECT d.version
FROM deployment d JOIN inc ON inc.component_id = d.component_id
WHERE d.deployed_at < (SELECT ts FROM first_err)
ORDER BY d.deployed_at DESC LIMIT 1""",
        rationale=f"First linked ERROR is at {BAD_DEPLOY['first_error_ts']}; the last deployment before it is "
                  f"{BAD_DEPLOY['version']} ({BAD_DEPLOY['deployed_at']}). A '+restart' re-deploy happened between the "
                  f"first error and the incident opening, and an unlinked ERROR occurred earlier that day.",
        naive={"latest deployment before incident.opened_at": f"""SELECT d.version FROM deployment d
JOIN incident i ON i.component_id = d.component_id
WHERE i.code = '{inc_bad}' AND d.deployed_at < i.opened_at ORDER BY d.deployed_at DESC LIMIT 1""",
               "first ERROR of the component that day (ignoring incident_link)": f"""WITH inc AS (SELECT incident_id, component_id, opened_at FROM incident WHERE code = '{inc_bad}'),
first_err AS (SELECT MIN(e.ts_utc) AS ts FROM service_event e JOIN inc ON inc.component_id = e.component_id
              WHERE e.level = 'ERROR' AND e.ts_utc >= date(inc.opened_at))
SELECT d.version FROM deployment d JOIN inc ON inc.component_id = d.component_id
WHERE d.deployed_at < (SELECT ts FROM first_err) ORDER BY d.deployed_at DESC LIMIT 1"""}))

    Q.append(Question(
        id="q08", stage="pre", db="v1", difficulty="medium", type="float", tolerance=0.05,
        knowledge_tags=["LOG_WINDOW", "DEPLOYMENT", "LATENCY"], answer_format="ratio, 2 decimals",
        text=(f"Component '{BAD_DEPLOY['component']}' had a deployment with version '{BAD_DEPLOY['version']}'; let T be "
              f"its deployed_at. For transactions on the route with code '{BAD_DEPLOY['route_code']}', compute the average "
              f"latency_ms over [T, T + 120 minutes) divided by the average latency_ms over [T - 120 minutes, T) "
              f"(all transactions regardless of status). Answer with the ratio rounded to 2 decimals."),
        gt_sql=f"""WITH d AS (
  SELECT dp.deployed_at AS t0 FROM deployment dp
  JOIN dim_component c ON c.component_id = dp.component_id
  WHERE c.name = '{BAD_DEPLOY['component']}' AND dp.version = '{BAD_DEPLOY['version']}'),
r AS (SELECT route_id FROM route WHERE code = '{BAD_DEPLOY['route_code']}')
SELECT ROUND(
  (SELECT AVG(t.latency_ms) FROM txn t, d, r WHERE t.route_id = r.route_id
     AND t.ts_utc >= d.t0 AND t.ts_utc < datetime(d.t0, '+120 minutes')) /
  (SELECT AVG(t.latency_ms) FROM txn t, d, r WHERE t.route_id = r.route_id
     AND t.ts_utc >= datetime(d.t0, '-120 minutes') AND t.ts_utc < d.t0), 2) AS ratio""",
        rationale="The bad release multiplied latency x4 on that route and produced 'Z1' processor timeouts (8-30 s), so "
                  "the mean latency after the deployment is an order of magnitude higher than before.",
        naive={"all routes instead of the affected route": f"""WITH d AS (
  SELECT dp.deployed_at AS t0 FROM deployment dp JOIN dim_component c ON c.component_id = dp.component_id
  WHERE c.name = '{BAD_DEPLOY['component']}' AND dp.version = '{BAD_DEPLOY['version']}')
SELECT ROUND((SELECT AVG(latency_ms) FROM txn t, d WHERE t.ts_utc >= d.t0 AND t.ts_utc < datetime(d.t0, '+120 minutes')) /
             (SELECT AVG(latency_ms) FROM txn t, d WHERE t.ts_utc >= datetime(d.t0, '-120 minutes') AND t.ts_utc < d.t0), 2)"""}))

    Q.append(Question(
        id="q09", stage="pre", db="v1", difficulty="hard", type="float", tolerance=0.0005,
        knowledge_tags=["CODE_DICT_VERSION", "INCIDENT_WINDOW", "ROUTE_ACQUIRER"], answer_format="decimal fraction, 4 decimals",
        text=(f"During incident {inc_outage} (from its opened_at inclusive to its closed_at exclusive), what share of "
              f"transactions on the routes of acquirer '{OUTAGE['acquirer']}' ended in a timeout? A timeout is a response "
              f"code flagged as timeout in the response-code dictionary version valid at the transaction time. "
              f"Share = timeout transactions / all transactions on those routes in the window (any status). "
              f"Answer as a decimal fraction rounded to 4 decimals."),
        gt_sql=f"""WITH inc AS (SELECT opened_at, closed_at FROM incident WHERE code = '{inc_outage}')
SELECT ROUND(AVG(rc.is_timeout), 4) AS timeout_share
FROM txn t
JOIN route r ON r.route_id = t.route_id
JOIN dim_acquirer a ON a.acquirer_id = r.acquirer_id
{RC_VERSIONED}
JOIN inc
WHERE a.name = '{OUTAGE['acquirer']}'
  AND t.ts_utc >= inc.opened_at AND t.ts_utc < inc.closed_at""",
        rationale="During the outage the acquirer returned Z3/91/96; code 96 is a timeout only in scheme version 2 "
                  "(valid in September), so classifying with version 1 under-counts timeouts.",
        naive={"always use scheme_version 1": f"""WITH inc AS (SELECT opened_at, closed_at FROM incident WHERE code = '{inc_outage}')
SELECT ROUND(AVG(rc.is_timeout), 4) FROM txn t
JOIN route r ON r.route_id = t.route_id JOIN dim_acquirer a ON a.acquirer_id = r.acquirer_id
JOIN response_code_dict rc ON rc.code = t.response_code AND rc.scheme_version = 1
JOIN inc WHERE a.name = '{OUTAGE['acquirer']}' AND t.ts_utc >= inc.opened_at AND t.ts_utc < inc.closed_at"""}))

    Q.append(Question(
        id="q10", stage="pre", db="v1", difficulty="hard", type="str", tolerance=0,
        knowledge_tags=["LOG_WINDOW", "OPERATOR_CHANGES", "DEPLOYMENT", "CONFIG_CHANGE"], answer_format="operator login",
        text=("Treat every deployment (deployed_at) and every config change (changed_at) as a 'change' made by its "
              "operator on a component. An incident is preceded by a change if the change is on the incident's component "
              "and 0 <= opened_at - change time <= 60 minutes. Which operator has the largest number of distinct incidents "
              "preceded by their changes? Answer with the operator's login."),
        gt_sql="""WITH changes AS (
  SELECT component_id, operator_id, deployed_at AS at FROM deployment
  UNION ALL
  SELECT component_id, operator_id, changed_at FROM config_change),
hits AS (
  SELECT DISTINCT ch.operator_id, i.incident_id
  FROM incident i
  JOIN changes ch ON ch.component_id = i.component_id
    AND ch.at <= i.opened_at AND ch.at >= datetime(i.opened_at, '-60 minutes'))
SELECT o.login
FROM hits h JOIN operator o ON o.operator_id = h.operator_id
GROUP BY o.login ORDER BY COUNT(*) DESC LIMIT 1""",
        rationale="r.svensson (SRE) made config changes 21-44 minutes before four different incidents; the runner-ups have 2 "
                  "(d.kowalski: the bad auth-router release plus one more deployment; j.mueller: two 'mitigation' changes).",
        naive={"deployments only (ignore config changes)": """WITH hits AS (
  SELECT DISTINCT d.operator_id, i.incident_id FROM incident i
  JOIN deployment d ON d.component_id = i.component_id AND d.deployed_at <= i.opened_at AND d.deployed_at >= datetime(i.opened_at, '-60 minutes'))
SELECT o.login FROM hits h JOIN operator o ON o.operator_id = h.operator_id GROUP BY o.login ORDER BY COUNT(*) DESC LIMIT 1"""}))

    Q.append(Question(
        id="q11", stage="pre", db="v1", difficulty="medium", type="int", tolerance=2,
        knowledge_tags=["SETTLEMENT", "FX_RATE_DATE"], answer_format="integer",
        text=("How many settlements were converted with an FX rate that deviates from the official daily rate? Count the "
              "settlements where |fx_rate_applied - R| / R > 0.005, where R is the official FX rate (EUR per unit of the "
              "transaction's currency) for the calendar date of settled_at (UTC). Answer with an integer."),
        gt_sql="""SELECT COUNT(*) AS n
FROM settlement s
JOIN txn t ON t.txn_id = s.txn_id
JOIN fx_rate f ON f.currency_id = t.currency_id AND f.rate_date = substr(s.settled_at, 1, 10)
WHERE ABS(s.fx_rate_applied - f.rate_to_eur) / f.rate_to_eur > 0.005""",
        rationale=f"The fx-service cache TTL was set to 7 days on {FX_STORY['change']['changed_at']}; settlement batches "
                  f"2025-05-13..2025-05-19 used the {FX_STORY['stale_rate_date']} snapshot. Only non-EUR settlements whose "
                  f"rate had drifted > 0.5 % by then are counted.",
        naive={"rate of the transaction date instead of the settlement date": """SELECT COUNT(*) FROM settlement s
JOIN txn t ON t.txn_id = s.txn_id
JOIN fx_rate f ON f.currency_id = t.currency_id AND f.rate_date = substr(t.ts_utc, 1, 10)
WHERE ABS(s.fx_rate_applied - f.rate_to_eur) / f.rate_to_eur > 0.005"""}))

    Q.append(Question(
        id="q12", stage="pre", db="v1", difficulty="hard", type="int", tolerance=0,
        knowledge_tags=["SETTLEMENT", "FX_RATE_DATE", "CONFIG_CHANGE", "LOG_WINDOW"], answer_format="integer change_id",
        text=(f"Call a settlement 'mis-rated' if |fx_rate_applied - R| / R > 0.005, where R is the official FX rate (EUR "
              f"per unit of the transaction's currency) for the calendar date of settled_at. Take the earliest mis-rated "
              f"settlement by settled_at. Which config change on component '{FX_STORY['component']}' was the most recent one "
              f"made strictly before that settlement time? Answer with its change_id (integer)."),
        gt_sql=f"""WITH first_bad AS (
  SELECT MIN(s.settled_at) AS ts
  FROM settlement s
  JOIN txn t ON t.txn_id = s.txn_id
  JOIN fx_rate f ON f.currency_id = t.currency_id AND f.rate_date = substr(s.settled_at, 1, 10)
  WHERE ABS(s.fx_rate_applied - f.rate_to_eur) / f.rate_to_eur > 0.005)
SELECT cc.change_id
FROM config_change cc
JOIN dim_component c ON c.component_id = cc.component_id
WHERE c.name = '{FX_STORY['component']}' AND cc.changed_at < (SELECT ts FROM first_bad)
ORDER BY cc.changed_at DESC LIMIT 1""",
        rationale=f"The first settlement with > 0.5 % deviation is in the 2025-05-14 batch; the last fx-service change before "
                  f"it is the rate_cache_ttl_seconds 300 -> 604800 change of {FX_STORY['change']['changed_at']} "
                  f"(a later log.level decoy precedes the incident's opened_at instead).",
        naive={"latest fx-service change before the fx incident's opened_at": f"""SELECT cc.change_id FROM config_change cc
JOIN incident i ON i.component_id = cc.component_id
WHERE i.code = '{inc_fx}' AND cc.changed_at < i.opened_at ORDER BY cc.changed_at DESC LIMIT 1"""}))

    Q.append(Question(
        id="q13", stage="pre", db="v1", difficulty="hard", type="str", tolerance=0,
        knowledge_tags=["HIERARCHY", "DATE_RANGE_JOIN", "FX_EXPONENT"], answer_format="group name",
        text=("Which top-level merchant group (a group without a parent group) had the highest total EUR value of CAPTURED "
              "transactions in November 2025 (2025-11-01 00:00:00 <= ts_utc < 2025-12-01 00:00:00)? Attribute each "
              "transaction to the merchant the terminal was assigned to at the time of the transaction, roll every merchant "
              "up through the whole group hierarchy to its top-level group, and convert amounts to EUR with the daily FX "
              "rate of the transaction date. Answer with the top-level group's name."),
        gt_sql=f"""WITH RECURSIVE tree(group_id, root_id) AS (
  SELECT group_id, group_id FROM dim_merchant_group WHERE parent_group_id IS NULL
  UNION ALL
  SELECT g.group_id, tree.root_id FROM dim_merchant_group g JOIN tree ON g.parent_group_id = tree.group_id)
SELECT rg.name
FROM txn t
JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id
  AND t.ts_utc >= ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc < ta.valid_to)
JOIN dim_merchant m ON m.merchant_id = ta.merchant_id
JOIN tree ON tree.group_id = m.group_id
JOIN dim_merchant_group rg ON rg.group_id = tree.root_id
{FX_V1}
{CAPTURED}
WHERE s.code = 'CAPTURED'
  AND t.ts_utc >= '2025-11-01 00:00:00' AND t.ts_utc < '2025-12-01 00:00:00'
GROUP BY rg.name ORDER BY SUM({EUR_V1}) DESC LIMIT 1""",
        rationale="Most merchants hang off level-3 chains; only one flagship store per holding is attached directly to the "
                  "top-level group, so without the roll-up the ranking is driven by those few stores.",
        naive={"only merchants attached directly to a top-level group": f"""SELECT rg.name FROM txn t
JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id AND t.ts_utc >= ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc < ta.valid_to)
JOIN dim_merchant m ON m.merchant_id = ta.merchant_id
JOIN dim_merchant_group rg ON rg.group_id = m.group_id AND rg.parent_group_id IS NULL
{FX_V1}
{CAPTURED}
WHERE s.code = 'CAPTURED' AND t.ts_utc >= '2025-11-01 00:00:00' AND t.ts_utc < '2025-12-01 00:00:00'
GROUP BY rg.name ORDER BY SUM({EUR_V1}) DESC LIMIT 1"""}))

    Q.append(Question(
        id="q14", stage="pre", db="v1", difficulty="medium", type="str", tolerance=0,
        knowledge_tags=["CODE_DICT_VERSION", "TERMINAL_MODEL", "TREND"], answer_format="YYYY-MM",
        text=("For terminals whose model belongs to firmware family 'OSX-3', what was the first calendar month of 2025 in "
              "which the monthly decline rate exceeded 9.0 %? A transaction is declined if its response code is flagged as "
              "a decline in the response-code dictionary version valid at the transaction time; monthly decline rate = "
              "declined / all transactions of these terminals in that month. Answer in the format YYYY-MM."),
        gt_sql=f"""SELECT month FROM (
  SELECT strftime('%Y-%m', t.ts_utc) AS month, AVG(rc.is_decline) AS rate
  FROM txn t
  {MODEL}
  {RC_VERSIONED}
  WHERE mo.firmware_family = 'OSX-3'
  GROUP BY month)
WHERE rate > 0.09
ORDER BY month LIMIT 1""",
        rationale="Firmware 3.7.2 was pushed to the OSX-3 fleet on 2025-08-04 02:00 UTC; the family's decline rate jumps "
                  "from ~6.5 % to ~10.5 % in August and stays there.",
        naive={"always use scheme_version 1": f"""SELECT month FROM (
  SELECT strftime('%Y-%m', t.ts_utc) AS month, AVG(rc.is_decline) AS rate FROM txn t
  {MODEL}
  JOIN response_code_dict rc ON rc.code = t.response_code AND rc.scheme_version = 1
  WHERE mo.firmware_family = 'OSX-3' GROUP BY month) WHERE rate > 0.09 ORDER BY month LIMIT 1"""}))

    # ------------------------------------------------------------------ post-drift (v2 schema)
    Q.append(Question(
        id="q15", stage="post", db="v2", difficulty="hard", type="float", tolerance=2500.0,
        knowledge_tags=["HIERARCHY", "DATE_RANGE_JOIN", "FX_EXPONENT", "SCHEMA_DRIFT"], answer_format="number (EUR, 2 decimals)",
        text=("What was the total value in EUR of CAPTURED transactions in 2025 attributed to the top-level merchant group "
              "'Aurora Collective' including all of its sub-groups at any depth? Attribute each transaction to the merchant "
              "the terminal was linked to at the time of the transaction, and convert amounts to EUR with the daily FX rate "
              "of the transaction date. Answer with one number in EUR rounded to 2 decimals."),
        gt_sql=f"""{hier('Aurora Collective')}
SELECT ROUND(SUM({EUR_V2}), 2) AS eur_total
FROM txn t
{ASSIGN_V2}
{FX_V2}
{CAPTURED}
WHERE s.code = 'CAPTURED'""",
        rationale="Same knowledge as q03/q13 under the renamed schema (terminal_merchant_link.start_ts/end_ts, "
                  "dim_merchant.merchant_group_id, fx_rate_daily.eur_per_unit); the coffee chain's H1 volume belongs to "
                  "Aurora only through the historical link.",
        naive={"join on current link (end_ts IS NULL)": f"""{hier('Aurora Collective')}
SELECT ROUND(SUM({EUR_V2}), 2) FROM txn t
{ASSIGN_V2_NAIVE}
{FX_V2}
{CAPTURED}
WHERE s.code = 'CAPTURED'"""}))

    Q.append(Question(
        id="q16", stage="post", db="v2", difficulty="medium", type="str", tolerance=0,
        knowledge_tags=["ISO_WEEK", "LOG_SPLIT", "SCHEMA_DRIFT"], answer_format="YYYY-Www",
        text=(f"Which ISO-8601 week of 2025 had the largest number of ERROR-level service events for component "
              f"'{BAD_DEPLOY['component']}'? Consider all service events of the whole year 2025. Answer in the format "
              f"YYYY-Www, e.g. 2025-W07."),
        gt_sql=f"""WITH ev AS (
  SELECT ts_utc, component_id, level FROM service_event_h1
  UNION ALL
  SELECT ts_utc, component_id, level FROM service_event_h2)
SELECT {ISO_WEEK.format(c='e.ts_utc')} AS iso_week
FROM ev e JOIN dim_component c ON c.component_id = e.component_id
WHERE c.name = '{BAD_DEPLOY['component']}' AND e.level = 'ERROR'
GROUP BY iso_week ORDER BY COUNT(*) DESC LIMIT 1""",
        rationale="The log table is split into service_event_h1/h2; the March release incident (W11) has more ERRORs than "
                  "the October capacity incident (W41), which is the maximum if only h2 is read.",
        naive={"service_event_h2 only": f"""SELECT {ISO_WEEK.format(c='e.ts_utc')} AS iso_week
FROM service_event_h2 e JOIN dim_component c ON c.component_id = e.component_id
WHERE c.name = '{BAD_DEPLOY['component']}' AND e.level = 'ERROR' GROUP BY iso_week ORDER BY COUNT(*) DESC LIMIT 1""",
               "strftime('%W') instead of ISO week (both halves)": f"""WITH ev AS (SELECT ts_utc, component_id, level FROM service_event_h1 UNION ALL SELECT ts_utc, component_id, level FROM service_event_h2)
SELECT {NAIVE_WEEK.format(c='e.ts_utc')} FROM ev e JOIN dim_component c ON c.component_id = e.component_id
WHERE c.name = '{BAD_DEPLOY['component']}' AND e.level = 'ERROR' GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1"""}))

    Q.append(Question(
        id="q17", stage="post", db="v2", difficulty="hard", type="float", tolerance=0.0005,
        knowledge_tags=["CODE_DICT_VERSION", "TERMINAL_MODEL", "SCHEMA_DRIFT"], answer_format="decimal fraction, 4 decimals",
        text=("For terminal model 'Lane 3000X', what was the decline rate in November 2025 "
              "(2025-11-01 00:00:00 <= ts_utc < 2025-12-01 00:00:00)? A transaction counts as declined if its response "
              "code is flagged as a decline in the response-code dictionary version that was valid at the transaction's "
              "timestamp. Decline rate = declined / all transactions of that model in the month (any status). Answer as a "
              "decimal fraction rounded to 4 decimals."),
        gt_sql=f"""SELECT ROUND(AVG(rc.is_decline), 4) AS decline_rate
FROM txn t
{MODEL}
{RC_VERSIONED}
WHERE mo.model_name = 'Lane 3000X'
  AND t.ts_utc >= '2025-11-01 00:00:00' AND t.ts_utc < '2025-12-01 00:00:00'""",
        rationale="Scheme version 3 (valid from 2025-10-01, present only in the migrated DB) re-maps Z1 and 91 from timeout "
                  "to decline; using the remembered version 2 under-counts declines in November.",
        naive={"scheme_version 2 (stale knowledge from before the migration)": f"""SELECT ROUND(AVG(rc.is_decline), 4) FROM txn t
{MODEL}
JOIN response_code_dict rc ON rc.code = t.response_code AND rc.scheme_version = 2
WHERE mo.model_name = 'Lane 3000X' AND t.ts_utc >= '2025-11-01 00:00:00' AND t.ts_utc < '2025-12-01 00:00:00'"""}))

    Q.append(Question(
        id="q18", stage="post", db="v2", difficulty="hard", type="int", tolerance=0,
        knowledge_tags=["INCIDENT_LINK", "LOG_WINDOW", "CONFIG_CHANGE", "LOG_SPLIT", "SCHEMA_DRIFT"], answer_format="integer change_id",
        text=(f"Incident {inc_q18} is linked to service events through correlation ids. Find the earliest ERROR-level "
              f"service event linked to this incident. Which config change on the incident's component was the most recent "
              f"one made strictly before that event? Answer with its change_id (integer)."),
        gt_sql=f"""WITH inc AS (SELECT incident_id, component_id FROM incident WHERE code = '{inc_q18}'),
ev AS (
  SELECT ts_utc, level, correlation_id FROM service_event_h1
  UNION ALL
  SELECT ts_utc, level, correlation_id FROM service_event_h2),
first_err AS (
  SELECT MIN(e.ts_utc) AS ts
  FROM ev e
  JOIN incident_link l ON l.correlation_id = e.correlation_id
  JOIN inc ON inc.incident_id = l.incident_id
  WHERE e.level = 'ERROR')
SELECT cc.change_id
FROM config_change cc JOIN inc ON inc.component_id = cc.component_id
WHERE cc.changed_at < (SELECT ts FROM first_err)
ORDER BY cc.changed_at DESC LIMIT 1""",
        rationale="The first linked ERROR is 12 minutes before opened_at; r.svensson's jvm.heap_mb change 40 minutes before "
                  "opening precedes it, while j.mueller's mitigation change 4 minutes before opening does not.",
        naive={"latest change before incident.opened_at": f"""SELECT cc.change_id FROM config_change cc
JOIN incident i ON i.component_id = cc.component_id
WHERE i.code = '{inc_q18}' AND cc.changed_at < i.opened_at ORDER BY cc.changed_at DESC LIMIT 1"""}))

    Q.append(Question(
        id="q19", stage="post", db="v2", difficulty="medium", type="str", tolerance=0,
        knowledge_tags=["FX_EXPONENT", "SETTLEMENT", "ISO_WEEK", "SCHEMA_DRIFT"], answer_format="YYYY-Www",
        text=("For every settlement, recompute the settled EUR amount in cents as ROUND(A * R * 100), where A is the "
              "transaction amount in major units of its currency and R is the official daily FX rate (EUR per unit of that "
              "currency) for the calendar date of settled_at (UTC); then take the absolute difference between this value and "
              "settled_eur_minor. Which ISO-8601 week (by settled_at) has the largest sum of these absolute differences? "
              "Answer in the format YYYY-Www."),
        gt_sql=f"""SELECT {ISO_WEEK.format(c='s.settled_at')} AS iso_week
FROM settlement s
JOIN txn t ON t.txn_id = s.txn_id
JOIN dim_currency c ON c.currency_id = t.currency_id
JOIN fx_rate_daily f ON f.currency_id = t.currency_id AND f.rate_date = substr(s.settled_at, 1, 10)
GROUP BY iso_week
ORDER BY SUM(ABS(s.settled_eur_minor - ROUND(t.amount_minor / power(10, c.exponent) * f.eur_per_unit * 100))) DESC
LIMIT 1""",
        rationale="Outside the stale-cache window the recomputation matches exactly; six of the seven stale settlement "
                  "batches (2025-05-13..18) fall into ISO week 2025-W20.",
        naive={"strftime('%W') instead of ISO week": f"""SELECT {NAIVE_WEEK.format(c='s.settled_at')} AS wk
FROM settlement s JOIN txn t ON t.txn_id = s.txn_id JOIN dim_currency c ON c.currency_id = t.currency_id
JOIN fx_rate_daily f ON f.currency_id = t.currency_id AND f.rate_date = substr(s.settled_at, 1, 10)
GROUP BY wk ORDER BY SUM(ABS(s.settled_eur_minor - ROUND(t.amount_minor / power(10, c.exponent) * f.eur_per_unit * 100))) DESC LIMIT 1"""}))

    Q.append(Question(
        id="q20", stage="post", db="v2", difficulty="hard", type="int", tolerance=0,
        knowledge_tags=["HIERARCHY", "DATE_RANGE_JOIN", "SCHEMA_DRIFT"], answer_format="integer",
        text=("How many distinct terminals were linked to a merchant of merchant group 'Borealis Retail AG' or any of its "
              "sub-groups at some moment during May 2025, i.e. the terminal-merchant link interval overlaps "
              "[2025-05-01 00:00:00, 2025-06-01 00:00:00)? Answer with an integer."),
        gt_sql=f"""{hier('Borealis Retail AG')}
SELECT COUNT(DISTINCT tl.terminal_id) AS n_terminals
FROM terminal_merchant_link tl
JOIN dim_merchant m ON m.merchant_id = tl.merchant_id
JOIN grp ON grp.group_id = m.merchant_group_id
WHERE tl.start_ts < '2025-06-01 00:00:00'
  AND (tl.end_ts IS NULL OR tl.end_ts > '2025-05-01 00:00:00')""",
        rationale="The 44 ex-Aurora coffee terminals were linked to Borealis merchants only from 2025-06-16, so they must "
                  "not be counted for May; the current-link view includes them.",
        naive={"current links only (end_ts IS NULL)": f"""{hier('Borealis Retail AG')}
SELECT COUNT(DISTINCT tl.terminal_id) FROM terminal_merchant_link tl
JOIN dim_merchant m ON m.merchant_id = tl.merchant_id JOIN grp ON grp.group_id = m.merchant_group_id
WHERE tl.end_ts IS NULL"""}))
    return Q
