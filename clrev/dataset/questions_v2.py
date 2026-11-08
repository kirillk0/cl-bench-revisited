"""Question catalogue v2 ("hard wording"): data/questions_v2.json.

Same database, same ground truth for q01..q20, but the texts no longer explain HOW the
schema encodes the concepts (effective-dated terminal assignments, versioned response-code
dictionary, currency exponents, incident <-> event linkage).  The metric itself stays
unambiguous (interval bounds, UTC, rounding, status, "including sub-groups at any level").
Six new investigative / trend questions (q21..q26) require scanning candidates instead of
following a prescribed path.

Every question carries ``naive_variants`` — typical wrong approaches with their SQL — so
that model errors can be classified; ``candidates_sql`` records the margin between the
winning candidate and the runner-up for "which X" questions.

Sequence order (= run order; the runner swaps the DB after position ``drift_after``):
  pre-drift  (v1 DB): q01..q14, q21, q22, q23, q24      -> drift_after = 18
  post-drift (v2 DB): q15..q20, q25, q26
"""
from __future__ import annotations

import copy

from .common import Dataset
from .questions import (
    ASSIGN_V1,
    ASSIGN_V1_NAIVE,
    ASSIGN_V2,
    CAPTURED,
    EUR_V1,
    EUR_V2,
    FX_V1,
    FX_V2,
    ISO_WEEK,
    MODEL,
    NAIVE_WEEK,
    RC_VERSIONED,
    Question,
    hier,
)
from .stories import BAD_DEPLOY, FX_STORY, OUTAGE, SEASONAL_GROUP

PRE_ORDER = ["q01", "q02", "q03", "q04", "q05", "q06", "q07", "q08", "q09", "q10", "q11", "q12", "q13", "q14",
             "q21", "q22", "q23", "q24"]
POST_ORDER = ["q15", "q16", "q17", "q18", "q19", "q20", "q25", "q26"]
DRIFT_AFTER = len(PRE_ORDER)

RC_V1_ONLY = "JOIN response_code_dict rc ON rc.code = t.response_code AND rc.scheme_version = 1"
RC_V2_ONLY = "JOIN response_code_dict rc ON rc.code = t.response_code AND rc.scheme_version = 2"
NO_EXP_V1 = "t.amount_minor / 100.0 * f.rate_to_eur"
NO_EXP_V2 = "t.amount_minor / 100.0 * f.eur_per_unit"
EV_V2 = "(SELECT ts_utc, component_id, level, event_type_id, correlation_id FROM service_event_h1\n   UNION ALL SELECT ts_utc, component_id, level, event_type_id, correlation_id FROM service_event_h2)"

# Decline / timeout definitions in business language (no mention of dictionary versions).
DECLINED = ("A transaction is declined when its response code means a decline (approvals and technical "
            "timeouts are not declines).")
TIMED_OUT = ("A transaction timed out when its response code means a technical timeout (as opposed to an "
             "approval or a decline).")
FX_CONV = "Convert each transaction to EUR at the official daily FX rate of the transaction date."
SUBGROUPS = "including all of its sub-groups at any level"


def _v(description: str, sql: str) -> dict:
    return {"description": description, "sql": sql}


# ----------------------------------------------------------------------------- reformulated texts (q01..q20)
def _texts(thr: int, inc: dict) -> dict[str, str]:
    g = SEASONAL_GROUP["group"]
    return {
        "q01": ("What was the total value in EUR of CAPTURED transactions timestamped on 2025-03-14 UTC "
                "(2025-03-14 00:00:00 <= timestamp < 2025-03-15 00:00:00)? " + FX_CONV +
                " Answer with one number in EUR rounded to 2 decimals, e.g. 12345.67."),
        "q02": (f"Which ISO-8601 week of 2025 had the most transactions (any status) for merchant group '{g}', "
                f"{SUBGROUPS}? Answer in the format YYYY-Www, e.g. 2025-W07."),
        "q03": ("What was the total value in EUR of CAPTURED transactions of merchant group 'Aurora Hospitality' "
                f"({SUBGROUPS}) in the first half of 2025 (2025-01-01 00:00:00 <= timestamp < 2025-07-01 00:00:00)? "
                + FX_CONV + " Answer with one number in EUR rounded to 2 decimals."),
        "q04": ("What was the decline rate of terminal model 'P400' in August 2025 "
                "(2025-08-01 00:00:00 <= timestamp < 2025-09-01 00:00:00)? Decline rate = declined transactions / all "
                "transactions of that model in the month (any status). " + DECLINED +
                " Answer as a decimal fraction rounded to 4 decimals, e.g. 0.0712."),
        "q05": ("Among terminal firmware families with at least 10,000 transactions in Q4 2025 "
                "(2025-10-01 00:00:00 <= timestamp < 2026-01-01 00:00:00), which one had the highest decline rate? "
                "Decline rate = declined / all transactions of the family in Q4 (any status). " + DECLINED +
                " Answer with the firmware family name exactly as stored."),
        "q06": (f"For merchant group '{g}' ({SUBGROUPS}), what was the first calendar month of 2025 in which the total "
                f"EUR value of its CAPTURED transactions exceeded {thr:,} EUR? " + FX_CONV +
                " Answer in the format YYYY-MM."),
        "q07": (f"Take the earliest ERROR-level log event that is recorded as belonging to incident {inc['bad_deploy']}. "
                "Which release of the incident's component was in production at that moment, i.e. the most recent "
                "deployment of that component strictly before the event? Answer with the version string exactly as stored."),
        "q08": (f"Release '{BAD_DEPLOY['version']}' of component '{BAD_DEPLOY['component']}' was deployed at some time T. "
                f"For transactions on route '{BAD_DEPLOY['route_code']}' (all statuses), divide the mean latency in "
                "milliseconds over [T, T + 120 minutes) by the mean latency over [T - 120 minutes, T). "
                "Answer with the ratio rounded to 2 decimals."),
        "q09": (f"During incident {inc['outage']} (from the time it was opened, inclusive, to the time it was closed, "
                f"exclusive), what share of transactions on the routes of acquirer '{OUTAGE['acquirer']}' timed out? "
                "Share = timed-out transactions / all transactions on those routes in the window (any status). "
                + TIMED_OUT + " Answer as a decimal fraction rounded to 4 decimals."),
        "q10": ("Consider every deployment and every configuration change as a 'change' made by an operator on a "
                "component. An incident counts as preceded by a change if the change was made on the incident's "
                "component between 60 minutes before the incident was opened and the opening time itself (both "
                "inclusive). Which operator has the largest number of distinct incidents preceded by their changes? "
                "Answer with the operator's login."),
        "q11": ("How many settlements were converted at an FX rate that deviates by more than 0.5 % from the official "
                "daily rate, i.e. |applied rate - R| / R > 0.005 where R is the official rate of the transaction's "
                "currency on the UTC calendar date of the settlement? Answer with an integer."),
        "q12": ("Call a settlement 'mis-rated' if the FX rate applied to it deviates by more than 0.5 % from the "
                "official daily rate of its currency on the UTC calendar date of the settlement (|applied - R| / R > "
                f"0.005). Which configuration change on component '{FX_STORY['component']}' was the most recent one made "
                "strictly before the earliest mis-rated settlement? Answer with its change_id (integer)."),
        "q13": ("Which top-level merchant group (a group without a parent group) had the highest total EUR value of "
                "CAPTURED transactions in November 2025 (2025-11-01 00:00:00 <= timestamp < 2025-12-01 00:00:00), "
                "counting every merchant anywhere below it in the group hierarchy? " + FX_CONV +
                " Answer with the group's name."),
        "q14": ("For terminals of firmware family 'OSX-3', what was the first calendar month of 2025 in which the "
                "monthly decline rate exceeded 9.0 %? Decline rate = declined / all transactions of these terminals in "
                "the month (any status). " + DECLINED + " Answer in the format YYYY-MM."),
        "q15": ("What was the total value in EUR of CAPTURED transactions in 2025 for the top-level merchant group "
                f"'Aurora Collective', {SUBGROUPS}? " + FX_CONV + " Answer with one number in EUR rounded to 2 decimals."),
        "q16": (f"Which ISO-8601 week of 2025 had the most ERROR-level log events from component "
                f"'{BAD_DEPLOY['component']}'? Consider the whole calendar year 2025. Answer in the format YYYY-Www, "
                "e.g. 2025-W07."),
        "q17": ("What was the decline rate of terminal model 'Lane 3000X' in November 2025 "
                "(2025-11-01 00:00:00 <= timestamp < 2025-12-01 00:00:00)? Decline rate = declined / all transactions of "
                "that model in the month (any status). " + DECLINED + " Answer as a decimal fraction rounded to 4 decimals."),
        "q18": (f"Take the earliest ERROR-level log event that is recorded as belonging to incident {inc['random_16']}. "
                "Which configuration change on the incident's component was the most recent one made strictly before "
                "that event? Answer with its change_id (integer)."),
        "q19": ("For every settlement, recompute the settled EUR amount in cents as ROUND(A * R * 100), where A is the "
                "transaction amount in currency units (e.g. 12.34 EUR, not cents) and R is the official daily FX rate of "
                "that currency on the UTC calendar date of the settlement; take the absolute difference between this "
                "value and the EUR cents actually settled. Which ISO-8601 week (by settlement time) has the largest sum "
                "of these absolute differences? Answer in the format YYYY-Www."),
        "q20": (f"How many distinct terminals belonged to a merchant of merchant group 'Borealis Retail AG' ({SUBGROUPS}) "
                "at some moment during May 2025, i.e. between 2025-05-01 00:00:00 (inclusive) and 2025-06-01 00:00:00 "
                "(exclusive)? Answer with an integer."),
    }


# ----------------------------------------------------------------------------- extra naive variants for q01..q20
def _extra_variants(thr: int, inc: dict) -> dict[str, list[dict]]:
    g = SEASONAL_GROUP["group"]
    return {
        "q02": [_v("join on the current assignment (valid_to IS NULL) instead of the assignment valid at txn time",
                   f"""{hier(g)}
SELECT {ISO_WEEK.format(c='t.ts_utc')} AS iso_week, COUNT(*) AS n FROM txn t
{ASSIGN_V1_NAIVE}
GROUP BY iso_week ORDER BY n DESC LIMIT 1""")],
        "q03": [_v("divide all amounts by 100 (ignore dim_currency.exponent)",
                   f"""{hier('Aurora Hospitality')}
SELECT ROUND(SUM({NO_EXP_V1}), 2) FROM txn t
{ASSIGN_V1}
{FX_V1}
{CAPTURED}
WHERE s.code = 'CAPTURED' AND t.ts_utc >= '2025-01-01 00:00:00' AND t.ts_utc < '2025-07-01 00:00:00'"""),
                _v("only merchants attached directly to the group (no roll-up of sub-groups)",
                   f"""SELECT ROUND(SUM({EUR_V1}), 2) FROM txn t
JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id AND t.ts_utc >= ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc < ta.valid_to)
JOIN dim_merchant m ON m.merchant_id = ta.merchant_id
JOIN dim_merchant_group g ON g.group_id = m.group_id AND g.name = 'Aurora Hospitality'
{FX_V1}
{CAPTURED}
WHERE s.code = 'CAPTURED' AND t.ts_utc >= '2025-01-01 00:00:00' AND t.ts_utc < '2025-07-01 00:00:00'""")],
        "q05": [_v("always use scheme_version 1",
                   f"""SELECT mo.firmware_family FROM txn t
{MODEL}
{RC_V1_ONLY}
WHERE t.ts_utc >= '2025-10-01 00:00:00' AND t.ts_utc < '2026-01-01 00:00:00'
GROUP BY mo.firmware_family HAVING COUNT(*) >= 10000 ORDER BY AVG(rc.is_decline) DESC LIMIT 1""")],
        "q06": [_v("join on the current assignment (valid_to IS NULL)",
                   f"""{hier(g)}
SELECT month FROM (
  SELECT strftime('%Y-%m', t.ts_utc) AS month, SUM({EUR_V1}) AS eur FROM txn t
  {ASSIGN_V1_NAIVE}
  {FX_V1}
  {CAPTURED}
  WHERE s.code = 'CAPTURED' GROUP BY month)
WHERE eur > {thr} ORDER BY month LIMIT 1"""),
                _v("divide all amounts by 100 (ignore dim_currency.exponent)",
                   f"""{hier(g)}
SELECT month FROM (
  SELECT strftime('%Y-%m', t.ts_utc) AS month, SUM({NO_EXP_V1}) AS eur FROM txn t
  {ASSIGN_V1}
  {FX_V1}
  {CAPTURED}
  WHERE s.code = 'CAPTURED' GROUP BY month)
WHERE eur > {thr} ORDER BY month LIMIT 1""")],
        "q09": [_v("status = FAILED as 'timed out' (declines counted as timeouts)",
                   f"""WITH inc AS (SELECT opened_at, closed_at FROM incident WHERE code = '{inc['outage']}')
SELECT ROUND(AVG(s.code = 'FAILED'), 4) FROM txn t
JOIN route r ON r.route_id = t.route_id JOIN dim_acquirer a ON a.acquirer_id = r.acquirer_id
{CAPTURED}
JOIN inc WHERE a.name = '{OUTAGE['acquirer']}' AND t.ts_utc >= inc.opened_at AND t.ts_utc < inc.closed_at""")],
        "q10": [_v("config changes only (ignore deployments)",
                   """WITH hits AS (
  SELECT DISTINCT cc.operator_id, i.incident_id FROM incident i
  JOIN config_change cc ON cc.component_id = i.component_id AND cc.changed_at <= i.opened_at AND cc.changed_at >= datetime(i.opened_at, '-60 minutes'))
SELECT o.login FROM hits h JOIN operator o ON o.operator_id = h.operator_id GROUP BY o.login ORDER BY COUNT(*) DESC LIMIT 1""")],
        "q11": [_v("count any difference between applied and official rate (no 0.5 % threshold)",
                   """SELECT COUNT(*) FROM settlement s JOIN txn t ON t.txn_id = s.txn_id
JOIN fx_rate f ON f.currency_id = t.currency_id AND f.rate_date = substr(s.settled_at, 1, 10)
WHERE s.fx_rate_applied <> f.rate_to_eur""")],
        "q13": [_v("join on the current assignment (valid_to IS NULL)",
                   f"""WITH RECURSIVE tree(group_id, root_id) AS (
  SELECT group_id, group_id FROM dim_merchant_group WHERE parent_group_id IS NULL
  UNION ALL
  SELECT g.group_id, tree.root_id FROM dim_merchant_group g JOIN tree ON g.parent_group_id = tree.group_id)
SELECT rg.name FROM txn t
JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id AND ta.valid_to IS NULL
JOIN dim_merchant m ON m.merchant_id = ta.merchant_id
JOIN tree ON tree.group_id = m.group_id
JOIN dim_merchant_group rg ON rg.group_id = tree.root_id
{FX_V1}
{CAPTURED}
WHERE s.code = 'CAPTURED' AND t.ts_utc >= '2025-11-01 00:00:00' AND t.ts_utc < '2025-12-01 00:00:00'
GROUP BY rg.name ORDER BY SUM({EUR_V1}) DESC LIMIT 1""")],
        "q15": [_v("only merchants attached directly to the top-level group (no roll-up)",
                   f"""SELECT ROUND(SUM({EUR_V2}), 2) FROM txn t
JOIN terminal_merchant_link tl ON tl.terminal_id = t.terminal_id AND t.ts_utc >= tl.start_ts AND (tl.end_ts IS NULL OR t.ts_utc < tl.end_ts)
JOIN dim_merchant m ON m.merchant_id = tl.merchant_id
JOIN dim_merchant_group g ON g.group_id = m.merchant_group_id AND g.name = 'Aurora Collective'
{FX_V2}
{CAPTURED}
WHERE s.code = 'CAPTURED'"""),
                _v("divide all amounts by 100 (ignore dim_currency.exponent)",
                   f"""{hier('Aurora Collective')}
SELECT ROUND(SUM({NO_EXP_V2}), 2) FROM txn t
{ASSIGN_V2}
{FX_V2}
{CAPTURED}
WHERE s.code = 'CAPTURED'""")],
        "q16": [_v("service_event_h1 only",
                   f"""SELECT {ISO_WEEK.format(c='e.ts_utc')} AS iso_week
FROM service_event_h1 e JOIN dim_component c ON c.component_id = e.component_id
WHERE c.name = '{BAD_DEPLOY['component']}' AND e.level = 'ERROR' GROUP BY iso_week ORDER BY COUNT(*) DESC LIMIT 1""")],
        "q17": [_v("always use scheme_version 1",
                   f"""SELECT ROUND(AVG(rc.is_decline), 4) FROM txn t
{MODEL}
{RC_V1_ONLY}
WHERE mo.model_name = 'Lane 3000X' AND t.ts_utc >= '2025-11-01 00:00:00' AND t.ts_utc < '2025-12-01 00:00:00'"""),
                _v("status = FAILED as 'declined'",
                   f"""SELECT ROUND(AVG(s.code = 'FAILED'), 4) FROM txn t
{MODEL}
{CAPTURED}
WHERE mo.model_name = 'Lane 3000X' AND t.ts_utc >= '2025-11-01 00:00:00' AND t.ts_utc < '2025-12-01 00:00:00'""")],
        "q18": [_v("service_event_h2 only (the incident is in November, so the first linked ERROR is found anyway)",
                   f"""WITH inc AS (SELECT incident_id, component_id FROM incident WHERE code = '{inc['random_16']}'),
first_err AS (
  SELECT MIN(e.ts_utc) AS ts FROM service_event_h2 e
  JOIN incident_link l ON l.correlation_id = e.correlation_id JOIN inc ON inc.incident_id = l.incident_id
  WHERE e.level = 'ERROR')
SELECT cc.change_id FROM config_change cc JOIN inc ON inc.component_id = cc.component_id
WHERE cc.changed_at < (SELECT ts FROM first_err) ORDER BY cc.changed_at DESC LIMIT 1""")],
        "q19": [_v("divide all amounts by 100 (ignore dim_currency.exponent)",
                   f"""SELECT {ISO_WEEK.format(c='s.settled_at')} AS iso_week
FROM settlement s JOIN txn t ON t.txn_id = s.txn_id
JOIN fx_rate_daily f ON f.currency_id = t.currency_id AND f.rate_date = substr(s.settled_at, 1, 10)
GROUP BY iso_week ORDER BY SUM(ABS(s.settled_eur_minor - ROUND(t.amount_minor / 100.0 * f.eur_per_unit * 100))) DESC LIMIT 1"""),
                _v("rate of the transaction date instead of the settlement date",
                   f"""SELECT {ISO_WEEK.format(c='s.settled_at')} AS iso_week
FROM settlement s JOIN txn t ON t.txn_id = s.txn_id JOIN dim_currency c ON c.currency_id = t.currency_id
JOIN fx_rate_daily f ON f.currency_id = t.currency_id AND f.rate_date = substr(t.ts_utc, 1, 10)
GROUP BY iso_week ORDER BY SUM(ABS(s.settled_eur_minor - ROUND(t.amount_minor / power(10, c.exponent) * f.eur_per_unit * 100))) DESC LIMIT 1""")],
        "q20": [_v("links that started in May only (start_ts within the month) instead of interval overlap",
                   f"""{hier('Borealis Retail AG')}
SELECT COUNT(DISTINCT tl.terminal_id) FROM terminal_merchant_link tl
JOIN dim_merchant m ON m.merchant_id = tl.merchant_id JOIN grp ON grp.group_id = m.merchant_group_id
WHERE tl.start_ts >= '2025-05-01 00:00:00' AND tl.start_ts < '2025-06-01 00:00:00'""")],
    }


# ----------------------------------------------------------------------------- margin (candidate) queries for q01..q20
def _candidates(inc: dict) -> dict[str, str]:
    g = SEASONAL_GROUP["group"]
    return {
        "q02": f"""{hier(g)}
SELECT {ISO_WEEK.format(c='t.ts_utc')} AS iso_week, COUNT(*) AS n FROM txn t
{ASSIGN_V1}
GROUP BY iso_week ORDER BY n DESC LIMIT 2""",
        "q05": f"""SELECT mo.firmware_family, ROUND(AVG(rc.is_decline), 4) FROM txn t
{MODEL}
{RC_VERSIONED}
WHERE t.ts_utc >= '2025-10-01 00:00:00' AND t.ts_utc < '2026-01-01 00:00:00'
GROUP BY mo.firmware_family HAVING COUNT(*) >= 10000 ORDER BY AVG(rc.is_decline) DESC LIMIT 2""",
        "q10": """WITH changes AS (
  SELECT component_id, operator_id, deployed_at AS at FROM deployment
  UNION ALL SELECT component_id, operator_id, changed_at FROM config_change),
hits AS (
  SELECT DISTINCT ch.operator_id, i.incident_id FROM incident i
  JOIN changes ch ON ch.component_id = i.component_id AND ch.at <= i.opened_at AND ch.at >= datetime(i.opened_at, '-60 minutes'))
SELECT o.login, COUNT(*) FROM hits h JOIN operator o ON o.operator_id = h.operator_id GROUP BY o.login ORDER BY COUNT(*) DESC LIMIT 2""",
        "q13": f"""WITH RECURSIVE tree(group_id, root_id) AS (
  SELECT group_id, group_id FROM dim_merchant_group WHERE parent_group_id IS NULL
  UNION ALL
  SELECT g.group_id, tree.root_id FROM dim_merchant_group g JOIN tree ON g.parent_group_id = tree.group_id)
SELECT rg.name, ROUND(SUM({EUR_V1})) FROM txn t
JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id AND t.ts_utc >= ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc < ta.valid_to)
JOIN dim_merchant m ON m.merchant_id = ta.merchant_id
JOIN tree ON tree.group_id = m.group_id
JOIN dim_merchant_group rg ON rg.group_id = tree.root_id
{FX_V1}
{CAPTURED}
WHERE s.code = 'CAPTURED' AND t.ts_utc >= '2025-11-01 00:00:00' AND t.ts_utc < '2025-12-01 00:00:00'
GROUP BY rg.name ORDER BY 2 DESC LIMIT 2""",
        "q16": f"""WITH ev AS (SELECT ts_utc, component_id, level FROM service_event_h1 UNION ALL SELECT ts_utc, component_id, level FROM service_event_h2)
SELECT {ISO_WEEK.format(c='e.ts_utc')} AS iso_week, COUNT(*) FROM ev e JOIN dim_component c ON c.component_id = e.component_id
WHERE c.name = '{BAD_DEPLOY['component']}' AND e.level = 'ERROR' GROUP BY iso_week ORDER BY 2 DESC LIMIT 2""",
        "q19": f"""SELECT {ISO_WEEK.format(c='s.settled_at')} AS iso_week,
  SUM(ABS(s.settled_eur_minor - ROUND(t.amount_minor / power(10, c.exponent) * f.eur_per_unit * 100))) AS diff_cents
FROM settlement s JOIN txn t ON t.txn_id = s.txn_id JOIN dim_currency c ON c.currency_id = t.currency_id
JOIN fx_rate_daily f ON f.currency_id = t.currency_id AND f.rate_date = substr(s.settled_at, 1, 10)
GROUP BY iso_week ORDER BY diff_cents DESC LIMIT 2""",
    }


# ----------------------------------------------------------------------------- new questions q21..q26
Q21_SQL = """SELECT d.deployment_id
FROM deployment d
WHERE d.rolled_back_at IS NOT NULL
ORDER BY (SELECT COUNT(*) FROM service_event e
          WHERE e.component_id = d.component_id AND e.level = 'ERROR'
            AND e.ts_utc >= d.deployed_at AND e.ts_utc < d.rolled_back_at) DESC
LIMIT 1"""
Q21_CAND = """SELECT d.deployment_id || ' ' || d.version,
       (SELECT COUNT(*) FROM service_event e WHERE e.component_id = d.component_id AND e.level = 'ERROR'
          AND e.ts_utc >= d.deployed_at AND e.ts_utc < d.rolled_back_at) AS n_err
FROM deployment d WHERE d.rolled_back_at IS NOT NULL ORDER BY n_err DESC LIMIT 2"""

Q22_TEMPLATE = """WITH RECURSIVE tree(group_id, anc_id) AS (
  SELECT group_id, group_id FROM dim_merchant_group
  UNION ALL
  SELECT g.group_id, tree.anc_id FROM dim_merchant_group g JOIN tree ON g.parent_group_id = tree.group_id),
div AS (
  SELECT g.group_id, g.name FROM dim_merchant_group g
  JOIN dim_merchant_group p ON p.group_id = g.parent_group_id
  WHERE p.parent_group_id IS NULL),
m2d AS (
  SELECT m.merchant_id, div.group_id AS div_id
  FROM dim_merchant m JOIN tree ON tree.group_id = m.group_id JOIN div ON div.group_id = tree.anc_id),
weeks(w) AS (SELECT 1 UNION ALL SELECT w + 1 FROM weeks WHERE w < 52),
wk AS (
  SELECT m2d.div_id, {iso} AS iso_week, COUNT(*) AS n
  FROM txn t
  {assign}
  JOIN m2d ON m2d.merchant_id = ta.merchant_id
  GROUP BY m2d.div_id, iso_week),
pts AS (
  SELECT div.group_id, div.name, weeks.w, COALESCE(wk.n, 0) AS n
  FROM div CROSS JOIN weeks
  LEFT JOIN wk ON wk.div_id = div.group_id AND wk.iso_week = '2025-W' || printf('%02d', weeks.w))
SELECT name{extra_cols}
FROM pts GROUP BY group_id
ORDER BY (COUNT(*) * SUM(w * n) - SUM(w) * SUM(n)) * 1.0 / (COUNT(*) * SUM(w * w) - SUM(w) * SUM(w)) DESC
LIMIT {limit}"""
Q22_ASSIGN = """JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id
    AND t.ts_utc >= ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc < ta.valid_to)"""
Q22_ASSIGN_NAIVE = "JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id AND ta.valid_to IS NULL"
Q22_SLOPE_COL = ", ROUND((COUNT(*) * SUM(w * n) - SUM(w) * SUM(n)) * 1.0 / (COUNT(*) * SUM(w * w) - SUM(w) * SUM(w)), 3) AS slope"


def _q22(iso: str, assign: str, limit: int = 1, extra_cols: str = "", no_hierarchy: bool = False) -> str:
    sql = Q22_TEMPLATE.format(iso=iso, assign=assign, limit=limit, extra_cols=extra_cols)
    if no_hierarchy:   # merchants attached directly to the division only
        sql = sql.replace("JOIN tree ON tree.group_id = m.group_id JOIN div ON div.group_id = tree.anc_id",
                          "JOIN div ON div.group_id = m.group_id")
    return sql


Q23_TEMPLATE = """WITH day AS (
  SELECT t.txn_id, t.terminal_id, t.ts_utc, {flag} AS is_timeout
  FROM txn t
  {join}
  WHERE t.ts_utc >= '2025-09-18 00:00:00' AND t.ts_utc < '2025-09-19 00:00:00')
SELECT COUNT(DISTINCT a.txn_id) AS n_retried
FROM day a
JOIN day b ON b.terminal_id = a.terminal_id AND b.ts_utc > a.ts_utc AND b.ts_utc <= datetime(a.ts_utc, '+90 seconds')
WHERE a.is_timeout = 1"""

Q24_SQL = """SELECT cc.change_id
FROM config_change cc
ORDER BY (SELECT COUNT(*) FROM service_event e
          WHERE e.component_id = cc.component_id AND e.level = 'ERROR'
            AND e.ts_utc >= cc.changed_at AND e.ts_utc < datetime(cc.changed_at, '+60 minutes')) DESC
LIMIT 1"""
Q24_CAND = """SELECT cc.change_id || ' ' || c.name || ' ' || cc.key || ' @ ' || cc.changed_at,
       (SELECT COUNT(*) FROM service_event e WHERE e.component_id = cc.component_id AND e.level = 'ERROR'
          AND e.ts_utc >= cc.changed_at AND e.ts_utc < datetime(cc.changed_at, '+60 minutes')) AS n_err
FROM config_change cc JOIN dim_component c ON c.component_id = cc.component_id ORDER BY n_err DESC LIMIT 2"""

Q25_TEMPLATE = """SELECT {week} AS iso_week{extra}
FROM {src} e
WHERE e.level = 'ERROR'
GROUP BY iso_week ORDER BY COUNT(*) DESC LIMIT {limit}"""

Q26_TEMPLATE = """WITH leaf AS (
  SELECT g.group_id, g.name FROM dim_merchant_group g
  WHERE NOT EXISTS (SELECT 1 FROM dim_merchant_group x WHERE x.parent_group_id = g.group_id))
SELECT leaf.name{extra}
FROM txn t
{link}
JOIN dim_merchant m ON m.merchant_id = tl.merchant_id
JOIN leaf ON leaf.group_id = m.merchant_group_id
GROUP BY leaf.group_id
ORDER BY SUM(t.ts_utc < '2025-07-01 00:00:00') - SUM(t.ts_utc >= '2025-07-01 00:00:00') DESC
LIMIT {limit}"""
Q26_LINK = """JOIN terminal_merchant_link tl ON tl.terminal_id = t.terminal_id
  AND t.ts_utc >= tl.start_ts AND (tl.end_ts IS NULL OR t.ts_utc < tl.end_ts)"""
Q26_LINK_NAIVE = "JOIN terminal_merchant_link tl ON tl.terminal_id = t.terminal_id AND tl.end_ts IS NULL"
Q26_LOSS = ", SUM(t.ts_utc < '2025-07-01 00:00:00') - SUM(t.ts_utc >= '2025-07-01 00:00:00') AS loss"


def _new_questions() -> list[Question]:
    Q: list[Question] = []
    Q.append(Question(
        id="q21", stage="pre", db="v1", difficulty="medium", type="int", tolerance=0,
        knowledge_tags=["DEPLOYMENT", "ROLLBACK_WINDOW", "LOG_WINDOW", "CANDIDATE_SCAN"], answer_format="integer deployment_id",
        text=("Of all releases (deployments) in 2025 that were later rolled back, which one was live - from its "
              "deployment time (inclusive) to its rollback time (exclusive) - while its own component logged the most "
              "ERROR-level events? Answer with the deployment_id (integer)."),
        gt_sql=Q21_SQL, candidates_sql=Q21_CAND,
        rationale=("Story 1: the bad auth-router release v4.18.0 (deployment_id 31) was live 14:05-16:30 on 2025-03-11 "
                   "and produced ~300 ERROR events; the other rolled-back releases (8 % of random deployments) only see "
                   "baseline noise (<= 2 errors). The '+restart' decoy was never rolled back."),
        naive_variants=[
            _v("ERROR events in a fixed 60-minute window after every deployment (ignoring rollbacks)",
               """SELECT d.deployment_id FROM deployment d
ORDER BY (SELECT COUNT(*) FROM service_event e WHERE e.component_id = d.component_id AND e.level = 'ERROR'
          AND e.ts_utc >= d.deployed_at AND e.ts_utc < datetime(d.deployed_at, '+60 minutes')) DESC LIMIT 1"""),
            _v("ERROR events of all components (not only the deployed one) during the live window",
               """SELECT d.deployment_id FROM deployment d WHERE d.rolled_back_at IS NOT NULL
ORDER BY (SELECT COUNT(*) FROM service_event e WHERE e.level = 'ERROR' AND e.ts_utc >= d.deployed_at AND e.ts_utc < d.rolled_back_at) DESC LIMIT 1"""),
        ]))

    Q.append(Question(
        id="q22", stage="pre", db="v1", difficulty="hard", type="str", tolerance=0,
        knowledge_tags=["HIERARCHY", "DATE_RANGE_JOIN", "ISO_WEEK", "TREND", "REGRESSION", "CANDIDATE_SCAN"],
        answer_format="group name",
        text=("Among second-level merchant groups (divisions, i.e. groups whose parent is a top-level group), which one "
              "had the strongest upward trend in weekly transaction count during 2025, counting transactions of any "
              "status for all merchants anywhere below the group? Trend = ordinary-least-squares slope of the weekly "
              "count against the ISO week number over the 52 weeks 2025-W01 .. 2025-W52 (x = 1..52; a week without "
              "transactions counts as 0; 2025-W01 contains only 1-5 January and is taken as is). Answer with the "
              "group's name."),
        gt_sql=_q22(ISO_WEEK.format(c="t.ts_utc"), Q22_ASSIGN),
        candidates_sql=_q22(ISO_WEEK.format(c="t.ts_utc"), Q22_ASSIGN, limit=2, extra_cols=Q22_SLOPE_COL),
        rationale=(f"Story 5: '{SEASONAL_GROUP['group']}' grows linearly by +{SEASONAL_GROUP['growth']:.0%} over the year "
                   "(plus a December bump); all other divisions are flat. Its merchants hang off level-3 chains, so the "
                   "division's weekly counts need the hierarchy roll-up and the assignment valid at transaction time. "
                   "The runner-up (Borealis Cafés & Bakeries) owes its slope to the 44 coffee-chain terminals it "
                   "received on 2025-06-16."),
        naive_variants=[
            _v("only merchants attached directly to the division (no roll-up of chains)",
               _q22(ISO_WEEK.format(c="t.ts_utc"), Q22_ASSIGN, no_hierarchy=True)),
            _v("join on the current assignment (valid_to IS NULL)",
               _q22(ISO_WEEK.format(c="t.ts_utc"), Q22_ASSIGN_NAIVE)),
            _v("strftime('%W') instead of ISO week (week numbers shifted by one)",
               _q22("strftime('%Y-W%W', t.ts_utc)", Q22_ASSIGN)),
        ]))

    Q.append(Question(
        id="q23", stage="pre", db="v1", difficulty="hard", type="int", tolerance=0,
        knowledge_tags=["CODE_DICT_VERSION", "SELF_JOIN", "TIME_WINDOW", "OUTAGE"], answer_format="integer",
        text=("On 2025-09-18 (UTC day, 2025-09-18 00:00:00 <= timestamp < 2025-09-19 00:00:00), how many timed-out "
              "transactions were retried, i.e. followed by another transaction on the same terminal within 90 seconds "
              "(0 < delta <= 90 s)? " + TIMED_OUT + " Count each timed-out transaction at most once. Answer with an integer."),
        gt_sql=Q23_TEMPLATE.format(flag="rc.is_timeout", join=RC_VERSIONED),
        rationale=(f"Story 3: during the {OUTAGE['acquirer']} outage half of the timed-out payments were retried 20-90 s "
                   "later. 15 % of the outage timeouts carry code '96', which is a timeout only in dictionary version 2 "
                   "(valid from 2025-07-01); with version-1 semantics those retries are missed. Outside the outage, "
                   "same-terminal follow-ups within 90 s are practically non-existent (<= 1 per day)."),
        naive_variants=[
            _v("always use scheme_version 1 (code 96 treated as a decline)",
               Q23_TEMPLATE.format(flag="rc.is_timeout", join=RC_V1_ONLY)),
            _v("status = FAILED as 'timed out' (declines included)",
               Q23_TEMPLATE.format(flag="(s.code = 'FAILED')", join=CAPTURED)),
        ]))

    Q.append(Question(
        id="q24", stage="pre", db="v1", difficulty="medium", type="int", tolerance=0,
        knowledge_tags=["CONFIG_CHANGE", "LOG_WINDOW", "CANDIDATE_SCAN"], answer_format="integer change_id",
        text=("Which configuration change of 2025 was followed by the most ERROR-level log events from the same "
              "component within the 60 minutes after the change (change time inclusive, change time + 60 minutes "
              "exclusive)? Answer with the change_id (integer)."),
        gt_sql=Q24_SQL, candidates_sql=Q24_CAND,
        rationale=("Story 7: r.svensson's feature.new_router change on risk-engine (2025-07-15 09:41) precedes the SEV2 "
                   "capacity incident INC-2025-0013 by 44 minutes and is followed by 40 ERROR events within the hour; "
                   "the runner-up is his autoscale change before INC-2025-0003 (30). Random config changes are kept "
                   ">= 75 min away from incidents of their component, and deployments are not configuration changes "
                   "(the '+restart' re-deploy would otherwise win)."),
        naive_variants=[
            _v("count log events of every level (INFO/WARN included) in the window",
               """SELECT cc.change_id FROM config_change cc
ORDER BY (SELECT COUNT(*) FROM service_event e WHERE e.component_id = cc.component_id
          AND e.ts_utc >= cc.changed_at AND e.ts_utc < datetime(cc.changed_at, '+60 minutes')) DESC LIMIT 1"""),
            _v("ERROR events of all components (not only the changed one) in the window",
               """SELECT cc.change_id FROM config_change cc
ORDER BY (SELECT COUNT(*) FROM service_event e WHERE e.level = 'ERROR'
          AND e.ts_utc >= cc.changed_at AND e.ts_utc < datetime(cc.changed_at, '+60 minutes')) DESC LIMIT 1"""),
            _v("24-hour window instead of 60 minutes",
               """SELECT cc.change_id FROM config_change cc
ORDER BY (SELECT COUNT(*) FROM service_event e WHERE e.component_id = cc.component_id AND e.level = 'ERROR'
          AND e.ts_utc >= cc.changed_at AND e.ts_utc < datetime(cc.changed_at, '+24 hours')) DESC LIMIT 1"""),
        ]))

    Q.append(Question(
        id="q25", stage="post", db="v2", difficulty="medium", type="str", tolerance=0,
        knowledge_tags=["ISO_WEEK", "LOG_SPLIT", "SCHEMA_DRIFT", "CANDIDATE_SCAN"], answer_format="YYYY-Www",
        text=("Which ISO-8601 week of 2025 had the most ERROR-level log events across all components? Consider the "
              "whole calendar year 2025. Answer in the format YYYY-Www."),
        gt_sql=Q25_TEMPLATE.format(week=ISO_WEEK.format(c="e.ts_utc"), extra="", src=EV_V2, limit=1),
        candidates_sql=Q25_TEMPLATE.format(week=ISO_WEEK.format(c="e.ts_utc"), extra=", COUNT(*) AS n", src=EV_V2, limit=2),
        rationale=(f"Story 3: the {OUTAGE['acquirer']} outage (2025-09-18, W38) produces ~840 acquirer-gateway ERRORs in "
                   "one week, far ahead of the March release incident (W11). In the migrated schema the log is split "
                   "into service_event_h1/h2: reading only h1 gives W11, strftime('%W') gives W37."),
        naive_variants=[
            _v("service_event_h1 only",
               Q25_TEMPLATE.format(week=ISO_WEEK.format(c="e.ts_utc"), extra="", src="service_event_h1", limit=1)),
            _v("service_event_h2 only",
               Q25_TEMPLATE.format(week=ISO_WEEK.format(c="e.ts_utc"), extra="", src="service_event_h2", limit=1)),
            _v("strftime('%W') instead of ISO week (both halves)",
               Q25_TEMPLATE.format(week=NAIVE_WEEK.format(c="e.ts_utc"), extra="", src=EV_V2, limit=1)),
        ]))

    Q.append(Question(
        id="q26", stage="post", db="v2", difficulty="hard", type="str", tolerance=0,
        knowledge_tags=["HIERARCHY", "DATE_RANGE_JOIN", "TREND", "SCHEMA_DRIFT", "CANDIDATE_SCAN"], answer_format="group name",
        text=("Among the lowest-level merchant groups (groups that have no sub-groups), which one lost the most "
              "transactions between the first and the second half of 2025? Loss = number of transactions (any status) "
              "with timestamp < 2025-07-01 00:00:00 minus the number with timestamp >= 2025-07-01 00:00:00. Answer "
              "with the group's name."),
        gt_sql=Q26_TEMPLATE.format(extra="", link=Q26_LINK, limit=1),
        candidates_sql=Q26_TEMPLATE.format(extra=Q26_LOSS, link=Q26_LINK, limit=2),
        rationale=("Story 6: the 44 terminals of 'Aurora Coffee Chain' were re-linked to Borealis merchants on "
                   "2025-06-16, so with the historical link the chain has ~5,300 transactions in H1 and none in H2. "
                   "With the current link (end_ts IS NULL) the chain has no transactions at all and the 'loss' ranking "
                   "is pure noise (Borealis Online, -12)."),
        naive_variants=[
            _v("join on the current link (end_ts IS NULL)",
               Q26_TEMPLATE.format(extra="", link=Q26_LINK_NAIVE, limit=1)),
        ]))
    return Q


def build_questions_v2(ds: Dataset, v1_questions: list[Question]) -> list[Question]:
    """Return the 26 v2 questions in run order (pre-drift first, then post-drift)."""
    inc = ds.meta["incident_by_tag"]
    thr = ds.meta["q06_threshold"]
    texts = _texts(thr, inc)
    extra = _extra_variants(thr, inc)
    cands = _candidates(inc)
    by_id: dict[str, Question] = {}
    for q1 in v1_questions:
        q = copy.deepcopy(q1)
        q.text = texts[q.id]
        q.naive_variants = [_v(label, sql) for label, sql in q1.naive.items()] + extra.get(q.id, [])
        q.candidates_sql = cands.get(q.id)
        q.naive = {}
        q.answer = None          # re-derived from gt_sql by run_ground_truth (must equal the v1 answer)
        by_id[q.id] = q
    for q in _new_questions():
        by_id[q.id] = q
    ordered = [by_id[i] for i in PRE_ORDER + POST_ORDER]
    assert len(ordered) == len(by_id) == 26
    for pos, q in enumerate(ordered, 1):
        assert (q.stage == "pre") == (pos <= DRIFT_AFTER), (q.id, pos)
        assert (q.db == "v1") == (q.stage == "pre"), q.id
    return ordered
