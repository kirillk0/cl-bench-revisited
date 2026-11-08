# Memory modes report — analysis_haiku

Runs: `haiku_icl_r1` = runs/haiku_icl_r1 (haiku, icl), `haiku_memory_guided_r1` = runs/haiku_memory_guided_r1 (haiku, memory), `haiku_memory_r1` = runs/haiku_memory_r1 (haiku, memory), `haiku_stateless_r1` = runs/haiku_stateless_r1 (haiku, stateless), `haiku_stateless_r2` = runs/haiku_stateless_r2 (haiku, stateless)

Silent migration after question 18 (index in the full list).

## Overview

| run | model | mode | accuracy | pre-drift | post-drift | errors | no answer | cost | wall | n_sql | slow | n_bash |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| haiku_icl_r1 | haiku | icl | 26/26 (100%) | 18/18 (100%) | 8/8 (100%) | 0 | 0 | $0.0594 | 152s | 87 | 3 | 0 |
| haiku_memory_guided_r1 | haiku | memory | 26/26 (100%) | 18/18 (100%) | 8/8 (100%) | 0 | 0 | $0.0891 | 396s | 280 | 3 | 59 |
| haiku_memory_r1 | haiku | memory | 26/26 (100%) | 18/18 (100%) | 8/8 (100%) | 0 | 0 | $0.0924 | 425s | 345 | 6 | 30 |
| haiku_stateless_r1 | haiku | stateless | 25/26 (96%) | 17/18 (94%) | 8/8 (100%) | 0 | 0 | $0.0752 | 349s | 335 | 3 | 0 |
| haiku_stateless_r2 | haiku | stateless | 26/26 (100%) | 18/18 (100%) | 8/8 (100%) | 0 | 0 | $0.0760 | 364s | 349 | 5 | 0 |

## Per-question correctness

✓ correct · ✗ wrong · ∅ no answer · ⚠ error · — missing

| q | phase | gt | haiku_icl_r1 | haiku_memory_guided_r1 | haiku_memory_r1 | haiku_stateless_r1 | haiku_stateless_r2 | class |
|---|---|---|---|---|---|---|---|---|
| q01 | pre-drift | 36531.85 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q02 | pre-drift | 2025-W51 | ✓ | ✓ | ✓ | ✗ | ✓ | only-haiku_stateless_r1-wrong |
| q03 | pre-drift | 815909.97 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q04 | pre-drift | 0.1014 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q05 | pre-drift | OSX-3 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q06 | pre-drift | 2025-05 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q07 | pre-drift | v4.18.0 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q08 | pre-drift | 14.96 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q09 | pre-drift | 0.7869 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q10 | pre-drift | r.svensson | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q11 | pre-drift | 743 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q12 | pre-drift | 54 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q13 | pre-drift | Helios Group | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q14 | pre-drift | 2025-08 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q21 | pre-drift | 31 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q22 | pre-drift | Helios Grocery | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q23 | pre-drift | 35 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q24 | pre-drift | 83 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q15 | post-drift | 2463087.54 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q16 | post-drift | 2025-W11 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q17 | post-drift | 0.072 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q18 | post-drift | 100 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q19 | post-drift | 2025-W20 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q20 | post-drift | 98 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q25 | post-drift | 2025-W38 | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q26 | post-drift | Aurora Coffee Chain | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |

## Divergence classes

| class | n | questions |
|---|---|---|
| all-correct | 25 | q01, q03, q04, q05, q06, q07, q08, q09, q10, q11, q12, q13, q14, q21, q22, q23, q24, q15, q16, q17, q18, q19, q20, q25, q26 |
| only-haiku_stateless_r1-wrong | 1 | q02 |

## Answers on divergent questions

| q | gt | haiku_icl_r1 | haiku_memory_guided_r1 | haiku_memory_r1 | haiku_stateless_r1 | haiku_stateless_r2 |
|---|---|---|---|---|---|---|
| q02 | 2025-W51 | 2025-W51 | 2025-W51 | 2025-W51 | 2025-W50 | 2025-W51 |

## Cost structure by run

Tokens: uncached input / cached input / cache writes / output (reasoning ⊂ output).

| run | uncached in | cached in | cache write | cached share | output | reasoning | cost | cost src | wall | turns | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|
| haiku_icl_r1 | 234 | 3.77M | 65k | 98% | 27k | 5.3k | $0.0594 | known | 152s | 91 | 65332 |
| haiku_memory_guided_r1 | 528 | 1.78M | 303k | 85% | 67k | 14k | $0.0891 | known | 396s | 238 | 16598 |
| haiku_memory_r1 | 530 | 1.67M | 305k | 85% | 75k | 17k | $0.0924 | known | 425s | 239 | 16591 |
| haiku_stateless_r1 | 444 | 1.05M | 267k | 80% | 62k | 16k | $0.0752 | known | 349s | 196 | 13081 |
| haiku_stateless_r2 | 454 | 1.09M | 260k | 81% | 65k | 18k | $0.0760 | known | 364s | 201 | 11460 |

## Per-question metrics — `haiku_icl_r1`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 12 | 0 | 0 | 7 | 66k | 45k | 2.0k | 394 | $0.0040 | 12s | 20721 |
| q02 | ✓ | 2025-W51 | 8 | 0 | 0 | 5 | 114k | 109k | 2.9k | 739 | $0.0031 | 15s | 25334 |
| q03 | ✓ | 815909.97 | 3 | 0 | 0 | 4 | 105k | 103k | 1.2k | 144 | $0.0019 | 6s | 27094 |
| q04 | ✓ | 0.1014 | 4 | 0 | 0 | 4 | 117k | 114k | 977 | 224 | $0.0020 | 6s | 30472 |
| q05 | ✓ | OSX-3 | 1 | 0 | 0 | 2 | 62k | 61k | 480 | 52 | $0.0010 | 2s | 31329 |
| q06 | ✓ | 2025-05 | 1 | 0 | 0 | 2 | 64k | 63k | 648 | 35 | $0.0011 | 3s | 32413 |
| q07 | ✓ | v4.18.0 | 9 | 0 | 0 | 6 | 205k | 201k | 1.1k | 187 | $0.0030 | 6s | 35941 |
| q08 | ✓ | 14.96 | 4 | 0 | 0 | 3 | 111k | 109k | 1.1k | 395 | $0.0019 | 6s | 38076 |
| q09 | ✓ | 0.7869 | 4 | 0 | 0 | 4 | 155k | 154k | 823 | 239 | $0.0021 | 5s | 39477 |
| q10 | ✓ | r.svensson | 6 | 0 | 0 | 6 | 245k | 242k | 1.3k | 133 | $0.0034 | 6s | 41872 |
| q11 | ✓ | 743 | 2 | 0 | 0 | 3 | 127k | 126k | 550 | 137 | $0.0016 | 4s | 42613 |
| q12 | ✓ | 54 | 3 | 0 | 0 | 3 | 129k | 128k | 492 | 41 | $0.0017 | 3s | 43630 |
| q13 | ✓ | Helios Group | 1 | 0 | 0 | 2 | 88k | 87k | 805 | 172 | $0.0014 | 4s | 44750 |
| q14 | ✓ | 2025-08 | 1 | 0 | 0 | 2 | 91k | 90k | 619 | 143 | $0.0013 | 4s | 45853 |
| q21 | ✓ | 31 | 1 | 0 | 0 | 2 | 93k | 92k | 306 | 0 | $0.0012 | 2s | 46990 |
| q22 | ✓ | Helios Grocery | 2 | 2 | 0 | 3 | 146k | 143k | 2.5k | 605 | $0.0031 | 14s | 50241 |
| q23 | ✓ | 35 | 1 | 0 | 0 | 2 | 101k | 101k | 578 | 154 | $0.0014 | 4s | 51028 |
| q24 | ✓ | 83 | 1 | 0 | 0 | 2 | 103k | 102k | 290 | 0 | $0.0012 | 2s | 51607 |
| q15 | ✓ | 2463087.54 | 10 | 0 | 0 | 9 | 490k | 484k | 3.3k | 453 | $0.0072 | 15s | 57273 |
| q16 | ✓ | 2025-W11 | 2 | 0 | 0 | 3 | 174k | 172k | 880 | 120 | $0.0023 | 5s | 58472 |
| q17 | ✓ | 0.0720 | 1 | 0 | 0 | 2 | 118k | 117k | 442 | 0 | $0.0015 | 2s | 59156 |
| q18 | ✓ | 100 | 3 | 0 | 0 | 4 | 240k | 238k | 740 | 228 | $0.0029 | 5s | 60509 |
| q19 | ✓ | 2025-W20 | 1 | 1 | 0 | 2 | 122k | 121k | 715 | 182 | $0.0017 | 5s | 61560 |
| q20 | ✓ | 98 | 2 | 0 | 0 | 3 | 186k | 185k | 668 | 216 | $0.0023 | 5s | 62467 |
| q25 | ✓ | 2025-W38 | 1 | 0 | 0 | 2 | 125k | 125k | 364 | 0 | $0.0015 | 2s | 62992 |
| q26 | ✓ | Aurora Coffee Chain | 3 | 0 | 0 | 4 | 257k | 254k | 1.4k | 290 | $0.0035 | 8s | 65332 |

Slow SQL (> 1 s) in `haiku_icl_r1`:

- q22 (1652.0 ms): `WITH RECURSIVE sec AS (SELECT group_id AS sid, group_id AS gid FROM dim_merchant_group WHERE parent_group_id IN (SELECT group_id FROM dim_merchant_group WHERE parent_group_id IS NULL) UNION ALL SELECT sec.sid, g.group_id FROM dim_merchant_group g JOIN sec ON g.parent_group_id=sec.gid), tx AS ( SELEC`
- q22 (1662.2 ms): `WITH RECURSIVE sec AS (SELECT group_id AS sid, group_id AS gid FROM dim_merchant_group WHERE parent_group_id IN (SELECT group_id FROM dim_merchant_group WHERE parent_group_id IS NULL) UNION ALL SELECT sec.sid, g.group_id FROM dim_merchant_group g JOIN sec ON g.parent_group_id=sec.gid), tx AS ( SELEC`
- q19 (1498.3 ms): `WITH x AS ( SELECT s.settlement_id, s.settled_at, s.settled_eur_minor AS actual, ROUND((t.amount_minor*1.0/POWER(10,c.exponent)) * f.eur_per_unit * 100) AS recomputed FROM settlement s JOIN txn t ON t.txn_id=s.txn_id JOIN dim_currency c ON c.currency_id=t.currency_id LEFT JOIN fx_rate_daily f ON f.c`

## Per-question metrics — `haiku_memory_guided_r1`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 14 | 0 | 1 | 9 | 109k | 88k | 2.6k | 362 | $0.0049 | 13s | 21783 |
| q02 | ✓ | 2025-W51 | 22 | 0 | 2 | 13 | 121k | 105k | 4.4k | 1.2k | $0.0052 | 27s | 16964 |
| q03 | ✓ | 815909.97 | 18 | 0 | 2 | 9 | 80k | 68k | 4.1k | 613 | $0.0043 | 18s | 13733 |
| q04 | ✓ | 0.1014 | 11 | 0 | 2 | 10 | 76k | 67k | 2.2k | 505 | $0.0030 | 14s | 10759 |
| q05 | ✓ | OSX-3 | 10 | 0 | 2 | 9 | 68k | 58k | 2.4k | 340 | $0.0030 | 13s | 10535 |
| q06 | ✓ | 2025-05 | 15 | 0 | 3 | 11 | 101k | 89k | 2.9k | 429 | $0.0039 | 17s | 12973 |
| q07 | ✓ | v4.18.0 | 12 | 0 | 1 | 8 | 54k | 45k | 2.0k | 354 | $0.0026 | 11s | 9942 |
| q08 | ✓ | 14.96 | 8 | 0 | 2 | 7 | 51k | 42k | 1.9k | 482 | $0.0026 | 10s | 10633 |
| q09 | ✓ | 0.7869 | 15 | 0 | 2 | 10 | 97k | 85k | 2.5k | 520 | $0.0036 | 15s | 13276 |
| q10 | ✓ | r.svensson | 9 | 0 | 2 | 7 | 46k | 38k | 1.6k | 257 | $0.0022 | 9s | 9397 |
| q11 | ✓ | 743 | 9 | 0 | 3 | 8 | 54k | 46k | 1.6k | 272 | $0.0023 | 10s | 9071 |
| q12 | ✓ | 54 | 9 | 0 | 2 | 9 | 61k | 53k | 2.2k | 463 | $0.0026 | 12s | 9341 |
| q13 | ✓ | Helios Group | 11 | 0 | 3 | 8 | 66k | 55k | 2.9k | 604 | $0.0034 | 19s | 12211 |
| q14 | ✓ | 2025-08 | 8 | 0 | 2 | 7 | 56k | 46k | 2.1k | 388 | $0.0028 | 12s | 11437 |
| q21 | ✓ | 31 | 7 | 0 | 2 | 8 | 85k | 70k | 1.7k | 423 | $0.0034 | 11s | 15447 |
| q22 | ✓ | Helios Grocery | 9 | 1 | 4 | 11 | 106k | 93k | 3.8k | 1.2k | $0.0044 | 24s | 13759 |
| q23 | ✓ | 35 | 9 | 1 | 3 | 11 | 93k | 82k | 2.4k | 542 | $0.0033 | 16s | 11247 |
| q24 | ✓ | 83 | 10 | 0 | 2 | 8 | 58k | 49k | 1.7k | 192 | $0.0024 | 10s | 9462 |
| q15 | ✓ | 2463087.54 | 14 | 0 | 2 | 10 | 106k | 92k | 4.0k | 845 | $0.0046 | 20s | 14895 |
| q16 | ✓ | 2025-W11 | 9 | 0 | 4 | 12 | 124k | 109k | 3.1k | 641 | $0.0045 | 20s | 16010 |
| q17 | ✓ | 0.0720 | 8 | 0 | 1 | 8 | 70k | 59k | 1.7k | 303 | $0.0028 | 11s | 11720 |
| q18 | ✓ | 100 | 12 | 0 | 2 | 10 | 96k | 84k | 2.3k | 359 | $0.0036 | 16s | 13610 |
| q19 | ✓ | 2025-W20 | 5 | 1 | 3 | 9 | 71k | 61k | 2.5k | 747 | $0.0031 | 16s | 10548 |
| q20 | ✓ | 98 | 6 | 0 | 3 | 7 | 80k | 63k | 2.5k | 723 | $0.0040 | 13s | 18317 |
| q25 | ✓ | 2025-W38 | 7 | 0 | 2 | 9 | 45k | 40k | 1.9k | 375 | $0.0021 | 14s | 6631 |
| q26 | ✓ | Aurora Coffee Chain | 13 | 0 | 2 | 10 | 104k | 89k | 3.8k | 1.2k | $0.0047 | 23s | 16598 |

Slow SQL (> 1 s) in `haiku_memory_guided_r1`:

- q22 (2099.7 ms): `WITH RECURSIVE wk(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM wk WHERE x<52), g2 AS ( SELECT g.group_id AS g2id, g.name AS gname FROM dim_merchant_group g WHERE g.level=2 ), anc AS ( SELECT g.group_id AS gid, g.group_id AS aid FROM dim_merchant_group g UNION ALL SELECT a.gid, p.parent_group_id FROM an`
- q23 (1453.0 ms): `WITH t AS ( SELECT txn_id, ts_utc, terminal_id, response_code, status_id, LEAD(ts_utc) OVER (PARTITION BY terminal_id ORDER BY ts_utc, txn_id) AS nxt FROM txn ), rc AS ( SELECT code, is_timeout FROM response_code_dict WHERE scheme_version=2 ) SELECT COUNT(*) AS total_timeouts, SUM(CASE WHEN nxt IS N`
- q19 (1704.9 ms): `WITH x AS ( SELECT s.settlement_id, s.settled_at, s.settled_eur_minor AS act, ROUND(t.amount_minor / CAST(POWER(10, c.exponent) AS REAL) * f.eur_per_unit * 100) AS calc, date(s.settled_at) AS d FROM settlement s JOIN txn t ON t.txn_id=s.txn_id JOIN dim_currency c ON c.currency_id=t.currency_id LEFT `

## Per-question metrics — `haiku_memory_r1`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 13 | 0 | 1 | 10 | 40k | 33k | 2.1k | 227 | $0.0022 | 11s | 6847 |
| q02 | ✓ | 2025-W51 | 15 | 2 | 2 | 12 | 146k | 124k | 3.9k | 885 | $0.0059 | 27s | 22211 |
| q03 | ✓ | 815909.97 | 22 | 0 | 1 | 12 | 126k | 110k | 5.2k | 798 | $0.0056 | 24s | 16354 |
| q04 | ✓ | 0.1014 | 11 | 0 | 0 | 8 | 56k | 46k | 2.0k | 567 | $0.0027 | 11s | 11172 |
| q05 | ✓ | OSX-3 | 11 | 0 | 1 | 8 | 56k | 47k | 2.3k | 426 | $0.0028 | 13s | 10704 |
| q06 | ✓ | 2025-05 | 22 | 0 | 1 | 11 | 145k | 121k | 4.1k | 878 | $0.0062 | 21s | 24765 |
| q07 | ✓ | v4.18.0 | 7 | 0 | 1 | 6 | 66k | 48k | 1.5k | 380 | $0.0035 | 10s | 19278 |
| q08 | ✓ | 14.96 | 10 | 0 | 1 | 8 | 28k | 23k | 1.9k | 489 | $0.0018 | 13s | 5698 |
| q09 | ✓ | 0.7869 | 15 | 0 | 0 | 9 | 78k | 66k | 2.4k | 361 | $0.0034 | 14s | 13063 |
| q10 | ✓ | r.svensson | 8 | 0 | 1 | 6 | 36k | 28k | 1.5k | 254 | $0.0019 | 9s | 8288 |
| q11 | ✓ | 743 | 11 | 0 | 1 | 8 | 51k | 43k | 2.2k | 487 | $0.0026 | 12s | 9232 |
| q12 | ✓ | 54 | 17 | 0 | 1 | 9 | 105k | 88k | 3.7k | 1.1k | $0.0048 | 20s | 17583 |
| q13 | ✓ | Helios Group | 18 | 0 | 1 | 10 | 98k | 84k | 3.6k | 723 | $0.0044 | 18s | 15117 |
| q14 | ✓ | 2025-08 | 17 | 0 | 1 | 11 | 97k | 85k | 3.0k | 453 | $0.0038 | 17s | 13171 |
| q21 | ✓ | 31 | 9 | 0 | 1 | 6 | 41k | 32k | 1.4k | 127 | $0.0021 | 8s | 9852 |
| q22 | ✓ | Helios Grocery | 15 | 1 | 2 | 12 | 75k | 63k | 5.0k | 2.4k | $0.0046 | 29s | 12570 |
| q23 | ✓ | 35 | 10 | 0 | 1 | 8 | 56k | 47k | 2.2k | 602 | $0.0027 | 13s | 10029 |
| q24 | ✓ | 83 | 10 | 0 | 1 | 7 | 38k | 32k | 1.5k | 124 | $0.0019 | 10s | 7681 |
| q15 | ✓ | 2463087.54 | 20 | 0 | 2 | 12 | 127k | 112k | 5.8k | 919 | $0.0059 | 27s | 16742 |
| q16 | ✓ | 2025-W11 | 8 | 0 | 1 | 8 | 47k | 39k | 2.5k | 611 | $0.0025 | 14s | 8218 |
| q17 | ✓ | 0.0720 | 11 | 0 | 1 | 8 | 63k | 53k | 2.0k | 654 | $0.0028 | 13s | 11571 |
| q18 | ✓ | 100 | 15 | 0 | 1 | 11 | 87k | 75k | 2.2k | 432 | $0.0034 | 13s | 13215 |
| q19 | ✓ | 2025-W20 | 12 | 1 | 3 | 8 | 57k | 48k | 3.1k | 908 | $0.0032 | 22s | 10462 |
| q20 | ✓ | 98 | 11 | 0 | 1 | 10 | 79k | 68k | 2.5k | 559 | $0.0032 | 14s | 11478 |
| q25 | ✓ | 2025-W38 | 8 | 0 | 2 | 8 | 56k | 45k | 2.4k | 612 | $0.0029 | 14s | 11380 |
| q26 | ✓ | Aurora Coffee Chain | 19 | 2 | 1 | 13 | 127k | 111k | 4.9k | 1.4k | $0.0055 | 27s | 16591 |

Slow SQL (> 1 s) in `haiku_memory_r1`:

- q02 (1178.5 ms): `WITH x AS (SELECT DISTINCT t.txn_id, t.ts_utc FROM txn t JOIN terminal_assignment ta ON ta.terminal_id=t.terminal_id JOIN dim_merchant m ON m.merchant_id=ta.merchant_id WHERE m.group_id IN (10,11,12,13,14) AND t.ts_utc >= ta.valid_from AND (ta.valid_to IS NULL OR t.ts_utc < ta.valid_to)), w AS (SELE`
- q02 (1002.4 ms): `WITH x AS (SELECT DISTINCT t.txn_id, t.ts_utc FROM txn t JOIN terminal_assignment ta ON ta.terminal_id=t.terminal_id JOIN dim_merchant m ON m.merchant_id=ta.merchant_id WHERE m.group_id IN (10,11,12,13,14)), w AS (SELECT txn_id, date(ts_utc, '-' || ((CAST(strftime('%w',ts_utc) AS INT)+6)%7) || ' day`
- q22 (2054.3 ms): `WITH RECURSIVE nums(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM nums WHERE x<52), t AS (SELECT t.txn_id, t.ts_utc, a.merchant_id FROM txn t JOIN terminal_assignment a ON a.terminal_id=t.terminal_id AND t.ts_utc >= a.valid_from AND (a.valid_to IS NULL OR t.ts_utc < a.valid_to)), w AS (SELECT txn_id, me`
- q19 (2656.2 ms): `WITH s AS ( SELECT s.settlement_id, s.settled_at, s.settled_eur_minor AS eur, t.amount_minor, c.exponent, t.currency_id, date(s.settled_at) AS d FROM settlement s JOIN txn t ON t.txn_id=s.txn_id JOIN dim_currency c ON c.currency_id=t.currency_id), x AS ( SELECT s.*, f.eur_per_unit AS r, ABS(CAST(ROU`
- q26 (1797.0 ms): `WITH tl AS ( SELECT t.txn_id, replace(t.ts_utc,' ','T') ts, t.terminal_id FROM txn t ), a AS ( SELECT tl.txn_id, tl.ts, l.merchant_id FROM tl JOIN terminal_merchant_link l ON l.terminal_id=tl.terminal_id AND tl.ts >= replace(l.start_ts,' ','T') AND (l.end_ts IS NULL OR tl.ts < replace(l.end_ts,' ','`
- q26 (1140.0 ms): `WITH tl AS ( SELECT t.txn_id, replace(t.ts_utc,' ','T') ts, t.terminal_id FROM txn t ), a AS ( SELECT tl.txn_id, tl.ts, m.merchant_group_id gid FROM tl JOIN terminal_merchant_link l ON l.terminal_id=tl.terminal_id AND tl.ts >= replace(l.start_ts,' ','T') AND (l.end_ts IS NULL OR tl.ts < replace(l.en`

## Per-question metrics — `haiku_stateless_r1`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 13 | 0 | 0 | 8 | 92k | 70k | 2.2k | 272 | $0.0046 | 11s | 22120 |
| q02 | ✗ | 2025-W50 | 16 | 0 | 0 | 8 | 73k | 54k | 3.5k | 925 | $0.0046 | 17s | 19632 |
| q03 | ✓ | 815909.97 | 18 | 0 | 0 | 9 | 82k | 68k | 3.6k | 1.1k | $0.0042 | 17s | 14419 |
| q04 | ✓ | 0.1014 | 10 | 0 | 0 | 7 | 41k | 33k | 1.5k | 496 | $0.0021 | 9s | 9282 |
| q05 | ✓ | OSX-3 | 11 | 0 | 0 | 7 | 51k | 40k | 1.8k | 451 | $0.0026 | 11s | 11360 |
| q06 | ✓ | 2025-05 | 17 | 0 | 0 | 10 | 84k | 71k | 4.5k | 930 | $0.0046 | 21s | 13589 |
| q07 | ✓ | v4.18.0 | 10 | 0 | 0 | 7 | 37k | 29k | 1.5k | 454 | $0.0021 | 10s | 8963 |
| q08 | ✓ | 14.96 | 11 | 0 | 0 | 7 | 43k | 35k | 1.5k | 279 | $0.0021 | 10s | 8717 |
| q09 | ✓ | 0.7869 | 13 | 0 | 0 | 7 | 51k | 41k | 1.7k | 502 | $0.0026 | 11s | 11180 |
| q10 | ✓ | r.svensson | 12 | 0 | 0 | 9 | 57k | 47k | 3.7k | 979 | $0.0036 | 18s | 10465 |
| q11 | ✓ | 743 | 12 | 0 | 0 | 7 | 40k | 32k | 1.8k | 370 | $0.0022 | 11s | 8751 |
| q12 | ✓ | 54 | 17 | 0 | 0 | 7 | 48k | 37k | 2.4k | 628 | $0.0029 | 13s | 11142 |
| q13 | ✓ | Helios Group | 19 | 0 | 0 | 8 | 44k | 34k | 3.0k | 652 | $0.0031 | 15s | 10350 |
| q14 | ✓ | 2025-08 | 12 | 0 | 0 | 7 | 47k | 38k | 1.9k | 403 | $0.0025 | 13s | 10338 |
| q21 | ✓ | 31 | 8 | 0 | 0 | 5 | 26k | 19k | 1.2k | 287 | $0.0017 | 7s | 8236 |
| q22 | ✓ | Helios Grocery | 19 | 0 | 0 | 9 | 62k | 49k | 4.1k | 1.0k | $0.0041 | 21s | 13146 |
| q23 | ✓ | 35 | 8 | 0 | 0 | 6 | 34k | 25k | 1.7k | 548 | $0.0022 | 10s | 9244 |
| q24 | ✓ | 83 | 13 | 1 | 0 | 8 | 46k | 38k | 2.1k | 338 | $0.0024 | 15s | 8243 |
| q15 | ✓ | 2463087.54 | 20 | 0 | 0 | 10 | 60k | 51k | 3.4k | 691 | $0.0033 | 18s | 9972 |
| q16 | ✓ | 2025-W11 | 7 | 0 | 0 | 7 | 41k | 33k | 1.7k | 476 | $0.0021 | 13s | 8304 |
| q17 | ✓ | 0.0720 | 10 | 0 | 0 | 6 | 37k | 27k | 1.8k | 764 | $0.0023 | 10s | 10532 |
| q18 | ✓ | 100 | 13 | 0 | 0 | 8 | 52k | 43k | 1.9k | 343 | $0.0026 | 11s | 10256 |
| q19 | ✓ | 2025-W20 | 12 | 1 | 0 | 6 | 33k | 25k | 2.4k | 739 | $0.0025 | 15s | 9364 |
| q20 | ✓ | 98 | 8 | 0 | 0 | 6 | 38k | 29k | 1.2k | 289 | $0.0020 | 8s | 9434 |
| q25 | ✓ | 2025-W38 | 8 | 0 | 0 | 7 | 43k | 35k | 2.4k | 705 | $0.0025 | 13s | 8733 |
| q26 | ✓ | Aurora Coffee Chain | 18 | 1 | 0 | 10 | 56k | 44k | 3.6k | 1.3k | $0.0038 | 21s | 13081 |

Slow SQL (> 1 s) in `haiku_stateless_r1`:

- q24 (2492.2 ms): `SELECT c.change_id, c.component_id, COUNT(e.event_id) AS n FROM config_change c LEFT JOIN service_event e ON e.component_id = c.component_id AND e.level = 'ERROR' AND strftime('%s', e.ts_utc) >= strftime('%s', c.changed_at) AND strftime('%s', e.ts_utc) < strftime('%s', c.changed_at) + 3600 WHERE c.c`
- q19 (1776.2 ms): `WITH x AS ( SELECT s.settlement_id, s.settled_at, s.settled_eur_minor, ABS(ROUND(t.amount_minor * 1.0 / POWER(10, c.exponent) * f.eur_per_unit * 100) - s.settled_eur_minor) AS d, date(s.settled_at) AS dd FROM settlement s JOIN txn t ON t.txn_id=s.txn_id JOIN dim_currency c ON c.currency_id=t.currenc`
- q26 (1868.3 ms): `WITH leaf AS (SELECT group_id, name FROM dim_merchant_group g WHERE NOT EXISTS (SELECT 1 FROM dim_merchant_group c WHERE c.parent_group_id=g.group_id)), t AS ( SELECT t.txn_id, t.ts_utc, m.merchant_group_id gid FROM txn t JOIN terminal_merchant_link l ON l.terminal_id=t.terminal_id AND l.start_ts<=t`

## Per-question metrics — `haiku_stateless_r2`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 13 | 0 | 0 | 7 | 43k | 34k | 1.6k | 194 | $0.0023 | 9s | 9186 |
| q02 | ✓ | 2025-W51 | 18 | 3 | 0 | 10 | 84k | 71k | 4.3k | 843 | $0.0045 | 23s | 14281 |
| q03 | ✓ | 815909.97 | 18 | 0 | 0 | 9 | 69k | 57k | 3.5k | 1.0k | $0.0038 | 17s | 12924 |
| q04 | ✓ | 0.1014 | 12 | 0 | 0 | 9 | 62k | 52k | 2.1k | 615 | $0.0029 | 12s | 10808 |
| q05 | ✓ | OSX-3 | 10 | 0 | 0 | 7 | 49k | 39k | 1.6k | 455 | $0.0024 | 11s | 10518 |
| q06 | ✓ | 2025-05 | 22 | 0 | 0 | 9 | 76k | 63k | 3.6k | 808 | $0.0040 | 18s | 13784 |
| q07 | ✓ | v4.18.0 | 12 | 0 | 0 | 7 | 39k | 30k | 1.9k | 506 | $0.0024 | 12s | 10019 |
| q08 | ✓ | 14.96 | 8 | 0 | 0 | 5 | 15k | 11k | 1.4k | 280 | $0.0013 | 8s | 5183 |
| q09 | ✓ | 0.7869 | 15 | 0 | 0 | 9 | 71k | 60k | 2.8k | 847 | $0.0034 | 15s | 11946 |
| q10 | ✓ | r.svensson | 11 | 0 | 0 | 6 | 33k | 25k | 2.0k | 501 | $0.0022 | 10s | 8402 |
| q11 | ✓ | 743 | 12 | 0 | 0 | 7 | 39k | 31k | 2.0k | 393 | $0.0023 | 11s | 8210 |
| q12 | ✓ | 54 | 16 | 0 | 0 | 7 | 46k | 36k | 2.7k | 949 | $0.0029 | 15s | 10551 |
| q13 | ✓ | Helios Group | 14 | 0 | 0 | 8 | 63k | 51k | 3.5k | 968 | $0.0038 | 17s | 12901 |
| q14 | ✓ | 2025-08 | 13 | 0 | 0 | 9 | 75k | 60k | 2.8k | 797 | $0.0038 | 16s | 15145 |
| q21 | ✓ | 31 | 8 | 0 | 0 | 5 | 25k | 18k | 1.2k | 282 | $0.0017 | 8s | 8028 |
| q22 | ✓ | Helios Grocery | 16 | 1 | 0 | 10 | 72k | 60k | 4.2k | 1.8k | $0.0042 | 26s | 12982 |
| q23 | ✓ | 35 | 9 | 0 | 0 | 6 | 34k | 25k | 1.9k | 640 | $0.0023 | 11s | 9657 |
| q24 | ✓ | 83 | 10 | 0 | 0 | 7 | 35k | 28k | 1.4k | 300 | $0.0018 | 9s | 7085 |
| q15 | ✓ | 2463087.54 | 21 | 0 | 0 | 10 | 88k | 71k | 4.2k | 1.0k | $0.0050 | 21s | 18102 |
| q16 | ✓ | 2025-W11 | 11 | 0 | 0 | 7 | 45k | 36k | 2.4k | 703 | $0.0027 | 13s | 9594 |
| q17 | ✓ | 0.0720 | 10 | 0 | 0 | 6 | 37k | 28k | 2.0k | 910 | $0.0025 | 11s | 10941 |
| q18 | ✓ | 100 | 16 | 0 | 0 | 10 | 73k | 61k | 2.0k | 395 | $0.0031 | 12s | 12449 |
| q19 | ✓ | 2025-W20 | 15 | 1 | 0 | 7 | 46k | 37k | 3.1k | 908 | $0.0031 | 19s | 10415 |
| q20 | ✓ | 98 | 10 | 0 | 0 | 7 | 40k | 32k | 1.3k | 305 | $0.0019 | 9s | 8449 |
| q25 | ✓ | 2025-W38 | 7 | 0 | 0 | 6 | 28k | 22k | 1.9k | 524 | $0.0019 | 11s | 7034 |
| q26 | ✓ | Aurora Coffee Chain | 22 | 0 | 0 | 11 | 65k | 54k | 3.8k | 968 | $0.0038 | 20s | 11460 |

Slow SQL (> 1 s) in `haiku_stateless_r2`:

- q02 (1226.4 ms): `WITH sub AS (SELECT group_id FROM dim_merchant_group WHERE group_id=10 OR parent_group_id=10 OR parent_group_id IN (SELECT group_id FROM dim_merchant_group WHERE parent_group_id=10)), t_asg AS ( SELECT t.txn_id, t.ts_utc, strftime('%W', t.ts_utc) AS wk FROM txn t JOIN terminal_assignment ta ON ta.te`
- q02 (1211.7 ms): `WITH sub AS (SELECT group_id FROM dim_merchant_group WHERE group_id=10 OR parent_group_id=10 OR parent_group_id IN (SELECT group_id FROM dim_merchant_group WHERE parent_group_id=10)), t_asg AS ( SELECT DISTINCT t.txn_id, t.ts_utc FROM txn t JOIN terminal_assignment ta ON ta.terminal_id=t.terminal_id`
- q02 (1094.5 ms): `WITH sub AS (SELECT group_id FROM dim_merchant_group WHERE group_id=10 OR parent_group_id=10 OR parent_group_id IN (SELECT group_id FROM dim_merchant_group WHERE parent_group_id=10)), t_grp AS ( SELECT DISTINCT t.txn_id, t.ts_utc FROM txn t JOIN terminal_assignment ta ON ta.terminal_id=t.terminal_id`
- q22 (1096.6 ms): `WITH RECURSIVE wk(w) AS (SELECT 1 UNION ALL SELECT w+1 FROM wk WHERE w<52), t AS ( SELECT CAST((julianday(substr(t.ts_utc,1,10)) - julianday('2024-12-30'))/7 AS INTEGER)+1 AS wk, ta.merchant_id FROM txn t JOIN terminal_assignment ta ON ta.terminal_id=t.terminal_id AND t.ts_utc >= ta.valid_from AND (`
- q19 (1836.3 ms): `WITH x AS ( SELECT s.settled_at, ABS(ROUND(t.amount_minor/CAST(POWER(10,c.exponent) AS REAL) * f.eur_per_unit * 100) - s.settled_eur_minor) AS d FROM settlement s JOIN txn t ON t.txn_id=s.txn_id JOIN dim_currency c ON c.currency_id=t.currency_id JOIN fx_rate_daily f ON f.currency_id=t.currency_id AN`

## ICL: context growth by question

`haiku_icl_r1`

| q | context tokens at end | episode input tokens | episode cached |
|---|---|---|---|
| q01 | 20721 | 66k | 45k |
| q02 | 25334 | 114k | 109k |
| q03 | 27094 | 105k | 103k |
| q04 | 30472 | 117k | 114k |
| q05 | 31329 | 62k | 61k |
| q06 | 32413 | 64k | 63k |
| q07 | 35941 | 205k | 201k |
| q08 | 38076 | 111k | 109k |
| q09 | 39477 | 155k | 154k |
| q10 | 41872 | 245k | 242k |
| q11 | 42613 | 127k | 126k |
| q12 | 43630 | 129k | 128k |
| q13 | 44750 | 88k | 87k |
| q14 | 45853 | 91k | 90k |
| q21 | 46990 | 93k | 92k |
| q22 | 50241 | 146k | 143k |
| q23 | 51028 | 101k | 101k |
| q24 | 51607 | 103k | 102k |
| q15 | 57273 | 490k | 484k |
| q16 | 58472 | 174k | 172k |
| q17 | 59156 | 118k | 117k |
| q18 | 60509 | 240k | 238k |
| q19 | 61560 | 122k | 121k |
| q20 | 62467 | 186k | 185k |
| q25 | 62992 | 125k | 125k |
| q26 | 65332 | 257k | 254k |

## Memory: memory dir size and bash calls by question

`haiku_memory_guided_r1`

| q | memory bytes | files | bash calls | post-submit turns |
|---|---|---|---|---|
| q01 | 0 | 0 | 1 | 0 |
| q02 | 172 | 1 | 2 | 0 |
| q03 | 511 | 1 | 2 | 0 |
| q04 | 860 | 1 | 2 | 1 |
| q05 | 860 | 1 | 2 | 0 |
| q06 | 1094 | 1 | 3 | 2 |
| q07 | 1094 | 1 | 1 | 0 |
| q08 | 1328 | 1 | 2 | 0 |
| q09 | 1645 | 1 | 2 | 1 |
| q10 | 1645 | 1 | 2 | 0 |
| q11 | 1835 | 1 | 3 | 1 |
| q12 | 2050 | 1 | 2 | 0 |
| q13 | 2277 | 1 | 3 | 1 |
| q14 | 2413 | 1 | 2 | 0 |
| q21 | 2582 | 1 | 2 | 1 |
| q22 | 2848 | 1 | 4 | 2 |
| q23 | 3045 | 1 | 3 | 1 |
| q24 | 3301 | 1 | 2 | 1 |
| q15 | 3696 | 1 | 2 | 1 |
| q16 | 3921 | 1 | 4 | 1 |
| q17 | 3921 | 1 | 1 | 0 |
| q18 | 4163 | 1 | 2 | 1 |
| q19 | 4238 | 1 | 3 | 2 |
| q20 | 4508 | 1 | 3 | 1 |
| q25 | 4651 | 1 | 2 | 2 |
| q26 | 4890 | 1 | 2 | 0 |

`haiku_memory_r1`

| q | memory bytes | files | bash calls | post-submit turns |
|---|---|---|---|---|
| q01 | 0 | 0 | 1 | 0 |
| q02 | 0 | 0 | 2 | 0 |
| q03 | 0 | 0 | 1 | 0 |
| q04 | 0 | 0 | 0 | 0 |
| q05 | 0 | 0 | 1 | 0 |
| q06 | 0 | 0 | 1 | 0 |
| q07 | 0 | 0 | 1 | 0 |
| q08 | 0 | 0 | 1 | 0 |
| q09 | 0 | 0 | 0 | 0 |
| q10 | 0 | 0 | 1 | 0 |
| q11 | 0 | 0 | 1 | 0 |
| q12 | 0 | 0 | 1 | 0 |
| q13 | 0 | 0 | 1 | 0 |
| q14 | 0 | 0 | 1 | 0 |
| q21 | 0 | 0 | 1 | 0 |
| q22 | 0 | 0 | 2 | 0 |
| q23 | 0 | 0 | 1 | 0 |
| q24 | 0 | 0 | 1 | 0 |
| q15 | 0 | 0 | 2 | 0 |
| q16 | 0 | 0 | 1 | 0 |
| q17 | 0 | 0 | 1 | 0 |
| q18 | 0 | 0 | 1 | 0 |
| q19 | 0 | 0 | 3 | 0 |
| q20 | 0 | 0 | 1 | 0 |
| q25 | 0 | 0 | 2 | 0 |
| q26 | 0 | 0 | 1 | 0 |
