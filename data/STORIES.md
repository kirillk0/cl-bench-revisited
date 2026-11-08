# PayOps dataset — planted stories, ground truth and validation

> Private documentation for the experiment. **Never show this file to the models.**

Generated deterministically by `python -m clrev.dataset.build --out data/` (seed 20261108).

## Conventions

* All timestamps are UTC text `YYYY-MM-DD HH:MM:SS`; all validity intervals are half-open `[from, to)`, `NULL` = open.
* `txn.amount_minor` is in minor units of `txn.currency_id`; the number of minor digits is `dim_currency.exponent` (EUR/USD/... = 2, **JPY = 0, KWD = 3**).
* `fx_rate.rate_to_eur` (v2: `fx_rate_daily.eur_per_unit`) = EUR value of one unit of the currency on `rate_date`; daily rows for every currency incl. EUR = 1.0, 2025-01-01 .. 2026-01-07.
* `terminal_assignment` (v2: `terminal_merchant_link`) is effective-dated: terminals move between merchants, so historic attribution needs a date-range join. 44 terminals moved in the planted acquisition, 65 more moved once at random dates (6% of the fleet).
* `response_code_dict` is versioned by `scheme_version` with `valid_from/valid_to`; the raw codes in `txn.response_code` never change, only their interpretation does. `txn_status_dict` only knows CAPTURED / AUTHORIZED / FAILED / REVERSED / REFUNDED — FAILED covers both declines and timeouts, so the dictionary is the only way to tell them apart.
* `incident_link(incident_id, correlation_id)` connects incidents to `service_event.correlation_id`; most incident bursts also contain unlinked events with other correlation ids, and components emit baseline ERRORs all year.
* Merchant group hierarchy: 3 levels (holding → division → chain). Merchants mostly hang off chains, but every holding has one flagship store attached directly and ~70 % of divisions have a direct store too.

## Response code dictionary versions

* **v1** valid `2025-01-01` .. `2025-07-01 00:00:00` (exclusive).
* **v2** valid from `2025-07-01 00:00:00` (in payops.db open-ended; in payops_v2.db until `2025-10-01 00:00:00`):
  * `96` → "System malfunction - treated as technical timeout (auto-retry)" is_decline=0 is_timeout=1
  * `68` → "Response received too late - auto-reversed, counted as decline" is_decline=1 is_timeout=0
  * `65` → "Soft decline - strong customer authentication required" is_decline=1 is_timeout=0
* **v3** (payops_v2.db only) valid from `2025-10-01 00:00:00`:
  * `Z1` → "Processor declined - retry budget exhausted" is_decline=1 is_timeout=0
  * `91` → "Issuer unavailable - declined by stand-in processing" is_decline=1 is_timeout=0

## Story 1 — bad deployment of auth-router → latency/timeout spike on one route → incident

* Deployment `v4.18.0` of `auth-router` (deployment_id 31) by `d.kowalski` at **2025-03-11 14:05:00**, rolled back 2025-03-11 16:30:00.
* Effect window 2025-03-11 14:05:00 .. 2025-03-11 16:30:00 on route `ALP-PRX-1` (route_id 6) only: latency ×4.0, 22% 'Z1' processor timeouts.
  * data: 22 txns in the window, mean latency 4114 ms, Z1 share 0.182; the 145 min before: 26 txns, mean latency 344 ms, Z1 share 0.000.
* Logs: WARN LATENCY_HIGH from 2025-03-11 14:12:00, first **linked ERROR at 2025-03-11 14:21:07** (POOL_EXHAUSTED, correlation id in incident_link); 265 linked ERROR events in total. An unlinked baseline ERROR on the same component at 2025-03-11 13:52:40 is noise.
* Incident **INC-2025-0005** opened 2025-03-11 14:40:00, closed 2025-03-11 16:55:00 (SEV2, BAD_DEPLOY).
* Decoys: config change `pool.max_connections` 64→96 at 2025-03-11 13:10:00 by a.nowak; on-call re-deploy `v4.18.0+restart` (deployment_id 32) at 2025-03-11 14:33:00 by j.mueller — between first error and incident opening; hotfix `v4.18.1` at 2025-03-12 10:10:00.
* Questions: q07 (deployment before first linked ERROR), q08 (latency ratio), q16 (ISO week with most auth-router ERRORs).

## Story 2 — fx-service cache TTL misconfiguration → stale rates → settlement discrepancies

* Config change **change_id 54**: `rate_cache_ttl_seconds` 300→604800 on `fx-service` at **2025-05-12 09:14:00** by m.ferreira (ticket OPS-2231); reverted by change_id 60 at 2025-05-19 11:30:00. Decoy: change_id 58 (`log.level`) at 2025-05-15 16:40:00.
* Settlements with settled_at in [2025-05-12 09:14:00, 2025-05-19 11:30:00) used the rate snapshot of **2025-05-12** (`settlement.fx_rate_applied`), i.e. the 06:00 batches of 2025-05-13 .. 2025-05-19. 4007 settlements are in the window (EUR ones are unaffected, rate 1.0).
* Per settlement day: (date, settlements with applied rate ≠ official rate, of which relative deviation > 0.5 %)
  * 2025-05-13: 215 / 0
  * 2025-05-14: 254 / 34
  * 2025-05-15: 234 / 19
  * 2025-05-16: 229 / 113
  * 2025-05-17: 291 / 218
  * 2025-05-18: 299 / 184
  * 2025-05-19: 202 / 175
* Logs: hourly INFO CACHE_REFRESH on fx-service disappears during the window; hourly WARN RATE_AGE_HIGH instead (linked to incident **INC-2025-0010**, opened 2025-05-19 10:02:00).
* Questions: q11 (count of mis-rated settlements), q12 (config change before the first mis-rated settlement), q19 (ISO week with the largest settlement discrepancy, v2).

## Story 3 — acquirer outage → timeouts on its routes

* `Meridian Acquiring` unreachable **2025-09-18 09:10:00 .. 2025-09-18 13:40:00**; on all its routes 75% of transactions end in Z3, 91, 96 (weights {'Z3': 0.6, '91': 0.25, '96': 0.15}); 50% of timed-out payments are retried 20-90 s later (35 retry rows).
  * data: 120 txns on the acquirer's routes in the outage window; timeout share 0.8167 with v2 semantics (Z3, 91, 96) vs 0.7333 if '96' is treated as a decline (v1 semantics).
  * q09 window [opened_at, closed_at): 122 txns, timeout share 0.7869 (v2 semantics) vs 0.7049 (v1 semantics).
* Incident **INC-2025-0018** opened 2025-09-18 09:31:00, closed 2025-09-18 13:55:00 (SEV1, THIRD_PARTY_OUTAGE); acquirer-gateway ERROR UPSTREAM_TIMEOUT every ~20 s with the acquirer's route_ids, 30 of 40 correlation ids linked.
* Questions: q09 (timeout share during the incident window).

## Story 4 — terminal firmware family with elevated declines

* Firmware family **OSX-3** (models V240m, P400): rollout config change_id 87 (`fleet.firmware.OSX-3.target_version` 3.7.1→3.7.2) at 2025-08-04 01:30:00 by y.tanaka; INFO FIRMWARE_ROLLOUT events per terminal 02:00-06:00. From **2025-08-04 02:00:00** decline probability +4.5% (extra codes {'05': 0.5, '57': 0.3, '62': 0.2}).
* Incident **INC-2025-0016** (SEV4, FIRMWARE_DEFECT) opened only on 2025-08-21 09:15:00; daily WARN DECLINE_RATE_HIGH from risk-engine linked.
* Monthly decline rate of the family (versioned dictionary): 2025-01: 0.0683 (n=4964), 2025-02: 0.0726 (n=4240), 2025-03: 0.0649 (n=5225), 2025-04: 0.0655 (n=5541), 2025-05: 0.0676 (n=5872), 2025-06: 0.0666 (n=5632), 2025-07: 0.0599 (n=6197), 2025-08: 0.1028 (n=6177), 2025-09: 0.1066 (n=5790), 2025-10: 0.1078 (n=6225), 2025-11: 0.1079 (n=6421), 2025-12: 0.1084 (n=7567)
* Q4 decline rate by family: OSX-3: 0.1080 (n=20213), CTOS-2: 0.0675 (n=4887), ANDROID-SP: 0.0656 (n=3003), TETRA-9: 0.0634 (n=27547), PayDroid-8: 0.0631 (n=17144)
* Questions: q04 (P400 decline rate in August), q05 (family with highest Q4 decline rate), q14 (first month > 9 %), q17 (Lane 3000X in November under v3, v2 DB).

## Story 5 — weekly seasonality + growth for one merchant group

* Group **`Helios Grocery`** (level 2 under `Helios Group`; 4 chains + 1 direct store). Day-of-week factors Mon..Sun = [0.85, 0.9, 0.95, 1.0, 1.35, 1.5, 0.55], linear growth +70% over the year, December bump {'2025-W50': 1.12, '2025-W51': 1.3, '2025-W52': 0.9, '2026-W01': 0.8}. Everyone else: mild Fri/Sat peak and flat trend.
* Top ISO weeks by txn count: 2025-W51: 3321, 2025-W50: 2950, 2025-W49: 2628, 2025-W52: 2345
* Monthly CAPTURED EUR volume: 2025-01: 217,092, 2025-02: 193,201, 2025-03: 245,357, 2025-04: 259,486, 2025-05: 297,019, 2025-06: 282,014, 2025-07: 331,087, 2025-08: 330,737, 2025-09: 312,087, 2025-10: 359,299, 2025-11: 369,180, 2025-12: 448,222
* q06 threshold chosen from the data: 280,000 EUR.
* Questions: q02 (peak ISO week), q06 (first month above threshold).

## Story 6 — chain sold mid-year: terminals re-assigned to another holding

* On **2025-06-16 00:00:00** all 44 terminals of chain `Aurora Coffee Chain` (Aurora Hospitality / Aurora Collective; merchant_ids 107..120) were re-assigned 1:1 to new merchants of chain `Borealis Coffee (ex-Aurora)` (Borealis Cafés & Bakeries / Borealis Retail AG; merchant_ids 275..288, onboarded_at = move date).
* CAPTURED EUR volume attributed to `Aurora Coffee Chain` with the historical join: 61,274.19 (all of it before the move). A join on the *current* assignment attributes it to Borealis.
* Questions: q03, q13, q15, q20 (and the hierarchy questions in general).

## Story 7 — operator whose changes precede incidents

* `r.svensson` (Platform SRE) made config changes 21-44 min before 4 different incidents (change_ids 15, 49, 83, 100). Runner-ups: d.kowalski: 2, j.mueller: 2. Decoy changes 80-105 min before incidents do not count.
* q18 target: incident INC-2025-0021 — change_id 100 (r.svensson, 40 min before opening) precedes the first linked ERROR (12 min before opening); change_id 101 (j.mueller, 4 min before opening) is a decoy for 'latest change before opened_at'.
* Questions: q10, q18.

## Incidents

| code | opened_at | closed_at | sev | component | root cause | linked corr. ids | summary |
|---|---|---|---|---|---|---|---|
| INC-2025-0001 | 2025-01-14 08:52:00 | 2025-01-14 10:27:00 | SEV3 | api-edge | CAPACITY | 18 | Elevated 5xx at the edge during morning peak |
| INC-2025-0002 | 2025-01-28 03:15:00 | 2025-01-28 07:15:00 | SEV4 | reporting-etl | HARDWARE | 10 | Nightly merchant report delayed (disk failure on worker) |
| INC-2025-0003 | 2025-02-06 15:40:00 | 2025-02-06 16:50:00 | SEV3 | risk-engine | CONFIG_ERROR | 16 | Risk rules rejecting valid tokens after rule-set reload |
| INC-2025-0004 | 2025-02-19 11:05:00 | 2025-02-19 12:00:00 | SEV2 | acquirer-gateway | NETWORK | 6 | Packet loss towards NordPay endpoint |
| INC-2025-0005 | 2025-03-11 14:40:00 | 2025-03-11 16:55:00 | SEV2 | auth-router | BAD_DEPLOY | 22 | Timeouts and high latency on route ALP-PRX-1 after auth-router release |
| INC-2025-0006 | 2025-03-27 06:30:00 | 2025-03-27 09:30:00 | SEV3 | settlement-engine | CAPACITY | 7 | Settlement batch running late |
| INC-2025-0007 | 2025-04-09 13:20:00 | 2025-04-09 14:05:00 | SEV2 | tokenization-vault | CERT_EXPIRY | 18 | Vault client certificate expired |
| INC-2025-0008 | 2025-04-23 17:10:00 | 2025-04-23 18:10:00 | SEV3 | api-edge | UNKNOWN | 19 | Intermittent 502s from edge nodes in eu-west |
| INC-2025-0009 | 2025-05-06 09:45:00 | 2025-05-06 11:45:00 | SEV3 | ledger | BAD_DEPLOY | 8 | Ledger posting lag after release |
| INC-2025-0010 | 2025-05-19 10:02:00 | 2025-05-19 12:15:00 | SEV3 | fx-service | CONFIG_ERROR | 5 | Finance reports settlement EUR amounts not matching daily rates |
| INC-2025-0011 | 2025-06-03 12:00:00 | 2025-06-03 14:30:00 | SEV4 | notification-svc | THIRD_PARTY_OUTAGE | 18 | SMS provider degraded |
| INC-2025-0012 | 2025-06-24 16:35:00 | 2025-06-24 17:15:00 | SEV3 | acquirer-gateway | NETWORK | 20 | TLS handshakes failing to Gulf Card Services |
| INC-2025-0013 | 2025-07-15 10:25:00 | 2025-07-15 11:50:00 | SEV2 | risk-engine | CAPACITY | 10 | Risk scoring latency above SLO |
| INC-2025-0014 | 2025-07-29 02:05:00 | 2025-07-29 05:25:00 | SEV4 | scheduler | HARDWARE | 6 | Scheduler leader election flapping |
| INC-2025-0015 | 2025-08-12 14:50:00 | 2025-08-12 15:40:00 | SEV3 | api-edge | CONFIG_ERROR | 9 | Rate limits applied to internal clients |
| INC-2025-0016 | 2025-08-21 09:15:00 | 2025-08-29 17:00:00 | SEV4 | terminal-fleet-mgr | FIRMWARE_DEFECT | 15 | Elevated decline rate on OSX-3 terminals since firmware 3.7.2 |
| INC-2025-0017 | 2025-09-02 07:20:00 | 2025-09-02 09:30:00 | SEV3 | settlement-engine | BAD_DEPLOY | 11 | Duplicate fee lines in settlement export |
| INC-2025-0018 | 2025-09-18 09:31:00 | 2025-09-18 13:55:00 | SEV1 | acquirer-gateway | THIRD_PARTY_OUTAGE | 30 | Meridian Acquiring not responding - timeouts on all its routes |
| INC-2025-0019 | 2025-10-07 11:20:00 | 2025-10-07 13:10:00 | SEV2 | auth-router | CAPACITY | 4 | Thread starvation under promotional traffic |
| INC-2025-0020 | 2025-10-21 04:40:00 | 2025-10-21 09:00:00 | SEV4 | reporting-etl | UNKNOWN | 8 | ETL checkpoint corruption |
| INC-2025-0021 | 2025-11-04 09:05:00 | 2025-11-04 10:20:00 | SEV3 | tokenization-vault | CONFIG_ERROR | 7 | HSM partition quota exhausted |
| INC-2025-0022 | 2025-11-18 15:30:00 | 2025-11-18 16:35:00 | SEV2 | acquirer-gateway | THIRD_PARTY_OUTAGE | 20 | Sakura Card Acquiring maintenance overrun |
| INC-2025-0023 | 2025-12-02 10:15:00 | 2025-12-02 11:45:00 | SEV3 | ledger | CAPACITY | 8 | Ledger DB connection saturation |
| INC-2025-0024 | 2025-12-16 08:05:00 | 2025-12-16 08:40:00 | SEV4 | fx-service | THIRD_PARTY_OUTAGE | 18 | FX rate feed unavailable (fallback to previous day) |

## Migration payops.db → payops_v2.db

* `terminal_assignment(assignment_id, valid_from, valid_to)` → `terminal_merchant_link(link_id, start_ts, end_ts)`
* `dim_merchant.group_id` → `dim_merchant.merchant_group_id`
* `service_event` → `service_event_h1` (ts < 2025-07-01) + `service_event_h2` (ts ≥ 2025-07-01), no view
* `response_code_dict`: v2 rows get valid_to = `2025-10-01 00:00:00`, v3 rows added (see above)
* `fx_rate(fx_rate_id, rate_to_eur)` → `fx_rate_daily(fx_id, eur_per_unit)`
* Facts are byte-identical (the v2 file is created by copying v1 and applying ALTER/INSERT statements).

## Questions

| id | stage | db | difficulty | tags | answer | tolerance |
|---|---|---|---|---|---|---|
| q01 | pre | v1 | medium | FX_EXPONENT, DATE_FILTER | `36,531.85` | 1.0 |
| q02 | pre | v1 | medium | HIERARCHY, DATE_RANGE_JOIN, ISO_WEEK | `2025-W51` | 0 |
| q03 | pre | v1 | hard | HIERARCHY, DATE_RANGE_JOIN, FX_EXPONENT | `815,909.97` | 500.0 |
| q04 | pre | v1 | medium | CODE_DICT_VERSION, TERMINAL_MODEL | `0.1014` | 0.0005 |
| q05 | pre | v1 | hard | CODE_DICT_VERSION, TERMINAL_MODEL | `OSX-3` | 0 |
| q06 | pre | v1 | medium | HIERARCHY, DATE_RANGE_JOIN, FX_EXPONENT, TREND | `2025-05` | 0 |
| q07 | pre | v1 | hard | INCIDENT_LINK, LOG_WINDOW, DEPLOYMENT | `v4.18.0` | 0 |
| q08 | pre | v1 | medium | LOG_WINDOW, DEPLOYMENT, LATENCY | `14.96` | 0.05 |
| q09 | pre | v1 | hard | CODE_DICT_VERSION, INCIDENT_WINDOW, ROUTE_ACQUIRER | `0.7869` | 0.0005 |
| q10 | pre | v1 | hard | LOG_WINDOW, OPERATOR_CHANGES, DEPLOYMENT, CONFIG_CHANGE | `r.svensson` | 0 |
| q11 | pre | v1 | medium | SETTLEMENT, FX_RATE_DATE | `743` | 2 |
| q12 | pre | v1 | hard | SETTLEMENT, FX_RATE_DATE, CONFIG_CHANGE, LOG_WINDOW | `54` | 0 |
| q13 | pre | v1 | hard | HIERARCHY, DATE_RANGE_JOIN, FX_EXPONENT | `Helios Group` | 0 |
| q14 | pre | v1 | medium | CODE_DICT_VERSION, TERMINAL_MODEL, TREND | `2025-08` | 0 |
| q15 | post | v2 | hard | HIERARCHY, DATE_RANGE_JOIN, FX_EXPONENT, SCHEMA_DRIFT | `2,463,087.54` | 2500.0 |
| q16 | post | v2 | medium | ISO_WEEK, LOG_SPLIT, SCHEMA_DRIFT | `2025-W11` | 0 |
| q17 | post | v2 | hard | CODE_DICT_VERSION, TERMINAL_MODEL, SCHEMA_DRIFT | `0.072` | 0.0005 |
| q18 | post | v2 | hard | INCIDENT_LINK, LOG_WINDOW, CONFIG_CHANGE, LOG_SPLIT, SCHEMA_DRIFT | `100` | 0 |
| q19 | post | v2 | medium | FX_EXPONENT, SETTLEMENT, ISO_WEEK, SCHEMA_DRIFT | `2025-W20` | 0 |
| q20 | post | v2 | hard | HIERARCHY, DATE_RANGE_JOIN, SCHEMA_DRIFT | `98` | 0 |

## Validation: naive approach → naive answer → correct answer

| question | naive approach | naive answer | correct answer | graded incorrect? |
|---|---|---|---|---|
| q01 | divide all amounts by 100 (ignore exponent) | `45,247.23` | `36,531.85` | yes |
| q02 | strftime('%W') instead of ISO week | `2025-W50` | `2025-W51` | yes |
| q02 | only merchants directly in the group (no hierarchy) | `None` | `2025-W51` | yes |
| q03 | join on current assignment (valid_to IS NULL) | `727,578.12` | `815,909.97` | yes |
| q04 | always use scheme_version 1 | `0.1045` | `0.1014` | yes |
| q04 | status = FAILED as 'declined' | `0.1145` | `0.1014` | yes |
| q05 | status = FAILED as 'declined' | `OSX-3` | `OSX-3` | NO (same answer) |
| q06 | only merchants directly in the group (no hierarchy) | `None` | `2025-05` | yes |
| q07 | latest deployment before incident.opened_at | `v4.18.0+restart` | `v4.18.0` | yes |
| q07 | first ERROR of the component that day (ignoring incident_link) | `v4.17.0` | `v4.18.0` | yes |
| q08 | all routes instead of the affected route | `2.31` | `14.96` | yes |
| q09 | always use scheme_version 1 | `0.7049` | `0.7869` | yes |
| q10 | deployments only (ignore config changes) | `d.kowalski` | `r.svensson` | yes |
| q11 | rate of the transaction date instead of the settlement date | `13388` | `743` | yes |
| q12 | latest fx-service change before the fx incident's opened_at | `58` | `54` | yes |
| q13 | only merchants attached directly to a top-level group | `Sakura Trading K.K.` | `Helios Group` | yes |
| q14 | always use scheme_version 1 | `2025-08` | `2025-08` | NO (same answer) |
| q15 | join on current link (end_ts IS NULL) | `2,399,506.17` | `2,463,087.54` | yes |
| q16 | service_event_h2 only | `2025-W41` | `2025-W11` | yes |
| q16 | strftime('%W') instead of ISO week (both halves) | `2025-W10` | `2025-W11` | yes |
| q17 | scheme_version 2 (stale knowledge from before the migration) | `0.0663` | `0.072` | yes |
| q18 | latest change before incident.opened_at | `101` | `100` | yes |
| q19 | strftime('%W') instead of ISO week | `2025-W19` | `2025-W20` | yes |
| q20 | current links only (end_ts IS NULL) | `145` | `98` | yes |

Rows marked `NO (same answer)` are questions whose answer is robust to that particular shortcut (the knowledge is still required to run the query, but it does not change the result); they are kept as controls.

## Validation: independent re-computation (pandas on the generated frames)

| question | pandas | SQL ground truth | match |
|---|---|---|---|
| q01 | `36,531.85` | `36,531.85` | ok |
| q02 | `2025-W51` | `2025-W51` | ok |
| q03 | `815,909.97` | `815,909.97` | ok |
| q09 | `0.7869` | `0.7869` | ok |
| q10 | `r.svensson` | `r.svensson` | ok |
| q11 | `743` | `743` | ok |
| q16 | `2025-W11` | `2025-W11` | ok |
| q20 | `98` | `98` | ok |

## Ground-truth query timings

Wall-clock of each gt_sql on the machine that built the dataset (python sqlite3, warm file cache); the only non-deterministic part of this file.

| question | db | ms |
|---|---|---|
| q01 | v1 | 1.3 |
| q02 | v1 | 851.5 |
| q03 | v1 | 198.1 |
| q04 | v1 | 16.6 |
| q05 | v1 | 161.5 |
| q06 | v1 | 871.1 |
| q07 | v1 | 6.1 |
| q08 | v1 | 0.4 |
| q09 | v1 | 0.6 |
| q10 | v1 | 1.0 |
| q11 | v1 | 343.0 |
| q12 | v1 | 189.7 |
| q13 | v1 | 106.8 |
| q14 | v1 | 423.8 |
| q15 | v2 | 1235.0 |
| q16 | v2 | 56.1 |
| q17 | v2 | 25.5 |
| q18 | v2 | 48.4 |
| q19 | v2 | 1636.0 |
| q20 | v2 | 0.9 |

## Row counts and file sizes

| table | rows |
|---|---|
| config_change | 109 |
| deployment | 160 |
| dim_acquirer | 6 |
| dim_component | 12 |
| dim_country | 14 |
| dim_currency | 10 |
| dim_event_type | 24 |
| dim_mcc | 16 |
| dim_mcc_category | 9 |
| dim_merchant | 288 |
| dim_merchant_group | 53 |
| dim_processor | 3 |
| dim_region | 6 |
| dim_root_cause | 9 |
| dim_severity | 4 |
| dim_team | 6 |
| dim_terminal | 1,100 |
| dim_terminal_model | 8 |
| fee_schedule | 7 |
| fx_rate | 3,720 |
| incident | 24 |
| incident_link | 313 |
| operator | 12 |
| response_code_dict | 30 |
| route | 14 |
| service_event | 149,195 |
| settlement | 213,636 |
| terminal_assignment | 1,209 |
| txn | 247,789 |
| txn_status_dict | 5 |

* payops.db: 66.4 MB
* payops_v2.db: 66.5 MB

## Questions v2 — `data/questions_v2.json` (hard wording + investigative questions)

Second catalogue over the **same databases** (no change to payops.db / payops_v2.db). Motivation: the calibration run of gpt-6-luna in stateless mode scored 18/20 on `questions.json`; both misses were the ISO-week trap (`strftime('%W')`), everything else was solved because the texts spelled out the mechanics ("assigned at the time of each transaction", "dictionary version valid at the transaction's timestamp", "EUR per unit", "through correlation ids").

* **q01..q20**: same ids, same `gt_sql`, same answers and tolerances as in `questions.json`; only the wording changed. Texts are written the way a manager would brief an analyst: the metric stays unambiguous (interval bounds, UTC, rounding, status/class of transactions, "including all sub-groups at any level"), but nothing says how the schema encodes it — effective-dated terminal assignments, versioned response-code dictionary, currency exponents, incident ↔ event linkage and the h1/h2 log split must be discovered from the DDL comments and the data.
* **q21..q26**: new investigative / trend questions where the path is not prescribed and candidates have to be scanned (rolled-back releases, divisions' weekly trends, retries after timeouts, configuration changes followed by error bursts, platform-wide error peaks, shrinking chains). Each answer is a single value with a documented margin to the runner-up.
* Every question carries `naive_variants` (description, SQL, answer, `discriminative`): the typical shortcuts — current assignment instead of the date-range join, dictionary v1 after 2025-07-01, no exponent, `%W` instead of ISO week, one of h1/h2 only, latest change before `opened_at` instead of before the first linked ERROR, status FAILED as decline/timeout, no hierarchy roll-up. `discriminative: false` marks shortcuts that happen to give the right answer for that question (controls).
* **Run order** = file order: pre-drift q01..q14, q21..q24 (v1 DB), then post-drift q15..q20, q25..q26 (v2 DB) → `--drift-after 18`.

### Questions v2

| # | id | stage | db | difficulty | tags | answer | tolerance | margin to runner-up |
|---|---|---|---|---|---|---|---|---|
| 1 | q01 | pre | v1 | medium | FX_EXPONENT, DATE_FILTER | `36,531.85` | 1.0 | — |
| 2 | q02 | pre | v1 | medium | HIERARCHY, DATE_RANGE_JOIN, ISO_WEEK | `2025-W51` | 0 | `3321` vs `2025-W50` = `2950` (11%) |
| 3 | q03 | pre | v1 | hard | HIERARCHY, DATE_RANGE_JOIN, FX_EXPONENT | `815,909.97` | 500.0 | — |
| 4 | q04 | pre | v1 | medium | CODE_DICT_VERSION, TERMINAL_MODEL | `0.1014` | 0.0005 | — |
| 5 | q05 | pre | v1 | hard | CODE_DICT_VERSION, TERMINAL_MODEL | `OSX-3` | 0 | `0.108` vs `TETRA-9` = `0.0634` (41%) |
| 6 | q06 | pre | v1 | medium | HIERARCHY, DATE_RANGE_JOIN, FX_EXPONENT, TREND | `2025-05` | 0 | — |
| 7 | q07 | pre | v1 | hard | INCIDENT_LINK, LOG_WINDOW, DEPLOYMENT | `v4.18.0` | 0 | — |
| 8 | q08 | pre | v1 | medium | LOG_WINDOW, DEPLOYMENT, LATENCY | `14.96` | 0.05 | — |
| 9 | q09 | pre | v1 | hard | CODE_DICT_VERSION, INCIDENT_WINDOW, ROUTE_ACQUIRER | `0.7869` | 0.0005 | — |
| 10 | q10 | pre | v1 | hard | LOG_WINDOW, OPERATOR_CHANGES, DEPLOYMENT, CONFIG_CHANGE | `r.svensson` | 0 | `4` vs `d.kowalski` = `2` (50%) |
| 11 | q11 | pre | v1 | medium | SETTLEMENT, FX_RATE_DATE | `743` | 2 | — |
| 12 | q12 | pre | v1 | hard | SETTLEMENT, FX_RATE_DATE, CONFIG_CHANGE, LOG_WINDOW | `54` | 0 | — |
| 13 | q13 | pre | v1 | hard | HIERARCHY, DATE_RANGE_JOIN, FX_EXPONENT | `Helios Group` | 0 | `398,503.00` vs `Aurora Collective` = `197,685.00` (50%) |
| 14 | q14 | pre | v1 | medium | CODE_DICT_VERSION, TERMINAL_MODEL, TREND | `2025-08` | 0 | — |
| 15 | q21 | pre | v1 | medium | DEPLOYMENT, ROLLBACK_WINDOW, LOG_WINDOW, CANDIDATE_SCAN | `31` | 0 | `311` vs `52 v3.22.0` = `2` (99%) |
| 16 | q22 | pre | v1 | hard | HIERARCHY, DATE_RANGE_JOIN, ISO_WEEK, TREND, REGRESSION, CANDIDATE_SCAN | `Helios Grocery` | 0 | `27.983` vs `Borealis Cafés & Bakeries` = `8.353` (70%) |
| 17 | q23 | pre | v1 | hard | CODE_DICT_VERSION, SELF_JOIN, TIME_WINDOW, OUTAGE | `35` | 0 | — |
| 18 | q24 | pre | v1 | medium | CONFIG_CHANGE, LOG_WINDOW, CANDIDATE_SCAN | `83` | 0 | `40` vs `15 risk-engine autoscale.min_replicas @ 2025-02-06 15:02:00` = `30` (25%) |
| 19 | q15 | post | v2 | hard | HIERARCHY, DATE_RANGE_JOIN, FX_EXPONENT, SCHEMA_DRIFT | `2,463,087.54` | 2500.0 | — |
| 20 | q16 | post | v2 | medium | ISO_WEEK, LOG_SPLIT, SCHEMA_DRIFT | `2025-W11` | 0 | `342` vs `2025-W41` = `183` (46%) |
| 21 | q17 | post | v2 | hard | CODE_DICT_VERSION, TERMINAL_MODEL, SCHEMA_DRIFT | `0.072` | 0.0005 | — |
| 22 | q18 | post | v2 | hard | INCIDENT_LINK, LOG_WINDOW, CONFIG_CHANGE, LOG_SPLIT, SCHEMA_DRIFT | `100` | 0 | — |
| 23 | q19 | post | v2 | medium | FX_EXPONENT, SETTLEMENT, ISO_WEEK, SCHEMA_DRIFT | `2025-W20` | 0 | `45,379.00` vs `2025-W21` = `8,187.00` (82%) |
| 24 | q20 | post | v2 | hard | HIERARCHY, DATE_RANGE_JOIN, SCHEMA_DRIFT | `98` | 0 | — |
| 25 | q25 | post | v2 | medium | ISO_WEEK, LOG_SPLIT, SCHEMA_DRIFT, CANDIDATE_SCAN | `2025-W38` | 0 | `967` vs `2025-W11` = `518` (46%) |
| 26 | q26 | post | v2 | hard | HIERARCHY, DATE_RANGE_JOIN, TREND, SCHEMA_DRIFT, CANDIDATE_SCAN | `Aurora Coffee Chain` | 0 | `5322` vs `Borealis Online` = `12` (100%) |

### New questions in detail

* **q21** (pre, v1, medium) — Of all releases (deployments) in 2025 that were later rolled back, which one was live - from its deployment time (inclusive) to its rollback time (exclusive) - while its own component logged the most ERROR-level events? Answer with the deployment_id (integer).
  * answer `31`; Story 1: the bad auth-router release v4.18.0 (deployment_id 31) was live 14:05-16:30 on 2025-03-11 and produced ~300 ERROR events; the other rolled-back releases (8 % of random deployments) only see baseline noise (<= 2 errors). The '+restart' decoy was never rolled back. Margin: '31 v4.18.0' = 311 vs runner-up '52 v3.22.0' = 2 (99% of the winner's value).
* **q22** (pre, v1, hard) — Among second-level merchant groups (divisions, i.e. groups whose parent is a top-level group), which one had the strongest upward trend in weekly transaction count during 2025, counting transactions of any status for all merchants anywhere below the group? Trend = ordinary-least-squares slope of the weekly count against the ISO week number over the 52 weeks 2025-W01 .. 2025-W52 (x = 1..52; a week without transactions counts as 0; 2025-W01 contains only 1-5 January and is taken as is). Answer with the group's name.
  * answer `Helios Grocery`; Story 5: 'Helios Grocery' grows linearly by +70% over the year (plus a December bump); all other divisions are flat. Its merchants hang off level-3 chains, so the division's weekly counts need the hierarchy roll-up and the assignment valid at transaction time. The runner-up (Borealis Cafés & Bakeries) owes its slope to the 44 coffee-chain terminals it received on 2025-06-16. Margin: 'Helios Grocery' = 27.983 vs runner-up 'Borealis Cafés & Bakeries' = 8.353 (70% of the winner's value).
* **q23** (pre, v1, hard) — On 2025-09-18 (UTC day, 2025-09-18 00:00:00 <= timestamp < 2025-09-19 00:00:00), how many timed-out transactions were retried, i.e. followed by another transaction on the same terminal within 90 seconds (0 < delta <= 90 s)? A transaction timed out when its response code means a technical timeout (as opposed to an approval or a decline). Count each timed-out transaction at most once. Answer with an integer.
  * answer `35`; Story 3: during the Meridian Acquiring outage half of the timed-out payments were retried 20-90 s later. 15 % of the outage timeouts carry code '96', which is a timeout only in dictionary version 2 (valid from 2025-07-01); with version-1 semantics those retries are missed. Outside the outage, same-terminal follow-ups within 90 s are practically non-existent (<= 1 per day).
* **q24** (pre, v1, medium) — Which configuration change of 2025 was followed by the most ERROR-level log events from the same component within the 60 minutes after the change (change time inclusive, change time + 60 minutes exclusive)? Answer with the change_id (integer).
  * answer `83`; Story 7: r.svensson's feature.new_router change on risk-engine (2025-07-15 09:41) precedes the SEV2 capacity incident INC-2025-0013 by 44 minutes and is followed by 40 ERROR events within the hour; the runner-up is his autoscale change before INC-2025-0003 (30). Random config changes are kept >= 75 min away from incidents of their component, and deployments are not configuration changes (the '+restart' re-deploy would otherwise win). Margin: '83 risk-engine feature.new_router @ 2025-07-15 09:41:00' = 40 vs runner-up '15 risk-engine autoscale.min_replicas @ 2025-02-06 15:02:00' = 30 (25% of the winner's value).
* **q25** (post, v2, medium) — Which ISO-8601 week of 2025 had the most ERROR-level log events across all components? Consider the whole calendar year 2025. Answer in the format YYYY-Www.
  * answer `2025-W38`; Story 3: the Meridian Acquiring outage (2025-09-18, W38) produces ~840 acquirer-gateway ERRORs in one week, far ahead of the March release incident (W11). In the migrated schema the log is split into service_event_h1/h2: reading only h1 gives W11, strftime('%W') gives W37. Margin: '2025-W38' = 967 vs runner-up '2025-W11' = 518 (46% of the winner's value).
* **q26** (post, v2, hard) — Among the lowest-level merchant groups (groups that have no sub-groups), which one lost the most transactions between the first and the second half of 2025? Loss = number of transactions (any status) with timestamp < 2025-07-01 00:00:00 minus the number with timestamp >= 2025-07-01 00:00:00. Answer with the group's name.
  * answer `Aurora Coffee Chain`; Story 6: the 44 terminals of 'Aurora Coffee Chain' were re-linked to Borealis merchants on 2025-06-16, so with the historical link the chain has ~5,300 transactions in H1 and none in H2. With the current link (end_ts IS NULL) the chain has no transactions at all and the 'loss' ranking is pure noise (Borealis Online, -12). Margin: 'Aurora Coffee Chain' = 5322 vs runner-up 'Borealis Online' = 12 (100% of the winner's value).

OLS slopes of weekly transaction counts per division (q22, historical assignment, zero-filled weeks): Helios Grocery: 27.983, Borealis Cafés & Bakeries: 8.353, Vistula Food: 2.817, Al-Rashid Supermarkets: 1.803, Sakura Convenience: 1.348, Aurora Fuel & Convenience: 0.941, Nordlicht Fashion: 0.848, Helios Pharma: 0.755, Borealis Electronics: 0.457, Vistula Fashion: 0.452, Sakura Dining: 0.438, Al-Rashid Jewellery: 0.227, Nordlicht Home & Living: 0.14, Aurora Hospitality: -5.137

### Validation v2: naive approach → naive answer → correct answer

| question | naive approach | naive answer | correct answer | graded incorrect? |
|---|---|---|---|---|
| q01 | divide all amounts by 100 (ignore exponent) | `45,247.23` | `36,531.85` | yes |
| q02 | strftime('%W') instead of ISO week | `2025-W50` | `2025-W51` | yes |
| q02 | only merchants directly in the group (no hierarchy) | `None` | `2025-W51` | yes |
| q02 | join on the current assignment (valid_to IS NULL) instead of the assignment valid at txn time | `2025-W51` | `2025-W51` | NO (same answer) |
| q03 | join on current assignment (valid_to IS NULL) | `727,578.12` | `815,909.97` | yes |
| q03 | divide all amounts by 100 (ignore dim_currency.exponent) | `815,909.97` | `815,909.97` | NO (same answer) |
| q03 | only merchants attached directly to the group (no roll-up of sub-groups) | `11,916.64` | `815,909.97` | yes |
| q04 | always use scheme_version 1 | `0.1045` | `0.1014` | yes |
| q04 | status = FAILED as 'declined' | `0.1145` | `0.1014` | yes |
| q05 | status = FAILED as 'declined' | `OSX-3` | `OSX-3` | NO (same answer) |
| q05 | always use scheme_version 1 | `OSX-3` | `OSX-3` | NO (same answer) |
| q06 | only merchants directly in the group (no hierarchy) | `None` | `2025-05` | yes |
| q06 | join on the current assignment (valid_to IS NULL) | `2025-05` | `2025-05` | NO (same answer) |
| q06 | divide all amounts by 100 (ignore dim_currency.exponent) | `2025-05` | `2025-05` | NO (same answer) |
| q07 | latest deployment before incident.opened_at | `v4.18.0+restart` | `v4.18.0` | yes |
| q07 | first ERROR of the component that day (ignoring incident_link) | `v4.17.0` | `v4.18.0` | yes |
| q08 | all routes instead of the affected route | `2.31` | `14.96` | yes |
| q09 | always use scheme_version 1 | `0.7049` | `0.7869` | yes |
| q09 | status = FAILED as 'timed out' (declines counted as timeouts) | `0.8607` | `0.7869` | yes |
| q10 | deployments only (ignore config changes) | `d.kowalski` | `r.svensson` | yes |
| q10 | config changes only (ignore deployments) | `r.svensson` | `r.svensson` | NO (same answer) |
| q11 | rate of the transaction date instead of the settlement date | `13388` | `743` | yes |
| q11 | count any difference between applied and official rate (no 0.5 % threshold) | `1724` | `743` | yes |
| q12 | latest fx-service change before the fx incident's opened_at | `58` | `54` | yes |
| q13 | only merchants attached directly to a top-level group | `Sakura Trading K.K.` | `Helios Group` | yes |
| q13 | join on the current assignment (valid_to IS NULL) | `Helios Group` | `Helios Group` | NO (same answer) |
| q14 | always use scheme_version 1 | `2025-08` | `2025-08` | NO (same answer) |
| q21 | ERROR events in a fixed 60-minute window after every deployment (ignoring rollbacks) | `32` | `31` | yes |
| q21 | ERROR events of all components (not only the deployed one) during the live window | `31` | `31` | NO (same answer) |
| q22 | only merchants attached directly to the division (no roll-up of chains) | `Borealis Cafés & Bakeries` | `Helios Grocery` | yes |
| q22 | join on the current assignment (valid_to IS NULL) | `Helios Grocery` | `Helios Grocery` | NO (same answer) |
| q22 | strftime('%W') instead of ISO week (week numbers shifted by one) | `Helios Grocery` | `Helios Grocery` | NO (same answer) |
| q23 | always use scheme_version 1 (code 96 treated as a decline) | `29` | `35` | yes |
| q23 | status = FAILED as 'timed out' (declines included) | `35` | `35` | NO (same answer) |
| q24 | count log events of every level (INFO/WARN included) in the window | `83` | `83` | NO (same answer) |
| q24 | ERROR events of all components (not only the changed one) in the window | `22` | `83` | yes |
| q24 | 24-hour window instead of 60 minutes | `31` | `83` | yes |
| q15 | join on current link (end_ts IS NULL) | `2,399,506.17` | `2,463,087.54` | yes |
| q15 | only merchants attached directly to the top-level group (no roll-up) | `146,332.55` | `2,463,087.54` | yes |
| q15 | divide all amounts by 100 (ignore dim_currency.exponent) | `2,463,087.54` | `2,463,087.54` | NO (same answer) |
| q16 | service_event_h2 only | `2025-W41` | `2025-W11` | yes |
| q16 | strftime('%W') instead of ISO week (both halves) | `2025-W10` | `2025-W11` | yes |
| q16 | service_event_h1 only | `2025-W11` | `2025-W11` | NO (same answer) |
| q17 | scheme_version 2 (stale knowledge from before the migration) | `0.0663` | `0.072` | yes |
| q17 | always use scheme_version 1 | `0.0653` | `0.072` | yes |
| q17 | status = FAILED as 'declined' | `0.077` | `0.072` | yes |
| q18 | latest change before incident.opened_at | `101` | `100` | yes |
| q18 | service_event_h2 only (the incident is in November, so the first linked ERROR is found anyway) | `100` | `100` | NO (same answer) |
| q19 | strftime('%W') instead of ISO week | `2025-W19` | `2025-W20` | yes |
| q19 | divide all amounts by 100 (ignore dim_currency.exponent) | `2025-W37` | `2025-W20` | yes |
| q19 | rate of the transaction date instead of the settlement date | `2025-W49` | `2025-W20` | yes |
| q20 | current links only (end_ts IS NULL) | `145` | `98` | yes |
| q20 | links that started in May only (start_ts within the month) instead of interval overlap | `1` | `98` | yes |
| q25 | service_event_h1 only | `2025-W11` | `2025-W38` | yes |
| q25 | service_event_h2 only | `2025-W38` | `2025-W38` | NO (same answer) |
| q25 | strftime('%W') instead of ISO week (both halves) | `2025-W37` | `2025-W38` | yes |
| q26 | join on the current link (end_ts IS NULL) | `Borealis Online` | `Aurora Coffee Chain` | yes |

### Validation v2: independent re-computation (pandas on the generated frames)

q01..q20 are asserted to have exactly the v1 answers (same gt_sql); the new questions are recomputed independently.

| question | pandas | SQL ground truth | match |
|---|---|---|---|
| q21 | `31` | `31` | ok |
| q22 | `Helios Grocery` | `Helios Grocery` | ok |
| q23 | `35` | `35` | ok |
| q24 | `83` | `83` | ok |
| q25 | `2025-W38` | `2025-W38` | ok |
| q26 | `Aurora Coffee Chain` | `Aurora Coffee Chain` | ok |

### Ground-truth query timings v2

| question | db | ms |
|---|---|---|
| q01 | v1 | 1.2 |
| q02 | v1 | 899.5 |
| q03 | v1 | 228.8 |
| q04 | v1 | 19.6 |
| q05 | v1 | 168.2 |
| q06 | v1 | 794.9 |
| q07 | v1 | 5.5 |
| q08 | v1 | 0.2 |
| q09 | v1 | 0.3 |
| q10 | v1 | 0.7 |
| q11 | v1 | 259.3 |
| q12 | v1 | 137.3 |
| q13 | v1 | 102.4 |
| q14 | v1 | 376.1 |
| q21 | v1 | 0.8 |
| q22 | v1 | 2060.6 |
| q23 | v1 | 2.8 |
| q24 | v1 | 2.0 |
| q15 | v2 | 1086.0 |
| q16 | v2 | 41.3 |
| q17 | v2 | 24.3 |
| q18 | v2 | 58.0 |
| q19 | v2 | 1636.1 |
| q20 | v2 | 0.6 |
| q25 | v2 | 87.0 |
| q26 | v2 | 867.2 |
