"""Render data/STORIES.md — the private description of the planted phenomena and validation tables."""
from __future__ import annotations

from .common import Dataset
from .questions import Question
from .stories import (BAD_DEPLOY, BAD_DEPLOY_NOISE_ERROR_TS, BAD_DEPLOY_PRELUDE_CFG, BAD_DEPLOY_RESTART, FIRMWARE,
                      FX_STORY, MOVE, OPERATOR_STORY, OUTAGE, RANDOM_MOVE_SHARE, RC_V2_FROM, RC_V3_FROM, SEASONAL_GROUP)
from .reference import RC_V2_CHANGES, RC_V3_CHANGES


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.4f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.2f}"
    return str(v)


def render(ds: Dataset, questions: list[Question], stats: dict, timings: list[dict], naive: list[dict],
           independent: list[dict], row_counts: dict, sizes: dict) -> str:
    inc = ds.meta["incident_by_tag"]
    chg = ds.meta["change_by_tag"]
    dep = ds.meta["deploy_by_tag"]
    L: list[str] = []
    w = L.append
    w("# PayOps dataset — planted stories, ground truth and validation\n")
    w("> Private documentation for the experiment. **Never show this file to the models.**\n")
    w("Generated deterministically by `python -m clrev.dataset.build --out data/` (seed 20261108).\n")
    w("## Conventions\n")
    w("* All timestamps are UTC text `YYYY-MM-DD HH:MM:SS`; all validity intervals are half-open `[from, to)`, `NULL` = open.")
    w("* `txn.amount_minor` is in minor units of `txn.currency_id`; the number of minor digits is `dim_currency.exponent` "
      "(EUR/USD/... = 2, **JPY = 0, KWD = 3**).")
    w("* `fx_rate.rate_to_eur` (v2: `fx_rate_daily.eur_per_unit`) = EUR value of one unit of the currency on `rate_date`; "
      "daily rows for every currency incl. EUR = 1.0, 2025-01-01 .. 2026-01-07.")
    w("* `terminal_assignment` (v2: `terminal_merchant_link`) is effective-dated: terminals move between merchants, "
      f"so historic attribution needs a date-range join. {len(ds.meta['moved_terminals'])} terminals moved in the planted "
      f"acquisition, {len(ds.meta['random_moves'])} more moved once at random dates ({RANDOM_MOVE_SHARE:.0%} of the fleet).")
    w("* `response_code_dict` is versioned by `scheme_version` with `valid_from/valid_to`; the raw codes in `txn.response_code` "
      "never change, only their interpretation does. `txn_status_dict` only knows CAPTURED / AUTHORIZED / FAILED / REVERSED / "
      "REFUNDED — FAILED covers both declines and timeouts, so the dictionary is the only way to tell them apart.")
    w("* `incident_link(incident_id, correlation_id)` connects incidents to `service_event.correlation_id`; most incident bursts "
      "also contain unlinked events with other correlation ids, and components emit baseline ERRORs all year.")
    w("* Merchant group hierarchy: 3 levels (holding → division → chain). Merchants mostly hang off chains, but every holding "
      "has one flagship store attached directly and ~70 % of divisions have a direct store too.\n")

    w("## Response code dictionary versions\n")
    w(f"* **v1** valid `2025-01-01` .. `{RC_V2_FROM}` (exclusive).")
    w(f"* **v2** valid from `{RC_V2_FROM}` (in payops.db open-ended; in payops_v2.db until `{RC_V3_FROM}`):")
    for c, (m, d, t) in RC_V2_CHANGES.items():
        w(f"  * `{c}` → \"{m}\" is_decline={d} is_timeout={t}")
    w(f"* **v3** (payops_v2.db only) valid from `{RC_V3_FROM}`:")
    for c, (m, d, t) in RC_V3_CHANGES.items():
        w(f"  * `{c}` → \"{m}\" is_decline={d} is_timeout={t}")
    w("")

    w("## Story 1 — bad deployment of auth-router → latency/timeout spike on one route → incident\n")
    dw, db = stats["deploy_window"], stats["deploy_before"]
    w(f"* Deployment `{BAD_DEPLOY['version']}` of `{BAD_DEPLOY['component']}` (deployment_id {dep['bad']}) by "
      f"`{BAD_DEPLOY['operator']}` at **{BAD_DEPLOY['deployed_at']}**, rolled back {BAD_DEPLOY['rolled_back_at']}.")
    w(f"* Effect window {BAD_DEPLOY['effect_from']} .. {BAD_DEPLOY['effect_to']} on route `{BAD_DEPLOY['route_code']}` "
      f"(route_id {ds.meta['bad_route_id']}) only: latency ×{BAD_DEPLOY['latency_mult']}, {BAD_DEPLOY['timeout_prob']:.0%} "
      f"'Z1' processor timeouts.")
    w(f"  * data: {dw[0]} txns in the window, mean latency {dw[1]:.0f} ms, Z1 share {dw[2]:.3f}; the 145 min before: "
      f"{db[0]} txns, mean latency {db[1]:.0f} ms, Z1 share {db[2]:.3f}.")
    w(f"* Logs: WARN LATENCY_HIGH from {BAD_DEPLOY['warn_from']}, first **linked ERROR at {BAD_DEPLOY['first_error_ts']}** "
      f"(POOL_EXHAUSTED, correlation id in incident_link); {stats['deploy_errors']} linked ERROR events in total. "
      f"An unlinked baseline ERROR on the same component at {BAD_DEPLOY_NOISE_ERROR_TS} is noise.")
    w(f"* Incident **{inc['bad_deploy']}** opened {BAD_DEPLOY['incident_opened']}, closed {BAD_DEPLOY['incident_closed']} "
      f"({BAD_DEPLOY['severity']}, {BAD_DEPLOY['root_cause']}).")
    w(f"* Decoys: config change `{BAD_DEPLOY_PRELUDE_CFG['key']}` {BAD_DEPLOY_PRELUDE_CFG['old']}→{BAD_DEPLOY_PRELUDE_CFG['new']} "
      f"at {BAD_DEPLOY_PRELUDE_CFG['changed_at']} by {BAD_DEPLOY_PRELUDE_CFG['operator']}; on-call re-deploy "
      f"`{BAD_DEPLOY_RESTART['version']}` (deployment_id {dep['restart']}) at {BAD_DEPLOY_RESTART['deployed_at']} by "
      f"{BAD_DEPLOY_RESTART['operator']} — between first error and incident opening; hotfix `{BAD_DEPLOY['hotfix_version']}` "
      f"at {BAD_DEPLOY['hotfix_at']}.")
    w("* Questions: q07 (deployment before first linked ERROR), q08 (latency ratio), q16 (ISO week with most auth-router ERRORs).\n")

    w("## Story 2 — fx-service cache TTL misconfiguration → stale rates → settlement discrepancies\n")
    c = FX_STORY["change"]
    w(f"* Config change **change_id {chg['fx_change']}**: `{FX_STORY['key']}` {c['old']}→{c['new']} on `{FX_STORY['component']}` "
      f"at **{c['changed_at']}** by {c['operator']} (ticket {c['ticket']}); reverted by change_id {chg['fx_revert']} at "
      f"{FX_STORY['revert']['changed_at']}. Decoy: change_id {chg['fx_decoy']} (`{FX_STORY['decoy']['key']}`) at "
      f"{FX_STORY['decoy']['changed_at']}.")
    w(f"* Settlements with settled_at in [{FX_STORY['stale_from']}, {FX_STORY['stale_to']}) used the rate snapshot of "
      f"**{FX_STORY['stale_rate_date']}** (`settlement.fx_rate_applied`), i.e. the 06:00 batches of 2025-05-13 .. 2025-05-19. "
      f"{ds.meta['n_stale_settlements']} settlements are in the window (EUR ones are unaffected, rate 1.0).")
    w("* Per settlement day: (date, settlements with applied rate ≠ official rate, of which relative deviation > 0.5 %)")
    for d, n, n5 in stats["stale_by_day"]:
        w(f"  * {d}: {n} / {n5}")
    w(f"* Logs: hourly INFO CACHE_REFRESH on fx-service disappears during the window; hourly WARN RATE_AGE_HIGH instead "
      f"(linked to incident **{inc['fx_stale']}**, opened {FX_STORY['incident_opened']}).")
    w("* Questions: q11 (count of mis-rated settlements), q12 (config change before the first mis-rated settlement), "
      "q19 (ISO week with the largest settlement discrepancy, v2).\n")

    w("## Story 3 — acquirer outage → timeouts on its routes\n")
    o = stats["outage"]
    w(f"* `{OUTAGE['acquirer']}` unreachable **{OUTAGE['from_ts']} .. {OUTAGE['to_ts']}**; on all its routes "
      f"{OUTAGE['timeout_prob']:.0%} of transactions end in {', '.join(OUTAGE['timeout_codes'])} "
      f"(weights {OUTAGE['timeout_codes']}); {OUTAGE['retry_prob']:.0%} of timed-out payments are retried 20-90 s later "
      f"({ds.meta['n_outage_retries']} retry rows).")
    w(f"  * data: {o[0]} txns on the acquirer's routes in the outage window; timeout share {o[1]:.4f} with v2 semantics "
      f"(Z3, 91, 96) vs {o[2]:.4f} if '96' is treated as a decline (v1 semantics).")
    oi = stats["outage_incident_window"]
    w(f"  * q09 window [opened_at, closed_at): {oi[0]} txns, timeout share {oi[1]:.4f} (v2 semantics) vs {oi[2]:.4f} (v1 semantics).")
    w(f"* Incident **{inc['outage']}** opened {OUTAGE['incident_opened']}, closed {OUTAGE['incident_closed']} "
      f"({OUTAGE['severity']}, {OUTAGE['root_cause']}); acquirer-gateway ERROR UPSTREAM_TIMEOUT every ~20 s with the "
      f"acquirer's route_ids, 30 of 40 correlation ids linked.")
    w("* Questions: q09 (timeout share during the incident window).\n")

    w("## Story 4 — terminal firmware family with elevated declines\n")
    fc = FIRMWARE["rollout_cfg"]
    w(f"* Firmware family **{FIRMWARE['family']}** (models V240m, P400): rollout config change_id {chg['fw_rollout']} "
      f"(`{fc['key']}` {fc['old']}→{fc['new']}) at {fc['changed_at']} by {fc['operator']}; INFO FIRMWARE_ROLLOUT events per "
      f"terminal 02:00-06:00. From **{FIRMWARE['from_ts']}** decline probability +{FIRMWARE['decline_add']:.1%} "
      f"(extra codes {FIRMWARE['extra_codes']}).")
    w(f"* Incident **{inc['firmware']}** ({FIRMWARE['severity']}, {FIRMWARE['root_cause']}) opened only on "
      f"{FIRMWARE['incident_opened']}; daily WARN DECLINE_RATE_HIGH from risk-engine linked.")
    w("* Monthly decline rate of the family (versioned dictionary): " +
      ", ".join(f"{m}: {r:.4f} (n={n})" for m, r, n in stats["firmware_monthly"]))
    w("* Q4 decline rate by family: " + ", ".join(f"{f}: {r:.4f} (n={n})" for f, r, n in stats["family_q4"]))
    w("* Questions: q04 (P400 decline rate in August), q05 (family with highest Q4 decline rate), q14 (first month > 9 %), "
      "q17 (Lane 3000X in November under v3, v2 DB).\n")

    w("## Story 5 — weekly seasonality + growth for one merchant group\n")
    w(f"* Group **`{SEASONAL_GROUP['group']}`** (level 2 under `Helios Group`; 4 chains + 1 direct store). Day-of-week factors "
      f"Mon..Sun = {SEASONAL_GROUP['dow']}, linear growth +{SEASONAL_GROUP['growth']:.0%} over the year, December bump "
      f"{SEASONAL_GROUP['week_bump']}. Everyone else: mild Fri/Sat peak and flat trend.")
    w("* Top ISO weeks by txn count: " + ", ".join(f"{wk}: {n}" for wk, n in stats["seasonal_weeks"]))
    w("* Monthly CAPTURED EUR volume: " + ", ".join(f"{m}: {v:,.0f}" for m, v in stats["seasonal_monthly"]))
    w(f"* q06 threshold chosen from the data: {ds.meta['q06_threshold']:,} EUR.")
    w("* Questions: q02 (peak ISO week), q06 (first month above threshold).\n")

    w("## Story 6 — chain sold mid-year: terminals re-assigned to another holding\n")
    w(f"* On **{MOVE['move_ts']}** all {stats['moved']} terminals of chain `{MOVE['from_group']}` (Aurora Hospitality / "
      f"Aurora Collective; merchant_ids {min(ds.meta['move_old_merchants'])}..{max(ds.meta['move_old_merchants'])}) were "
      f"re-assigned 1:1 to new merchants of chain `{MOVE['to_group']}` (Borealis Cafés & Bakeries / Borealis Retail AG; "
      f"merchant_ids {min(ds.meta['move_new_merchants'])}..{max(ds.meta['move_new_merchants'])}, onboarded_at = move date).")
    w(f"* CAPTURED EUR volume attributed to `{MOVE['from_group']}` with the historical join: {stats['coffee_h1_eur']:,.2f} "
      f"(all of it before the move). A join on the *current* assignment attributes it to Borealis.")
    w("* Questions: q03, q13, q15, q20 (and the hierarchy questions in general).\n")

    w("## Story 7 — operator whose changes precede incidents\n")
    w(f"* `{OPERATOR_STORY['operator']}` (Platform SRE) made config changes 21-44 min before 4 different incidents "
      f"(change_ids {', '.join(str(chg[f'story_{j}']) for j in range(4))}). Runner-ups: " +
      ", ".join(f"{k}: {v}" for k, v in sorted(ds.meta['operator_counts'].items(), key=lambda kv: -kv[1]) if k != OPERATOR_STORY['operator']) +
      ". Decoy changes 80-105 min before incidents do not count.")
    w(f"* q18 target: incident {inc['random_16']} — change_id {chg['story_3']} ({OPERATOR_STORY['operator']}, 40 min before "
      f"opening) precedes the first linked ERROR (12 min before opening); change_id {chg['story_8']} (j.mueller, 4 min before "
      f"opening) is a decoy for 'latest change before opened_at'.")
    w("* Questions: q10, q18.\n")

    w("## Incidents\n")
    w("| code | opened_at | closed_at | sev | component | root cause | linked corr. ids | summary |")
    w("|---|---|---|---|---|---|---|---|")
    for code, o, cl, sv, comp, rc, summ, nl in stats["incidents"]:
        w(f"| {code} | {o} | {cl} | {sv} | {comp} | {rc} | {nl} | {summ} |")
    w("")

    w("## Migration payops.db → payops_v2.db\n")
    w("* `terminal_assignment(assignment_id, valid_from, valid_to)` → `terminal_merchant_link(link_id, start_ts, end_ts)`")
    w("* `dim_merchant.group_id` → `dim_merchant.merchant_group_id`")
    w("* `service_event` → `service_event_h1` (ts < 2025-07-01) + `service_event_h2` (ts ≥ 2025-07-01), no view")
    w(f"* `response_code_dict`: v2 rows get valid_to = `{RC_V3_FROM}`, v3 rows added (see above)")
    w("* `fx_rate(fx_rate_id, rate_to_eur)` → `fx_rate_daily(fx_id, eur_per_unit)`")
    w("* Facts are byte-identical (the v2 file is created by copying v1 and applying ALTER/INSERT statements).\n")

    w("## Questions\n")
    w("| id | stage | db | difficulty | tags | answer | tolerance |")
    w("|---|---|---|---|---|---|---|")
    for q in questions:
        w(f"| {q.id} | {q.stage} | {q.db} | {q.difficulty} | {', '.join(q.knowledge_tags)} | `{_fmt(q.answer)}` | {q.tolerance} |")
    w("")

    w("## Validation: naive approach → naive answer → correct answer\n")
    w("| question | naive approach | naive answer | correct answer | graded incorrect? |")
    w("|---|---|---|---|---|")
    for r in naive:
        w(f"| {r['id']} | {r['label']} | `{_fmt(r['naive'])}` | `{_fmt(r['correct'])}` | {'yes' if r['distinguishes'] else 'NO (same answer)'} |")
    w("")

    w("Rows marked `NO (same answer)` are questions whose answer is robust to that particular shortcut (the knowledge is "
      "still required to run the query, but it does not change the result); they are kept as controls.\n")
    w("## Validation: independent re-computation (pandas on the generated frames)\n")
    w("| question | pandas | SQL ground truth | match |")
    w("|---|---|---|---|")
    for r in independent:
        w(f"| {r['id']} | `{_fmt(r['pandas'])}` | `{_fmt(r['sql'])}` | {'ok' if r['ok'] else 'MISMATCH'} |")
    w("")

    w("## Ground-truth query timings\n")
    w("Wall-clock of each gt_sql on the machine that built the dataset (python sqlite3, warm file cache); the only "
      "non-deterministic part of this file.\n")
    w("| question | db | ms |")
    w("|---|---|---|")
    for t in timings:
        w(f"| {t['id']} | {t['db']} | {t['ms']} |")
    w("")

    w("## Row counts and file sizes\n")
    w("| table | rows |")
    w("|---|---|")
    for k, v in row_counts.items():
        w(f"| {k} | {v:,} |")
    w("")
    for k, v in sizes.items():
        w(f"* {k}: {v / 1e6:.1f} MB")
    w("")
    return "\n".join(L)


def render_v2(questions_v2: list[Question], timings: list[dict], naive: list[dict], independent: list[dict],
              drift_after: int, q22_slopes: dict | None = None) -> str:
    """Section appended to STORIES.md describing data/questions_v2.json (hard wording + investigative questions)."""
    L: list[str] = []
    w = L.append
    w("## Questions v2 — `data/questions_v2.json` (hard wording + investigative questions)\n")
    w("Second catalogue over the **same databases** (no change to payops.db / payops_v2.db). Motivation: the calibration "
      "run of gpt-6-luna in stateless mode scored 18/20 on `questions.json`; both misses were the ISO-week trap "
      "(`strftime('%W')`), everything else was solved because the texts spelled out the mechanics "
      "(\"assigned at the time of each transaction\", \"dictionary version valid at the transaction's timestamp\", "
      "\"EUR per unit\", \"through correlation ids\").\n")
    w("* **q01..q20**: same ids, same `gt_sql`, same answers and tolerances as in `questions.json`; only the wording "
      "changed. Texts are written the way a manager would brief an analyst: the metric stays unambiguous (interval "
      "bounds, UTC, rounding, status/class of transactions, \"including all sub-groups at any level\"), but nothing "
      "says how the schema encodes it — effective-dated terminal assignments, versioned response-code dictionary, "
      "currency exponents, incident ↔ event linkage and the h1/h2 log split must be discovered from the DDL comments "
      "and the data.")
    w("* **q21..q26**: new investigative / trend questions where the path is not prescribed and candidates have to be "
      "scanned (rolled-back releases, divisions' weekly trends, retries after timeouts, configuration changes followed "
      "by error bursts, platform-wide error peaks, shrinking chains). Each answer is a single value with a documented "
      "margin to the runner-up.")
    w("* Every question carries `naive_variants` (description, SQL, answer, `discriminative`): the typical shortcuts "
      "— current assignment instead of the date-range join, dictionary v1 after 2025-07-01, no exponent, `%W` instead "
      "of ISO week, one of h1/h2 only, latest change before `opened_at` instead of before the first linked ERROR, "
      "status FAILED as decline/timeout, no hierarchy roll-up. `discriminative: false` marks shortcuts that happen to "
      "give the right answer for that question (controls).")
    w(f"* **Run order** = file order: pre-drift q01..q14, q21..q24 (v1 DB), then post-drift q15..q20, q25..q26 (v2 DB) "
      f"→ `--drift-after {drift_after}`.\n")

    w("### Questions v2\n")
    w("| # | id | stage | db | difficulty | tags | answer | tolerance | margin to runner-up |")
    w("|---|---|---|---|---|---|---|---|---|")
    for i, q in enumerate(questions_v2, 1):
        if q.margin:
            m = q.margin
            rel = f" ({m['rel_margin']:.0%})" if m.get("rel_margin") is not None else ""
            margin = f"`{_fmt(m['top_metric'])}` vs `{m['second']}` = `{_fmt(m['second_metric'])}`{rel}"
        else:
            margin = "—"
        w(f"| {i} | {q.id} | {q.stage} | {q.db} | {q.difficulty} | {', '.join(q.knowledge_tags)} | `{_fmt(q.answer)}` | "
          f"{q.tolerance} | {margin} |")
    w("")
    w("### New questions in detail\n")
    for q in questions_v2:
        if q.id in ("q21", "q22", "q23", "q24", "q25", "q26"):
            w(f"* **{q.id}** ({q.stage}, {q.db}, {q.difficulty}) — {q.text}")
            w(f"  * answer `{_fmt(q.answer)}`; {q.rationale}")
    w("")
    if q22_slopes:
        w("OLS slopes of weekly transaction counts per division (q22, historical assignment, zero-filled weeks): " +
          ", ".join(f"{k}: {v}" for k, v in q22_slopes.items()) + "\n")

    w("### Validation v2: naive approach → naive answer → correct answer\n")
    w("| question | naive approach | naive answer | correct answer | graded incorrect? |")
    w("|---|---|---|---|---|")
    for r in naive:
        w(f"| {r['id']} | {r['label']} | `{_fmt(r['naive'])}` | `{_fmt(r['correct'])}` | "
          f"{'yes' if r['distinguishes'] else 'NO (same answer)'} |")
    w("")
    w("### Validation v2: independent re-computation (pandas on the generated frames)\n")
    w("q01..q20 are asserted to have exactly the v1 answers (same gt_sql); the new questions are recomputed independently.\n")
    w("| question | pandas | SQL ground truth | match |")
    w("|---|---|---|---|")
    for r in independent:
        w(f"| {r['id']} | `{_fmt(r['pandas'])}` | `{_fmt(r['sql'])}` | {'ok' if r['ok'] else 'MISMATCH'} |")
    w("")
    w("### Ground-truth query timings v2\n")
    w("| question | db | ms |")
    w("|---|---|---|")
    for t in timings:
        w(f"| {t['id']} | {t['db']} | {t['ms']} |")
    w("")
    return "\n".join(L)
