# Memory modes report — analysis_glm

Runs: `glm_icl_r1` = runs/glm_icl_r1 (glm, icl), `glm_memory_guided_r1` = runs/glm_memory_guided_r1 (glm, memory), `glm_memory_r1` = runs/glm_memory_r1 (glm, memory), `glm_stateless_r1` = runs/glm_stateless_r1 (glm, stateless)

Silent migration after question 18 (index in the full list).

## Overview

| run | model | mode | accuracy | pre-drift | post-drift | errors | no answer | cost | wall | n_sql | slow | n_bash |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| glm_icl_r1 | glm | icl | 26/26 (100%) | 18/18 (100%) | 8/8 (100%) | 0 | 0 | $0.1443 | 718s | 121 | 12 | 0 |
| glm_memory_guided_r1 | glm | memory | 26/26 (100%) | 18/18 (100%) | 8/8 (100%) | 0 | 0 | $0.0518 | 1253s | 286 | 4 | 74 |
| glm_memory_r1 | glm | memory | 26/26 (100%) | 18/18 (100%) | 8/8 (100%) | 0 | 0 | $0.0527 | 1462s | 423 | 5 | 35 |
| glm_stateless_r1 | glm | stateless | 26/26 (100%) | 18/18 (100%) | 8/8 (100%) | 0 | 0 | $0.0329 | 958s | 367 | 5 | 0 |

## Per-question correctness

✓ correct · ✗ wrong · ∅ no answer · ⚠ error · — missing

| q | phase | gt | glm_icl_r1 | glm_memory_guided_r1 | glm_memory_r1 | glm_stateless_r1 | class |
|---|---|---|---|---|---|---|---|
| q01 | pre-drift | 36531.85 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q02 | pre-drift | 2025-W51 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q03 | pre-drift | 815909.97 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q04 | pre-drift | 0.1014 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q05 | pre-drift | OSX-3 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q06 | pre-drift | 2025-05 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q07 | pre-drift | v4.18.0 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q08 | pre-drift | 14.96 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q09 | pre-drift | 0.7869 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q10 | pre-drift | r.svensson | ✓ | ✓ | ✓ | ✓ | all-correct |
| q11 | pre-drift | 743 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q12 | pre-drift | 54 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q13 | pre-drift | Helios Group | ✓ | ✓ | ✓ | ✓ | all-correct |
| q14 | pre-drift | 2025-08 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q21 | pre-drift | 31 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q22 | pre-drift | Helios Grocery | ✓ | ✓ | ✓ | ✓ | all-correct |
| q23 | pre-drift | 35 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q24 | pre-drift | 83 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q15 | post-drift | 2463087.54 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q16 | post-drift | 2025-W11 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q17 | post-drift | 0.072 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q18 | post-drift | 100 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q19 | post-drift | 2025-W20 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q20 | post-drift | 98 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q25 | post-drift | 2025-W38 | ✓ | ✓ | ✓ | ✓ | all-correct |
| q26 | post-drift | Aurora Coffee Chain | ✓ | ✓ | ✓ | ✓ | all-correct |

## Divergence classes

| class | n | questions |
|---|---|---|
| all-correct | 26 | q01, q02, q03, q04, q05, q06, q07, q08, q09, q10, q11, q12, q13, q14, q21, q22, q23, q24, q15, q16, q17, q18, q19, q20, q25, q26 |

## Answers on divergent questions

(none)

## Cost structure by run

Tokens: uncached input / cached input / cache writes / output (reasoning ⊂ output).

| run | uncached in | cached in | cache write | cached share | output | reasoning | cost | cost src | wall | turns | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glm_icl_r1 | 50k | 4.64M | 0 | 99% | 42k | 19k | $0.1443 | known | 718s | 104 | 78127 |
| glm_memory_guided_r1 | 196k | 1.26M | 0 | 87% | 72k | 33k | $0.0518 | known | 1253s | 262 | 8980 |
| glm_memory_r1 | 158k | 1.36M | 0 | 90% | 80k | 42k | $0.0527 | known | 1462s | 290 | 7768 |
| glm_stateless_r1 | 139k | 753k | 0 | 84% | 68k | 36k | $0.0329 | known | 958s | 227 | 7941 |

## Per-question metrics — `glm_icl_r1`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 12 | 0 | 0 | 7 | 24k | 20k | 2.0k | 908 | $0.0009 | 27s | 5892 |
| q02 | ✓ | 2025-W51 | 20 | 2 | 0 | 11 | 141k | 134k | 8.7k | 5.4k | $0.0050 | 130s | 18132 |
| q03 | ✓ | 815909.97 | 5 | 0 | 0 | 4 | 77k | 76k | 1.7k | 419 | $0.0024 | 28s | 20203 |
| q04 | ✓ | 0.1014 | 5 | 0 | 0 | 4 | 89k | 87k | 1.4k | 775 | $0.0028 | 23s | 23773 |
| q05 | ✓ | OSX-3 | 1 | 0 | 0 | 2 | 48k | 48k | 480 | 129 | $0.0015 | 8s | 24530 |
| q06 | ✓ | 2025-05 | 1 | 0 | 0 | 2 | 50k | 49k | 492 | 72 | $0.0015 | 8s | 25358 |
| q07 | ✓ | v4.18.0 | 6 | 0 | 0 | 4 | 126k | 114k | 1.2k | 693 | $0.0039 | 19s | 38273 |
| q08 | ✓ | 14.96 | 4 | 0 | 0 | 4 | 157k | 155k | 1.1k | 259 | $0.0048 | 22s | 40056 |
| q09 | ✓ | 0.7869 | 3 | 0 | 0 | 3 | 121k | 121k | 400 | 95 | $0.0037 | 7s | 40807 |
| q10 | ✓ | r.svensson | 5 | 0 | 0 | 4 | 167k | 165k | 712 | 242 | $0.0051 | 11s | 42754 |
| q11 | ✓ | 743 | 4 | 0 | 0 | 3 | 130k | 129k | 569 | 157 | $0.0039 | 11s | 43713 |
| q12 | ✓ | 54 | 2 | 0 | 0 | 2 | 89k | 87k | 425 | 95 | $0.0027 | 7s | 44953 |
| q13 | ✓ | Helios Group | 1 | 0 | 0 | 2 | 91k | 90k | 630 | 208 | $0.0028 | 9s | 45852 |
| q14 | ✓ | 2025-08 | 1 | 0 | 0 | 2 | 92k | 92k | 300 | 20 | $0.0028 | 6s | 46560 |
| q21 | ✓ | 31 | 1 | 0 | 0 | 2 | 94k | 93k | 358 | 83 | $0.0029 | 5s | 47656 |
| q22 | ✓ | Helios Grocery | 11 | 6 | 0 | 10 | 544k | 539k | 10k | 5.2k | $0.0172 | 186s | 60949 |
| q23 | ✓ | 35 | 4 | 2 | 0 | 5 | 313k | 312k | 2.7k | 1.6k | $0.0096 | 47s | 63888 |
| q24 | ✓ | 83 | 1 | 0 | 0 | 2 | 129k | 128k | 321 | 69 | $0.0039 | 6s | 64773 |
| q15 | ✓ | 2463087.54 | 19 | 0 | 0 | 13 | 878k | 875k | 3.3k | 868 | $0.0266 | 60s | 70357 |
| q16 | ✓ | 2025-W11 | 4 | 0 | 0 | 3 | 212k | 212k | 595 | 121 | $0.0064 | 12s | 71332 |
| q17 | ✓ | 0.0720 | 1 | 0 | 0 | 2 | 143k | 143k | 290 | 30 | $0.0043 | 5s | 71785 |
| q18 | ✓ | 100 | 4 | 0 | 0 | 4 | 289k | 288k | 531 | 95 | $0.0087 | 9s | 72775 |
| q19 | ✓ | 2025-W20 | 3 | 1 | 0 | 3 | 222k | 221k | 2.0k | 1.0k | $0.0068 | 33s | 75484 |
| q20 | ✓ | 98 | 1 | 0 | 0 | 2 | 152k | 151k | 759 | 247 | $0.0046 | 13s | 76389 |
| q25 | ✓ | 2025-W38 | 1 | 0 | 0 | 2 | 153k | 153k | 460 | 41 | $0.0046 | 8s | 76987 |
| q26 | ✓ | Aurora Coffee Chain | 1 | 1 | 0 | 2 | 155k | 154k | 805 | 269 | $0.0047 | 18s | 78127 |

Slow SQL (> 1 s) in `glm_icl_r1`:

- q02 (1453.0 ms): `WITH RECURSIVE grp AS ( SELECT group_id FROM dim_merchant_group WHERE name = 'Helios Grocery' UNION ALL SELECT g.group_id FROM dim_merchant_group g JOIN grp ON g.parent_group_id = grp.group_id ), base AS ( SELECT substr(t.ts_utc,1,10) AS d FROM txn t JOIN terminal_assignment ta ON ta.terminal_id = t`
- q02 (1256.8 ms): `SELECT (SELECT COUNT(*) FROM txn) AS total_txn, (SELECT COUNT(*) FROM txn t JOIN terminal_assignment ta ON ta.terminal_id=t.terminal_id AND t.ts_utc >= ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc < ta.valid_to)) AS matched_any, (SELECT COUNT(*) FROM txn t JOIN terminal_assignment ta ON ta.ter`
- q22 (7979.1 ms): `WITH RECURSIVE divtree AS ( SELECT g.group_id, g.name AS div_name, g.group_id AS div_id FROM dim_merchant_group g JOIN dim_merchant_group p ON p.group_id = g.parent_group_id WHERE p.parent_group_id IS NULL UNION ALL SELECT d.group_id, t.div_name, t.div_id FROM dim_merchant_group d JOIN divtree t ON `
- q22 (1042.5 ms): `WITH base AS ( SELECT substr(t.ts_utc,1,10) AS d, t.terminal_id FROM txn t JOIN terminal_assignment ta ON ta.terminal_id = t.terminal_id AND t.ts_utc >= ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc < ta.valid_to) JOIN dim_merchant m ON m.merchant_id = ta.merchant_id WHERE m.group_id IN (10,11,`
- q22 (1516.6 ms): `WITH RECURSIVE divtree AS ( SELECT g.group_id, g.name AS div_name, g.group_id AS div_id FROM dim_merchant_group g JOIN dim_merchant_group p ON p.group_id = g.parent_group_id WHERE p.parent_group_id IS NULL UNION ALL SELECT d.group_id, t.div_name, t.div_id FROM dim_merchant_group d JOIN divtree t ON `
- q22 (4167.1 ms): `WITH RECURSIVE divtree AS ( SELECT g.group_id, g.name AS div_name, g.group_id AS div_id FROM dim_merchant_group g JOIN dim_merchant_group p ON p.group_id = g.parent_group_id WHERE p.parent_group_id IS NULL UNION ALL SELECT d.group_id, t.div_name, t.div_id FROM dim_merchant_group d JOIN divtree t ON `
- q22 (7634.8 ms): `WITH RECURSIVE divtree AS ( SELECT g.group_id, g.name AS div_name, g.group_id AS div_id FROM dim_merchant_group g JOIN dim_merchant_group p ON p.group_id = g.parent_group_id WHERE p.parent_group_id IS NULL UNION ALL SELECT d.group_id, t.div_name, t.div_id FROM dim_merchant_group d JOIN divtree t ON `
- q22 (7412.6 ms): `WITH RECURSIVE divtree AS ( SELECT g.group_id, g.name AS div_name, g.group_id AS div_id FROM dim_merchant_group g JOIN dim_merchant_group p ON p.group_id = g.parent_group_id WHERE p.parent_group_id IS NULL UNION ALL SELECT d.group_id, t.div_name, t.div_id FROM dim_merchant_group d JOIN divtree t ON `
- q23 (1483.6 ms): `WITH seq AS ( SELECT txn_id, terminal_id, ts_utc, LEAD(ts_utc) OVER (PARTITION BY terminal_id ORDER BY ts_utc, txn_id) AS next_ts FROM txn ) SELECT COUNT(*) AS retried, SUM(CASE WHEN s.ts_utc >= '2025-09-18 00:00:00' AND s.ts_utc < '2025-09-19 00:00:00' AND rcd.is_timeout=1 THEN 1 ELSE 0 END) AS tim`
- q23 (1504.0 ms): `WITH seq AS ( SELECT txn_id, terminal_id, ts_utc, response_code, LEAD(ts_utc) OVER (PARTITION BY terminal_id ORDER BY ts_utc, txn_id) AS next_ts FROM txn ) SELECT COUNT(*) AS n_timeouts, SUM(CASE WHEN next_ts IS NOT NULL AND next_ts > ts_utc AND next_ts <= datetime(ts_utc, '+90 seconds') THEN 1 ELSE`
- q19 (3086.6 ms): `WITH calc AS ( SELECT s.settlement_id, s.settled_at, s.settled_eur_minor, ROUND(1.0 * t.amount_minor / (CASE c.exponent WHEN 0 THEN 1.0 WHEN 2 THEN 100.0 WHEN 3 THEN 1000.0 END) * f.eur_per_unit * 100.0) AS recomp FROM settlement s JOIN txn t ON t.txn_id = s.txn_id JOIN dim_currency c ON c.currency_`
- q26 (1090.5 ms): `WITH leaves AS ( SELECT g.group_id, g.name FROM dim_merchant_group g WHERE g.group_id NOT IN (SELECT parent_group_id FROM dim_merchant_group WHERE parent_group_id IS NOT NULL) ), h1 AS ( SELECT m.merchant_group_id AS gid, COUNT(*) AS n FROM txn t JOIN terminal_merchant_link l ON l.terminal_id = t.te`

## Per-question metrics — `glm_memory_guided_r1`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 11 | 0 | 3 | 9 | 32k | 28k | 2.1k | 475 | $0.0011 | 26s | 5624 |
| q02 | ✓ | 2025-W51 | 21 | 2 | 3 | 17 | 96k | 75k | 6.0k | 3.2k | $0.0035 | 118s | 9984 |
| q03 | ✓ | 815909.97 | 18 | 0 | 3 | 12 | 79k | 71k | 4.1k | 1.9k | $0.0027 | 41s | 11011 |
| q04 | ✓ | 0.1014 | 9 | 0 | 3 | 8 | 37k | 32k | 2.4k | 1.2k | $0.0013 | 37s | 7970 |
| q05 | ✓ | OSX-3 | 6 | 0 | 2 | 7 | 24k | 17k | 2.0k | 786 | $0.0009 | 42s | 5596 |
| q06 | ✓ | 2025-05 | 9 | 0 | 2 | 10 | 46k | 41k | 3.0k | 1.1k | $0.0016 | 54s | 7241 |
| q07 | ✓ | v4.18.0 | 10 | 0 | 3 | 10 | 80k | 65k | 1.6k | 617 | $0.0026 | 27s | 16571 |
| q08 | ✓ | 14.96 | 7 | 0 | 3 | 10 | 27k | 25k | 1.2k | 315 | $0.0009 | 22s | 3755 |
| q09 | ✓ | 0.7869 | 16 | 0 | 3 | 12 | 83k | 73k | 2.2k | 826 | $0.0027 | 52s | 10865 |
| q10 | ✓ | r.svensson | 9 | 0 | 3 | 10 | 44k | 38k | 1.7k | 850 | $0.0015 | 42s | 6411 |
| q11 | ✓ | 743 | 14 | 0 | 3 | 10 | 56k | 49k | 2.4k | 1.3k | $0.0019 | 60s | 8842 |
| q12 | ✓ | 54 | 10 | 0 | 3 | 9 | 32k | 27k | 1.8k | 810 | $0.0012 | 47s | 6127 |
| q13 | ✓ | Helios Group | 10 | 0 | 3 | 9 | 43k | 38k | 2.6k | 1.4k | $0.0015 | 50s | 7804 |
| q14 | ✓ | 2025-08 | 7 | 0 | 2 | 7 | 42k | 35k | 2.0k | 945 | $0.0014 | 25s | 8174 |
| q21 | ✓ | 31 | 6 | 0 | 2 | 7 | 27k | 23k | 907 | 311 | $0.0009 | 13s | 5493 |
| q22 | ✓ | Helios Grocery | 6 | 0 | 3 | 8 | 59k | 52k | 5.3k | 3.0k | $0.0022 | 108s | 11876 |
| q23 | ✓ | 35 | 14 | 0 | 3 | 11 | 81k | 74k | 4.4k | 2.6k | $0.0028 | 53s | 11893 |
| q24 | ✓ | 83 | 8 | 0 | 2 | 8 | 33k | 28k | 1.0k | 290 | $0.0011 | 21s | 5484 |
| q15 | ✓ | 2463087.54 | 21 | 0 | 2 | 12 | 84k | 72k | 4.1k | 1.5k | $0.0035 | 88s | 10456 |
| q16 | ✓ | 2025-W11 | 14 | 0 | 3 | 12 | 81k | 67k | 4.5k | 2.1k | $0.0038 | 84s | 10783 |
| q17 | ✓ | 0.0720 | 10 | 0 | 3 | 9 | 45k | 39k | 2.7k | 1.1k | $0.0016 | 43s | 8126 |
| q18 | ✓ | 100 | 11 | 0 | 3 | 10 | 49k | 44k | 1.8k | 738 | $0.0017 | 24s | 7579 |
| q19 | ✓ | 2025-W20 | 14 | 1 | 6 | 17 | 116k | 108k | 5.2k | 2.7k | $0.0040 | 52s | 12174 |
| q20 | ✓ | 98 | 10 | 0 | 2 | 11 | 65k | 58k | 2.2k | 928 | $0.0021 | 43s | 7913 |
| q25 | ✓ | 2025-W38 | 8 | 0 | 3 | 9 | 46k | 39k | 2.4k | 911 | $0.0016 | 49s | 7834 |
| q26 | ✓ | Aurora Coffee Chain | 7 | 1 | 3 | 8 | 45k | 39k | 2.2k | 929 | $0.0016 | 30s | 8980 |

Slow SQL (> 1 s) in `glm_memory_guided_r1`:

- q02 (1067.6 ms): `WITH w AS ( SELECT t.txn_id, CAST((julianday(date(substr(t.ts_utc,1,10), '-6 days', 'weekday 1')) - julianday(date(strftime('%Y', date(substr(t.ts_utc,1,10), '-3 days', 'weekday 4')) || '-01-04', '-6 days', 'weekday 1')))/7 AS INTEGER) + 1 AS wk, strftime('%Y', date(substr(t.ts_utc,1,10), '-3 days',`
- q02 (1038.6 ms): `SELECT (SELECT COUNT(*) FROM txn t JOIN terminal_assignment ta ON t.terminal_id=ta.terminal_id AND t.ts_utc>=ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc<ta.valid_to) JOIN dim_merchant m ON m.merchant_id=ta.merchant_id WHERE m.group_id IN (10,11,12,13,14)) AS matched, (SELECT COUNT(*) FROM txn`
- q19 (1069.7 ms): `WITH base AS ( SELECT st.settlement_id, st.settled_eur_minor, date(st.settled_at) AS sdate, ROUND((CAST(t.amount_minor AS REAL) / POW(10, c.exponent)) * f.eur_per_unit * 100) AS recomp FROM settlement st JOIN txn t ON t.txn_id = st.txn_id JOIN dim_currency c ON c.currency_id = t.currency_id JOIN fx_`
- q26 (1275.0 ms): `WITH leaf AS ( SELECT g.group_id, g.name FROM dim_merchant_group g WHERE NOT EXISTS (SELECT 1 FROM dim_merchant_group c WHERE c.parent_group_id = g.group_id) ), t AS ( SELECT t.txn_id, t.ts_utc, m.merchant_group_id AS gid, CASE WHEN t.ts_utc < '2025-07-01 00:00:00' THEN 'h1' ELSE 'h2' END AS half FR`

## Per-question metrics — `glm_memory_r1`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 15 | 0 | 1 | 11 | 26k | 20k | 1.8k | 546 | $0.0010 | 43s | 4708 |
| q02 | ✓ | 2025-W51 | 24 | 2 | 1 | 19 | 154k | 147k | 9.1k | 4.0k | $0.0054 | 186s | 13880 |
| q03 | ✓ | 815909.97 | 27 | 0 | 2 | 18 | 81k | 74k | 3.6k | 1.5k | $0.0028 | 67s | 8623 |
| q04 | ✓ | 0.1014 | 8 | 0 | 0 | 7 | 29k | 24k | 1.5k | 666 | $0.0010 | 30s | 6221 |
| q05 | ✓ | OSX-3 | 10 | 0 | 1 | 9 | 39k | 33k | 2.0k | 1.1k | $0.0014 | 44s | 7033 |
| q06 | ✓ | 2025-05 | 26 | 0 | 2 | 16 | 102k | 94k | 5.3k | 3.4k | $0.0035 | 71s | 11977 |
| q07 | ✓ | v4.18.0 | 10 | 0 | 1 | 9 | 21k | 17k | 1.0k | 596 | $0.0007 | 18s | 4153 |
| q08 | ✓ | 14.96 | 11 | 0 | 1 | 9 | 17k | 15k | 1.3k | 352 | $0.0006 | 21s | 3237 |
| q09 | ✓ | 0.7869 | 16 | 0 | 1 | 8 | 26k | 22k | 2.0k | 1.0k | $0.0010 | 35s | 6027 |
| q10 | ✓ | r.svensson | 12 | 0 | 1 | 8 | 20k | 17k | 886 | 277 | $0.0007 | 19s | 3794 |
| q11 | ✓ | 743 | 14 | 0 | 1 | 10 | 35k | 31k | 2.0k | 989 | $0.0012 | 31s | 5463 |
| q12 | ✓ | 54 | 15 | 0 | 1 | 9 | 35k | 30k | 1.5k | 632 | $0.0012 | 19s | 6781 |
| q13 | ✓ | Helios Group | 26 | 0 | 1 | 13 | 48k | 44k | 2.4k | 1.3k | $0.0017 | 43s | 6466 |
| q14 | ✓ | 2025-08 | 26 | 0 | 1 | 14 | 96k | 86k | 3.9k | 2.5k | $0.0032 | 114s | 12087 |
| q21 | ✓ | 31 | 9 | 0 | 2 | 8 | 24k | 21k | 760 | 198 | $0.0008 | 13s | 4660 |
| q22 | ✓ | Helios Grocery | 20 | 1 | 1 | 13 | 78k | 70k | 6.0k | 3.9k | $0.0029 | 57s | 12025 |
| q23 | ✓ | 35 | 11 | 1 | 1 | 8 | 38k | 33k | 3.0k | 1.9k | $0.0014 | 66s | 7892 |
| q24 | ✓ | 83 | 12 | 0 | 2 | 10 | 22k | 18k | 891 | 239 | $0.0007 | 20s | 4003 |
| q15 | ✓ | 2463087.54 | 38 | 0 | 7 | 20 | 313k | 294k | 10k | 5.6k | $0.0103 | 200s | 27389 |
| q16 | ✓ | 2025-W11 | 16 | 0 | 1 | 14 | 58k | 51k | 5.4k | 2.4k | $0.0022 | 87s | 7762 |
| q17 | ✓ | 0.0720 | 11 | 0 | 1 | 10 | 50k | 43k | 2.0k | 1.2k | $0.0017 | 35s | 7833 |
| q18 | ✓ | 100 | 12 | 0 | 2 | 9 | 35k | 27k | 1.0k | 470 | $0.0012 | 25s | 6572 |
| q19 | ✓ | 2025-W20 | 15 | 1 | 1 | 11 | 59k | 53k | 5.1k | 2.9k | $0.0022 | 96s | 9810 |
| q20 | ✓ | 98 | 13 | 0 | 0 | 9 | 36k | 31k | 1.9k | 858 | $0.0013 | 39s | 6520 |
| q25 | ✓ | 2025-W38 | 9 | 0 | 2 | 9 | 33k | 27k | 2.9k | 1.6k | $0.0013 | 51s | 6108 |
| q26 | ✓ | Aurora Coffee Chain | 17 | 0 | 0 | 9 | 40k | 34k | 2.7k | 1.6k | $0.0014 | 31s | 7768 |

Slow SQL (> 1 s) in `glm_memory_r1`:

- q02 (1410.1 ms): `WITH RECURSIVE sub(id) AS ( SELECT 10 UNION ALL SELECT g.group_id FROM dim_merchant_group g JOIN sub ON g.parent_group_id = sub.id ), merchants AS ( SELECT merchant_id FROM dim_merchant WHERE group_id IN (SELECT id FROM sub) ), s1 AS ( SELECT t.txn_id, date(t.ts_utc) AS d FROM txn t JOIN terminal_as`
- q02 (30015.3 ms): `-- Cross-check: verify date ranges per top week and totals WITH RECURSIVE sub(id) AS (SELECT 10 UNION ALL SELECT g.group_id FROM dim_merchant_group g JOIN sub ON g.parent_group_id = sub.id), merchants AS (SELECT merchant_id FROM dim_merchant WHERE group_id IN (SELECT id FROM sub)), s1 AS ( SELECT t.`
- q22 (1594.1 ms): `WITH RECURSIVE weeks(w) AS (SELECT 1 UNION ALL SELECT w+1 FROM weeks WHERE w<52), divs AS ( SELECT group_id AS div_id, name FROM dim_merchant_group WHERE parent_group_id IN (SELECT group_id FROM dim_merchant_group WHERE parent_group_id IS NULL) ), sub AS ( SELECT d.div_id, g.group_id AS sub_id FROM `
- q23 (1137.6 ms): `WITH timeouts AS ( SELECT s.txn_id, s.ts_utc, s.terminal_id FROM txn s JOIN response_code_dict r ON r.code = s.response_code AND r.is_timeout = 1 AND r.valid_from <= s.ts_utc AND (r.valid_to IS NULL OR r.valid_to > s.ts_utc) WHERE s.ts_utc >= '2025-09-18 00:00:00' AND s.ts_utc < '2025-09-19 00:00:00`
- q19 (1659.7 ms): `WITH base AS ( SELECT s.settled_eur_minor, t.amount_minor, c.exponent, f.eur_per_unit, date(s.settled_at) AS d, (CAST(strftime('%w', date(s.settled_at)) AS INTEGER) + 6) % 7 + 1 AS isodow FROM settlement s JOIN txn t ON t.txn_id = s.txn_id JOIN dim_currency c ON c.currency_id = t.currency_id JOIN fx`

## Per-question metrics — `glm_stateless_r1`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 13 | 0 | 0 | 6 | 21k | 17k | 3.2k | 1.3k | $0.0009 | 26s | 7387 |
| q02 | ✓ | 2025-W51 | 15 | 1 | 0 | 9 | 40k | 33k | 4.1k | 2.5k | $0.0015 | 52s | 8586 |
| q03 | ✓ | 815909.97 | 27 | 0 | 0 | 15 | 57k | 51k | 2.9k | 1.4k | $0.0020 | 43s | 7761 |
| q04 | ✓ | 0.1014 | 12 | 0 | 0 | 7 | 26k | 20k | 2.1k | 1.0k | $0.0010 | 23s | 7173 |
| q05 | ✓ | OSX-3 | 12 | 0 | 0 | 9 | 40k | 35k | 1.8k | 1.1k | $0.0014 | 34s | 6877 |
| q06 | ✓ | 2025-05 | 17 | 0 | 0 | 12 | 32k | 28k | 2.5k | 1.1k | $0.0012 | 27s | 5896 |
| q07 | ✓ | v4.18.0 | 8 | 0 | 0 | 6 | 16k | 12k | 812 | 361 | $0.0006 | 14s | 4926 |
| q08 | ✓ | 14.96 | 9 | 0 | 0 | 6 | 15k | 12k | 993 | 242 | $0.0005 | 14s | 3735 |
| q09 | ✓ | 0.7869 | 15 | 0 | 0 | 9 | 23k | 19k | 1.4k | 521 | $0.0008 | 14s | 5221 |
| q10 | ✓ | r.svensson | 12 | 0 | 0 | 8 | 22k | 18k | 857 | 407 | $0.0007 | 17s | 4414 |
| q11 | ✓ | 743 | 13 | 0 | 0 | 7 | 23k | 17k | 1.1k | 465 | $0.0008 | 18s | 4832 |
| q12 | ✓ | 54 | 13 | 0 | 0 | 6 | 19k | 14k | 1.4k | 667 | $0.0007 | 19s | 5945 |
| q13 | ✓ | Helios Group | 21 | 0 | 0 | 12 | 57k | 50k | 2.6k | 1.6k | $0.0019 | 37s | 8506 |
| q14 | ✓ | 2025-08 | 9 | 0 | 0 | 6 | 21k | 17k | 1.6k | 747 | $0.0008 | 20s | 5924 |
| q21 | ✓ | 31 | 7 | 0 | 0 | 6 | 15k | 12k | 631 | 242 | $0.0005 | 8s | 4012 |
| q22 | ✓ | Helios Grocery | 21 | 2 | 0 | 12 | 71k | 65k | 6.9k | 4.4k | $0.0027 | 104s | 11721 |
| q23 | ✓ | 35 | 13 | 0 | 0 | 9 | 41k | 27k | 3.2k | 1.7k | $0.0015 | 43s | 9890 |
| q24 | ✓ | 83 | 10 | 0 | 0 | 7 | 18k | 14k | 783 | 330 | $0.0006 | 16s | 4075 |
| q15 | ✓ | 2463087.54 | 29 | 0 | 0 | 19 | 100k | 86k | 5.3k | 2.8k | $0.0035 | 123s | 11121 |
| q16 | ✓ | 2025-W11 | 9 | 0 | 0 | 7 | 21k | 17k | 2.3k | 1.2k | $0.0008 | 44s | 5266 |
| q17 | ✓ | 0.0720 | 9 | 0 | 0 | 8 | 32k | 26k | 1.6k | 853 | $0.0011 | 28s | 7097 |
| q18 | ✓ | 100 | 12 | 0 | 0 | 8 | 24k | 21k | 1.0k | 525 | $0.0008 | 24s | 4892 |
| q19 | ✓ | 2025-W20 | 19 | 1 | 0 | 10 | 75k | 69k | 9.3k | 5.7k | $0.0031 | 90s | 15048 |
| q20 | ✓ | 98 | 10 | 0 | 0 | 6 | 9.3k | 7.9k | 1.0k | 351 | $0.0004 | 15s | 2552 |
| q25 | ✓ | 2025-W38 | 19 | 0 | 0 | 9 | 40k | 36k | 5.0k | 2.4k | $0.0016 | 73s | 8252 |
| q26 | ✓ | Aurora Coffee Chain | 13 | 1 | 0 | 8 | 34k | 29k | 3.4k | 1.9k | $0.0013 | 32s | 7941 |

Slow SQL (> 1 s) in `glm_stateless_r1`:

- q02 (1568.7 ms): `WITH RECURSIVE g AS ( SELECT group_id FROM dim_merchant_group WHERE name = 'Helios Grocery' UNION ALL SELECT mg.group_id FROM dim_merchant_group mg JOIN g ON mg.parent_group_id = g.group_id ), matched AS ( SELECT t.txn_id, t.ts_utc FROM txn t JOIN terminal_assignment ta ON ta.terminal_id = t.termina`
- q22 (2523.1 ms): `WITH RECURSIVE g2 AS ( SELECT group_id, name FROM dim_merchant_group WHERE level = 2 ), dsc(g, d) AS ( SELECT group_id, group_id FROM g2 UNION ALL SELECT d.g, mg.group_id FROM dsc d JOIN dim_merchant_group mg ON mg.parent_group_id = d.d ), txn2025 AS ( SELECT ta.merchant_id, strftime('%Y', date(t.ts`
- q22 (1137.5 ms): `WITH RECURSIVE dsc(d) AS (SELECT 10 UNION ALL SELECT mg.group_id FROM dsc JOIN dim_merchant_group mg ON mg.parent_group_id = dsc.d), txn2025 AS ( SELECT ta.merchant_id, strftime('%Y', date(t.ts_utc,'-3 days','weekday 4')) AS iy, CAST((julianday(date(t.ts_utc,'-3 days','weekday 4')) - julianday(date(`
- q19 (1889.3 ms): `WITH base AS ( SELECT s.settlement_id, s.settled_at, s.settled_eur_minor, t.amount_minor, t.currency_id, c.exponent, date(s.settled_at) AS sd FROM settlement s JOIN txn t ON t.txn_id = s.txn_id JOIN dim_currency c ON c.currency_id = t.currency_id ), j AS ( SELECT b.*, f.eur_per_unit FROM base b JOIN`
- q26 (1197.3 ms): `SELECT COUNT(*) AS total_pairs, COUNT(DISTINCT t.txn_id) AS total_txn FROM txn t JOIN terminal_merchant_link l ON l.terminal_id = t.terminal_id AND t.ts_utc >= l.start_ts AND (l.end_ts IS NULL OR t.ts_utc <= l.end_ts)`

## ICL: context growth by question

`glm_icl_r1`

| q | context tokens at end | episode input tokens | episode cached |
|---|---|---|---|
| q01 | 5892 | 24k | 20k |
| q02 | 18132 | 141k | 134k |
| q03 | 20203 | 77k | 76k |
| q04 | 23773 | 89k | 87k |
| q05 | 24530 | 48k | 48k |
| q06 | 25358 | 50k | 49k |
| q07 | 38273 | 126k | 114k |
| q08 | 40056 | 157k | 155k |
| q09 | 40807 | 121k | 121k |
| q10 | 42754 | 167k | 165k |
| q11 | 43713 | 130k | 129k |
| q12 | 44953 | 89k | 87k |
| q13 | 45852 | 91k | 90k |
| q14 | 46560 | 92k | 92k |
| q21 | 47656 | 94k | 93k |
| q22 | 60949 | 544k | 539k |
| q23 | 63888 | 313k | 312k |
| q24 | 64773 | 129k | 128k |
| q15 | 70357 | 878k | 875k |
| q16 | 71332 | 212k | 212k |
| q17 | 71785 | 143k | 143k |
| q18 | 72775 | 289k | 288k |
| q19 | 75484 | 222k | 221k |
| q20 | 76389 | 152k | 151k |
| q25 | 76987 | 153k | 153k |
| q26 | 78127 | 155k | 154k |

## Memory: memory dir size and bash calls by question

`glm_memory_guided_r1`

| q | memory bytes | files | bash calls | post-submit turns |
|---|---|---|---|---|
| q01 | 785 | 1 | 3 | 1 |
| q02 | 1068 | 1 | 3 | 0 |
| q03 | 1394 | 1 | 3 | 0 |
| q04 | 1789 | 1 | 3 | 1 |
| q05 | 2088 | 1 | 2 | 1 |
| q06 | 2581 | 1 | 2 | 0 |
| q07 | 2944 | 1 | 3 | 0 |
| q08 | 3177 | 1 | 3 | 1 |
| q09 | 3494 | 1 | 3 | 1 |
| q10 | 3938 | 1 | 3 | 0 |
| q11 | 4398 | 1 | 3 | 0 |
| q12 | 4702 | 1 | 3 | 0 |
| q13 | 5097 | 1 | 3 | 1 |
| q14 | 5375 | 1 | 2 | 0 |
| q21 | 5576 | 1 | 2 | 0 |
| q22 | 6084 | 1 | 3 | 0 |
| q23 | 6481 | 1 | 3 | 0 |
| q24 | 6688 | 1 | 2 | 0 |
| q15 | 7323 | 1 | 2 | 0 |
| q16 | 7891 | 1 | 3 | 0 |
| q17 | 8498 | 1 | 3 | 0 |
| q18 | 8814 | 1 | 3 | 1 |
| q19 | 9498 | 1 | 6 | 0 |
| q20 | 9996 | 1 | 2 | 0 |
| q25 | 10384 | 1 | 3 | 1 |
| q26 | 10976 | 1 | 3 | 1 |

`glm_memory_r1`

| q | memory bytes | files | bash calls | post-submit turns |
|---|---|---|---|---|
| q01 | 0 | 0 | 1 | 0 |
| q02 | 0 | 0 | 1 | 0 |
| q03 | 0 | 0 | 2 | 0 |
| q04 | 0 | 0 | 0 | 0 |
| q05 | 0 | 0 | 1 | 0 |
| q06 | 0 | 0 | 2 | 0 |
| q07 | 0 | 0 | 1 | 0 |
| q08 | 0 | 0 | 1 | 0 |
| q09 | 0 | 0 | 1 | 0 |
| q10 | 0 | 0 | 1 | 0 |
| q11 | 0 | 0 | 1 | 0 |
| q12 | 0 | 0 | 1 | 0 |
| q13 | 0 | 0 | 1 | 0 |
| q14 | 0 | 0 | 1 | 0 |
| q21 | 0 | 0 | 2 | 0 |
| q22 | 0 | 0 | 1 | 0 |
| q23 | 0 | 0 | 1 | 0 |
| q24 | 0 | 0 | 2 | 0 |
| q15 | 0 | 0 | 7 | 0 |
| q16 | 0 | 0 | 1 | 0 |
| q17 | 0 | 0 | 1 | 0 |
| q18 | 0 | 0 | 2 | 0 |
| q19 | 0 | 0 | 1 | 0 |
| q20 | 0 | 0 | 0 | 0 |
| q25 | 0 | 0 | 2 | 0 |
| q26 | 0 | 0 | 0 | 0 |
