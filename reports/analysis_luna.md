# Memory modes report — analysis_luna

Runs: `luna_icl_r1` = runs/luna_icl_r1 (luna, icl), `luna_icl_r2` = runs/luna_icl_r2 (luna, icl), `luna_memory_guided_r1` = runs/luna_memory_guided_r1 (luna, memory), `luna_memory_r1` = runs/luna_memory_r1 (luna, memory), `luna_stateless_r1` = runs/luna_stateless_r1 (luna, stateless), `luna_stateless_r2` = runs/luna_stateless_r2 (luna, stateless), `luna_stateless_r3` = runs/luna_stateless_r3 (luna, stateless)

Silent migration after question 18 (index in the full list).

## Overview

| run | model | mode | accuracy | pre-drift | post-drift | errors | no answer | cost | wall | n_sql | slow | n_bash |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| luna_icl_r1 | luna | icl | 26/26 (100%) | 18/18 (100%) | 8/8 (100%) | 0 | 0 | $0.0212 | 309s | 81 | 2 | 0 |
| luna_icl_r2 | luna | icl | 25/26 (96%) | 17/18 (94%) | 8/8 (100%) | 0 | 0 | $0.0207 | 283s | 77 | 1 | 0 |
| luna_memory_guided_r1 | luna | memory | 22/26 (85%) | 17/18 (94%) | 5/8 (62%) | 0 | 0 | $0.0256 | 438s | 187 | 3 | 0 |
| luna_memory_r1 | luna | memory | 24/26 (92%) | 16/18 (89%) | 8/8 (100%) | 0 | 0 | $0.0259 | 440s | 189 | 0 | 0 |
| luna_stateless_r1 | luna | stateless | 19/26 (73%) | 14/18 (78%) | 5/8 (62%) | 0 | 0 | $0.0216 | 405s | 168 | 1 | 0 |
| luna_stateless_r2 | luna | stateless | 22/26 (85%) | 17/18 (94%) | 5/8 (62%) | 0 | 0 | $0.0219 | 408s | 185 | 0 | 0 |
| luna_stateless_r3 | luna | stateless | 22/26 (85%) | 17/18 (94%) | 5/8 (62%) | 0 | 0 | $0.0221 | 488s | 190 | 0 | 0 |

## Per-question correctness

✓ correct · ✗ wrong · ∅ no answer · ⚠ error · — missing

| q | phase | gt | luna_icl_r1 | luna_icl_r2 | luna_memory_guided_r1 | luna_memory_r1 | luna_stateless_r1 | luna_stateless_r2 | luna_stateless_r3 | class |
|---|---|---|---|---|---|---|---|---|---|---|
| q01 | pre-drift | 36531.85 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q02 | pre-drift | 2025-W51 | ✓ | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ | mixed:luna_memory_guided_r1+luna_memory_r1+luna_stateless_r2+luna_stateless_r3-wrong |
| q03 | pre-drift | 815909.97 | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | mixed:luna_memory_r1+luna_stateless_r1-wrong |
| q04 | pre-drift | 0.1014 | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | only-luna_stateless_r1-wrong |
| q05 | pre-drift | OSX-3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q06 | pre-drift | 2025-05 | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | only-luna_stateless_r1-wrong |
| q07 | pre-drift | v4.18.0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q08 | pre-drift | 14.96 | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | only-luna_stateless_r1-wrong |
| q09 | pre-drift | 0.7869 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q10 | pre-drift | r.svensson | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q11 | pre-drift | 743 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q12 | pre-drift | 54 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q13 | pre-drift | Helios Group | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q14 | pre-drift | 2025-08 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q21 | pre-drift | 31 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q22 | pre-drift | Helios Grocery | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | only-luna_icl_r2-wrong |
| q23 | pre-drift | 35 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q24 | pre-drift | 83 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q15 | post-drift | 2463087.54 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | only-luna_stateless_r2-wrong |
| q16 | post-drift | 2025-W11 | ✓ | ✓ | ✗ | ✓ | ✗ | ✓ | ✗ | mixed:luna_memory_guided_r1+luna_stateless_r1+luna_stateless_r3-wrong |
| q17 | post-drift | 0.072 | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | only-luna_stateless_r1-wrong |
| q18 | post-drift | 100 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q19 | post-drift | 2025-W20 | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ | ✓ | mixed:luna_memory_guided_r1+luna_stateless_r2-wrong |
| q20 | post-drift | 98 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all-correct |
| q25 | post-drift | 2025-W38 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | only-luna_stateless_r3-wrong |
| q26 | post-drift | Aurora Coffee Chain | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | mixed:luna_memory_guided_r1+luna_stateless_r1+luna_stateless_r2+luna_stateless_r3-wrong |

## Divergence classes

| class | n | questions |
|---|---|---|
| all-correct | 14 | q01, q05, q07, q09, q10, q11, q12, q13, q14, q21, q23, q24, q18, q20 |
| only-luna_stateless_r1-wrong | 4 | q04, q06, q08, q17 |
| mixed:luna_memory_guided_r1+luna_memory_r1+luna_stateless_r2+luna_stateless_r3-wrong | 1 | q02 |
| mixed:luna_memory_guided_r1+luna_stateless_r1+luna_stateless_r2+luna_stateless_r3-wrong | 1 | q26 |
| mixed:luna_memory_guided_r1+luna_stateless_r1+luna_stateless_r3-wrong | 1 | q16 |
| mixed:luna_memory_guided_r1+luna_stateless_r2-wrong | 1 | q19 |
| mixed:luna_memory_r1+luna_stateless_r1-wrong | 1 | q03 |
| only-luna_icl_r2-wrong | 1 | q22 |
| only-luna_stateless_r2-wrong | 1 | q15 |
| only-luna_stateless_r3-wrong | 1 | q25 |

## Answers on divergent questions

| q | gt | luna_icl_r1 | luna_icl_r2 | luna_memory_guided_r1 | luna_memory_r1 | luna_stateless_r1 | luna_stateless_r2 | luna_stateless_r3 |
|---|---|---|---|---|---|---|---|---|
| q02 | 2025-W51 | 2025-W51 | 2025-W51 | 2025-W50 | 2025-W50 | 2025-W51 | 2025-W50 | 2025-W50 |
| q03 | 815909.97 | 815909.97 | 815909.97 | 815909.97 | 843894.75 | 843894.75 | 815909.97 | 815909.97 |
| q04 | 0.1014 | 0.1014 | 0.1014 | 0.1014 | 0.1014 | 0.1030 | 0.1014 | 0.1014 |
| q06 | 2025-05 | 2025-05 | 2025-05 | 2025-05 | 2025-05 | 2025-01 | 2025-05 | 2025-05 |
| q08 | 14.96 | 14.96 | 14.96 | 14.96 | 14.96 | 6.34 | 14.96 | 14.96 |
| q22 | Helios Grocery | Helios Grocery | Aurora Hospitality | Helios Grocery | Helios Grocery | Helios Grocery | Helios Grocery | Helios Grocery |
| q15 | 2463087.54 | 2463087.54 | 2463087.54 | 2463087.54 | 2463087.54 | 2463087.54 | 2738612.10 | 2463087.54 |
| q16 | 2025-W11 | 2025-W11 | 2025-W11 | 2025-W10 | 2025-W11 | 2025-W10 | 2025-W11 | 2025-W10 |
| q17 | 0.072 | 0.0720 | 0.0720 | 0.0720 | 0.0720 | 0.0679 | 0.0720 | 0.0720 |
| q19 | 2025-W20 | 2025-W20 | 2025-W20 | 2025-W19 | 2025-W20 | 2025-W20 | 2025-W19 | 2025-W20 |
| q25 | 2025-W38 | 2025-W38 | 2025-W38 | 2025-W38 | 2025-W38 | 2025-W38 | 2025-W38 | 2025-W37 |
| q26 | Aurora Coffee Chain | Aurora Coffee Chain | Aurora Coffee Chain | Borealis Online | Aurora Coffee Chain | Borealis Online | Borealis Online | Borealis Online |

## Cost structure by run

Tokens: uncached input / cached input / cache writes / output (reasoning ⊂ output).

| run | uncached in | cached in | cache write | cached share | output | reasoning | cost | cost src | wall | turns | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|
| luna_icl_r1 | 55k | 1.12M | 0 | 95% | 9.0k | 452 | $0.0212 | known | 309s | 88 | 23673 |
| luna_icl_r2 | 60k | 1.06M | 0 | 95% | 8.2k | 419 | $0.0207 | known | 283s | 80 | 24480 |
| luna_memory_guided_r1 | 172k | 259k | 0 | 60% | 12k | 740 | $0.0256 | known | 438s | 181 | 3191 |
| luna_memory_r1 | 176k | 259k | 0 | 60% | 11k | 468 | $0.0259 | known | 440s | 186 | 2845 |
| luna_stateless_r1 | 142k | 159k | 0 | 53% | 12k | 1.0k | $0.0216 | known | 405s | 150 | 2744 |
| luna_stateless_r2 | 144k | 177k | 0 | 55% | 11k | 599 | $0.0219 | known | 408s | 154 | 2165 |
| luna_stateless_r3 | 146k | 156k | 0 | 52% | 12k | 617 | $0.0221 | known | 488s | 157 | 1941 |

## Per-question metrics — `luna_icl_r1`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 7 | 0 | 0 | 5 | 5.8k | 2.7k | 333 | 0 | $0.0005 | 11s | 1853 |
| q02 | ✓ | 2025-W51 | 7 | 0 | 0 | 6 | 17k | 14k | 871 | 266 | $0.0009 | 25s | 3797 |
| q03 | ✓ | 815909.97 | 3 | 0 | 0 | 4 | 17k | 12k | 552 | 13 | $0.0009 | 14s | 4687 |
| q04 | ✓ | 0.1014 | 5 | 0 | 0 | 4 | 26k | 20k | 274 | 0 | $0.0009 | 9s | 7344 |
| q05 | ✓ | OSX-3 | 1 | 0 | 0 | 2 | 15k | 14k | 196 | 0 | $0.0004 | 5s | 7776 |
| q06 | ✓ | 2025-05 | 1 | 0 | 0 | 2 | 16k | 15k | 267 | 0 | $0.0004 | 8s | 8302 |
| q07 | ✓ | v4.18.0 | 6 | 0 | 0 | 4 | 37k | 34k | 287 | 0 | $0.0008 | 9s | 9753 |
| q08 | ✓ | 14.96 | 5 | 0 | 0 | 5 | 51k | 47k | 495 | 0 | $0.0011 | 15s | 10704 |
| q09 | ✓ | 0.7869 | 4 | 0 | 0 | 3 | 34k | 32k | 260 | 0 | $0.0006 | 8s | 11453 |
| q10 | ✓ | r.svensson | 6 | 0 | 0 | 4 | 49k | 47k | 375 | 8 | $0.0008 | 15s | 12666 |
| q11 | ✓ | 743 | 2 | 0 | 0 | 3 | 39k | 36k | 128 | 0 | $0.0007 | 6s | 13114 |
| q12 | ✓ | 54 | 4 | 0 | 0 | 3 | 41k | 39k | 232 | 0 | $0.0007 | 8s | 13933 |
| q13 | ✓ | Helios Group | 1 | 0 | 0 | 2 | 28k | 28k | 285 | 0 | $0.0005 | 13s | 14456 |
| q14 | ✓ | 2025-08 | 1 | 0 | 0 | 2 | 29k | 27k | 197 | 0 | $0.0006 | 6s | 14906 |
| q21 | ✓ | 31 | 1 | 0 | 0 | 2 | 31k | 29k | 166 | 0 | $0.0005 | 6s | 15729 |
| q22 | ✓ | Helios Grocery | 2 | 1 | 0 | 3 | 49k | 46k | 688 | 0 | $0.0011 | 17s | 16880 |
| q23 | ✓ | 35 | 1 | 0 | 0 | 2 | 34k | 33k | 176 | 0 | $0.0006 | 7s | 17218 |
| q24 | ✓ | 83 | 1 | 0 | 0 | 2 | 35k | 34k | 150 | 0 | $0.0005 | 5s | 17794 |
| q15 | ✓ | 2463087.54 | 10 | 0 | 0 | 11 | 208k | 203k | 1.4k | 100 | $0.0033 | 49s | 20079 |
| q16 | ✓ | 2025-W11 | 3 | 0 | 0 | 4 | 82k | 81k | 258 | 0 | $0.0011 | 12s | 20733 |
| q17 | ✓ | 0.0720 | 1 | 0 | 0 | 2 | 42k | 41k | 172 | 0 | $0.0006 | 6s | 21082 |
| q18 | ✓ | 100 | 4 | 0 | 0 | 4 | 86k | 84k | 244 | 0 | $0.0011 | 14s | 21768 |
| q19 | ✓ | 2025-W20 | 1 | 1 | 0 | 2 | 44k | 43k | 213 | 0 | $0.0006 | 8s | 22251 |
| q20 | ✓ | 98 | 2 | 0 | 0 | 3 | 67k | 67k | 208 | 0 | $0.0008 | 10s | 22643 |
| q25 | ✓ | 2025-W38 | 1 | 0 | 0 | 2 | 46k | 45k | 192 | 0 | $0.0006 | 7s | 23005 |
| q26 | ✓ | Aurora Coffee Chain | 1 | 0 | 0 | 2 | 47k | 46k | 335 | 65 | $0.0007 | 16s | 23673 |

Slow SQL (> 1 s) in `luna_icl_r1`:

- q22 (1437.6 ms): `WITH RECURSIVE subtree(root,gid) AS (SELECT group_id,group_id FROM dim_merchant_group WHERE parent_group_id IN (SELECT group_id FROM dim_merchant_group WHERE parent_group_id IS NULL) UNION ALL SELECT subtree.root,g.group_id FROM dim_merchant_group g JOIN subtree ON g.parent_group_id=subtree.gid), pe`
- q19 (1274.2 ms): `WITH x AS (SELECT s.settled_at,ABS(ROUND(t.amount_minor*1.0/pow(10,c.exponent)*f.eur_per_unit*100)-s.settled_eur_minor) diff FROM settlement s JOIN txn t ON t.txn_id=s.txn_id JOIN dim_currency c ON c.currency_id=t.currency_id JOIN fx_rate_daily f ON f.currency_id=t.currency_id AND f.rate_date=substr`

## Per-question metrics — `luna_icl_r2`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 8 | 0 | 0 | 5 | 6.6k | 3.2k | 389 | 17 | $0.0006 | 13s | 2171 |
| q02 | ✓ | 2025-W51 | 6 | 0 | 0 | 5 | 17k | 12k | 785 | 235 | $0.0011 | 24s | 4708 |
| q03 | ✓ | 815909.97 | 1 | 0 | 0 | 2 | 10.0k | 9.2k | 269 | 0 | $0.0003 | 7s | 5142 |
| q04 | ✓ | 0.1014 | 6 | 0 | 0 | 4 | 28k | 25k | 315 | 0 | $0.0007 | 11s | 7866 |
| q05 | ✓ | OSX-3 | 1 | 0 | 0 | 2 | 16k | 15k | 179 | 0 | $0.0003 | 6s | 8297 |
| q06 | ✓ | 2025-05 | 1 | 0 | 0 | 2 | 17k | 10k | 300 | 0 | $0.0009 | 10s | 8836 |
| q07 | ✓ | v4.18.0 | 7 | 0 | 0 | 5 | 49k | 46k | 303 | 0 | $0.0009 | 11s | 10613 |
| q08 | ✓ | 14.96 | 4 | 0 | 0 | 4 | 44k | 41k | 310 | 0 | $0.0009 | 10s | 11357 |
| q09 | ✓ | 0.7869 | 4 | 0 | 0 | 3 | 36k | 34k | 255 | 0 | $0.0006 | 9s | 12192 |
| q10 | ✓ | r.svensson | 4 | 0 | 0 | 3 | 38k | 36k | 239 | 0 | $0.0007 | 8s | 13129 |
| q11 | ✓ | 743 | 2 | 0 | 0 | 3 | 40k | 39k | 127 | 0 | $0.0005 | 6s | 13576 |
| q12 | ✓ | 54 | 3 | 0 | 0 | 3 | 42k | 41k | 224 | 0 | $0.0006 | 8s | 14204 |
| q13 | ✓ | Helios Group | 1 | 0 | 0 | 2 | 29k | 28k | 306 | 0 | $0.0005 | 8s | 14770 |
| q14 | ✓ | 2025-08 | 1 | 0 | 0 | 2 | 30k | 29k | 196 | 0 | $0.0005 | 7s | 15223 |
| q21 | ✓ | 31 | 1 | 0 | 0 | 2 | 31k | 30k | 153 | 0 | $0.0005 | 7s | 16124 |
| q22 | ✗ | Aurora Hospitality | 2 | 1 | 0 | 3 | 51k | 49k | 1.1k | 54 | $0.0012 | 24s | 17546 |
| q23 | ✓ | 35 | 1 | 0 | 0 | 2 | 36k | 35k | 167 | 0 | $0.0005 | 6s | 17880 |
| q24 | ✓ | 83 | 1 | 0 | 0 | 2 | 36k | 35k | 136 | 0 | $0.0005 | 5s | 18394 |
| q15 | ✓ | 2463087.54 | 10 | 0 | 0 | 8 | 156k | 145k | 975 | 46 | $0.0031 | 35s | 20651 |
| q16 | ✓ | 2025-W11 | 4 | 0 | 0 | 4 | 84k | 81k | 297 | 14 | $0.0012 | 15s | 21535 |
| q17 | ✓ | 0.0720 | 1 | 0 | 0 | 2 | 44k | 43k | 167 | 0 | $0.0006 | 5s | 21886 |
| q18 | ✓ | 100 | 3 | 0 | 0 | 3 | 67k | 66k | 232 | 0 | $0.0009 | 8s | 22452 |
| q19 | ✓ | 2025-W20 | 2 | 0 | 0 | 3 | 68k | 66k | 216 | 22 | $0.0010 | 16s | 23091 |
| q20 | ✓ | 98 | 1 | 0 | 0 | 2 | 47k | 46k | 169 | 0 | $0.0006 | 6s | 23399 |
| q25 | ✓ | 2025-W38 | 1 | 0 | 0 | 2 | 47k | 46k | 176 | 13 | $0.0006 | 9s | 23847 |
| q26 | ✓ | Aurora Coffee Chain | 1 | 0 | 0 | 2 | 48k | 47k | 292 | 18 | $0.0008 | 9s | 24480 |

Slow SQL (> 1 s) in `luna_icl_r2`:

- q22 (1083.6 ms): `WITH RECURSIVE groups(gid,id) AS (SELECT g.group_id,g.group_id FROM dim_merchant_group g JOIN dim_merchant_group p ON p.group_id=g.parent_group_id WHERE p.parent_group_id IS NULL UNION ALL SELECT groups.gid,c.group_id FROM groups JOIN dim_merchant_group c ON c.parent_group_id=groups.id), weeks(x) AS`

## Per-question metrics — `luna_memory_guided_r1`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 9 | 0 | 0 | 11 | 29k | 24k | 562 | 0 | $0.0010 | 24s | 3514 |
| q02 | ✗ | 2025-W50 | 9 | 0 | 0 | 7 | 12k | 7.6k | 510 | 69 | $0.0008 | 20s | 2632 |
| q03 | ✓ | 815909.97 | 9 | 0 | 0 | 6 | 17k | 8.2k | 523 | 28 | $0.0012 | 18s | 3755 |
| q04 | ✓ | 0.1014 | 7 | 0 | 0 | 6 | 19k | 13k | 356 | 0 | $0.0009 | 13s | 4665 |
| q05 | ✓ | OSX-3 | 7 | 0 | 0 | 6 | 12k | 7.0k | 353 | 0 | $0.0007 | 13s | 3189 |
| q06 | ✓ | 2025-05 | 11 | 0 | 0 | 7 | 13k | 8.2k | 548 | 0 | $0.0008 | 19s | 2772 |
| q07 | ✓ | v4.18.0 | 7 | 0 | 0 | 7 | 18k | 13k | 346 | 0 | $0.0008 | 15s | 3605 |
| q08 | ✓ | 14.96 | 8 | 0 | 0 | 6 | 8.6k | 2.9k | 446 | 0 | $0.0008 | 14s | 2084 |
| q09 | ✓ | 0.7869 | 10 | 0 | 0 | 6 | 17k | 9.0k | 489 | 0 | $0.0011 | 15s | 3884 |
| q10 | ✓ | r.svensson | 5 | 0 | 0 | 7 | 15k | 6.3k | 255 | 0 | $0.0011 | 11s | 2853 |
| q11 | ✓ | 743 | 5 | 0 | 0 | 5 | 10k | 6.8k | 213 | 0 | $0.0005 | 10s | 2753 |
| q12 | ✓ | 54 | 8 | 0 | 0 | 7 | 17k | 13k | 412 | 0 | $0.0008 | 15s | 3333 |
| q13 | ✓ | Helios Group | 12 | 0 | 0 | 10 | 17k | 10k | 1.0k | 76 | $0.0013 | 30s | 3121 |
| q14 | ✓ | 2025-08 | 5 | 0 | 0 | 7 | 21k | 14k | 328 | 0 | $0.0010 | 13s | 4358 |
| q21 | ✓ | 31 | 5 | 0 | 0 | 6 | 13k | 4.1k | 276 | 0 | $0.0011 | 11s | 3177 |
| q22 | ✓ | Helios Grocery | 9 | 1 | 0 | 11 | 21k | 8.3k | 839 | 183 | $0.0018 | 34s | 3960 |
| q23 | ✓ | 35 | 6 | 0 | 0 | 6 | 18k | 12k | 348 | 0 | $0.0009 | 14s | 4429 |
| q24 | ✓ | 83 | 7 | 0 | 0 | 7 | 17k | 10k | 322 | 0 | $0.0009 | 12s | 3564 |
| q15 | ✓ | 2463087.54 | 10 | 0 | 0 | 7 | 19k | 14k | 572 | 0 | $0.0009 | 20s | 3748 |
| q16 | ✗ | 2025-W10 | 7 | 0 | 0 | 9 | 20k | 16k | 486 | 134 | $0.0008 | 20s | 2978 |
| q17 | ✓ | 0.0720 | 6 | 0 | 0 | 8 | 29k | 15k | 362 | 0 | $0.0017 | 15s | 5219 |
| q18 | ✓ | 100 | 7 | 0 | 0 | 5 | 12k | 8.1k | 351 | 0 | $0.0007 | 16s | 3414 |
| q19 | ✗ | 2025-W19 | 7 | 2 | 0 | 7 | 20k | 11k | 844 | 250 | $0.0014 | 30s | 3849 |
| q20 | ✓ | 98 | 3 | 0 | 0 | 5 | 9.7k | 6.4k | 236 | 0 | $0.0005 | 9s | 2491 |
| q25 | ✓ | 2025-W38 | 4 | 0 | 0 | 6 | 13k | 3.8k | 332 | 0 | $0.0011 | 13s | 2833 |
| q26 | ✗ | Borealis Online | 4 | 0 | 0 | 6 | 13k | 6.9k | 319 | 0 | $0.0009 | 13s | 3191 |

Slow SQL (> 1 s) in `luna_memory_guided_r1`:

- q22 (1102.9 ms): `WITH RECURSIVE descendants(root_id,gid) AS (SELECT group_id,group_id FROM dim_merchant_group WHERE level=2 AND parent_group_id IN (SELECT group_id FROM dim_merchant_group WHERE level=1) UNION ALL SELECT d.root_id,g.group_id FROM descendants d JOIN dim_merchant_group g ON g.parent_group_id=d.gid), we`
- q19 (1177.3 ms): `WITH diffs AS (SELECT s.settled_at, ABS(ROUND((t.amount_minor * 1.0 / (10.0 * c.exponent)) * f.eur_per_unit * 100) - s.settled_eur_minor) AS diff FROM settlement s JOIN txn t ON t.txn_id=s.txn_id JOIN dim_currency c ON c.currency_id=t.currency_id JOIN fx_rate_daily f ON f.currency_id=t.currency_id A`
- q19 (1316.5 ms): `WITH diffs AS (SELECT s.settled_at, ABS(ROUND((t.amount_minor * 1.0 / CASE c.exponent WHEN 0 THEN 1.0 WHEN 2 THEN 100.0 WHEN 3 THEN 1000.0 WHEN 4 THEN 10000.0 ELSE 100.0 END) * f.eur_per_unit * 100) - s.settled_eur_minor) AS diff FROM settlement s JOIN txn t ON t.txn_id=s.txn_id JOIN dim_currency c `

## Per-question metrics — `luna_memory_r1`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 10 | 0 | 0 | 7 | 13k | 8.6k | 608 | 33 | $0.0008 | 19s | 2755 |
| q02 | ✗ | 2025-W50 | 6 | 0 | 0 | 8 | 19k | 12k | 538 | 0 | $0.0011 | 18s | 3179 |
| q03 | ✗ | 843894.75 | 12 | 0 | 0 | 9 | 24k | 11k | 597 | 0 | $0.0017 | 21s | 3851 |
| q04 | ✓ | 0.1014 | 5 | 0 | 0 | 7 | 16k | 9.1k | 299 | 0 | $0.0009 | 13s | 2928 |
| q05 | ✓ | OSX-3 | 6 | 0 | 0 | 8 | 23k | 17k | 351 | 0 | $0.0009 | 16s | 4534 |
| q06 | ✓ | 2025-05 | 10 | 0 | 0 | 7 | 18k | 13k | 528 | 0 | $0.0009 | 16s | 3653 |
| q07 | ✓ | v4.18.0 | 6 | 0 | 0 | 8 | 19k | 11k | 313 | 0 | $0.0010 | 16s | 3364 |
| q08 | ✓ | 14.96 | 6 | 0 | 0 | 8 | 19k | 14k | 349 | 0 | $0.0008 | 18s | 3282 |
| q09 | ✓ | 0.7869 | 13 | 0 | 0 | 8 | 17k | 7.0k | 499 | 0 | $0.0013 | 18s | 3243 |
| q10 | ✓ | r.svensson | 7 | 0 | 0 | 5 | 6.7k | 1.5k | 319 | 20 | $0.0007 | 12s | 1953 |
| q11 | ✓ | 743 | 4 | 0 | 0 | 6 | 12k | 8.6k | 181 | 0 | $0.0005 | 10s | 2559 |
| q12 | ✓ | 54 | 9 | 0 | 0 | 8 | 22k | 17k | 495 | 0 | $0.0009 | 19s | 3977 |
| q13 | ✓ | Helios Group | 10 | 0 | 0 | 7 | 11k | 3.7k | 564 | 0 | $0.0011 | 18s | 2529 |
| q14 | ✓ | 2025-08 | 6 | 0 | 0 | 6 | 17k | 12k | 336 | 0 | $0.0008 | 14s | 4049 |
| q21 | ✓ | 31 | 4 | 0 | 0 | 6 | 13k | 7.0k | 233 | 0 | $0.0008 | 11s | 3077 |
| q22 | ✓ | Helios Grocery | 6 | 0 | 0 | 8 | 22k | 13k | 708 | 0 | $0.0014 | 25s | 4451 |
| q23 | ✓ | 35 | 6 | 0 | 0 | 5 | 16k | 10k | 347 | 0 | $0.0008 | 13s | 4607 |
| q24 | ✓ | 83 | 4 | 0 | 0 | 6 | 13k | 8.7k | 219 | 0 | $0.0006 | 10s | 2961 |
| q15 | ✓ | 2463087.54 | 12 | 0 | 0 | 10 | 22k | 10k | 575 | 0 | $0.0016 | 23s | 3726 |
| q16 | ✓ | 2025-W11 | 6 | 0 | 0 | 8 | 18k | 8.4k | 428 | 0 | $0.0012 | 19s | 2926 |
| q17 | ✓ | 0.0720 | 8 | 0 | 0 | 7 | 16k | 9.9k | 405 | 0 | $0.0009 | 15s | 3962 |
| q18 | ✓ | 100 | 10 | 0 | 0 | 9 | 25k | 20k | 434 | 0 | $0.0010 | 17s | 4169 |
| q19 | ✓ | 2025-W20 | 8 | 0 | 0 | 8 | 21k | 9.1k | 841 | 198 | $0.0017 | 32s | 6302 |
| q20 | ✓ | 98 | 3 | 0 | 0 | 5 | 9.3k | 4.0k | 234 | 0 | $0.0007 | 10s | 2388 |
| q25 | ✓ | 2025-W38 | 4 | 0 | 0 | 6 | 13k | 6.1k | 516 | 217 | $0.0010 | 19s | 2847 |
| q26 | ✓ | Aurora Coffee Chain | 8 | 0 | 0 | 6 | 10k | 5.9k | 523 | 0 | $0.0008 | 16s | 2845 |

## Per-question metrics — `luna_stateless_r1`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 8 | 0 | 0 | 7 | 15k | 8.1k | 454 | 0 | $0.0010 | 16s | 3049 |
| q02 | ✓ | 2025-W51 | 5 | 0 | 0 | 6 | 12k | 5.6k | 762 | 259 | $0.0011 | 22s | 3065 |
| q03 | ✗ | 843894.75 | 6 | 0 | 0 | 7 | 15k | 9.1k | 566 | 0 | $0.0010 | 18s | 3073 |
| q04 | ✗ | 0.1030 | 7 | 0 | 0 | 5 | 9.8k | 6.1k | 339 | 0 | $0.0006 | 12s | 2988 |
| q05 | ✓ | OSX-3 | 5 | 0 | 0 | 6 | 12k | 6.0k | 311 | 0 | $0.0008 | 14s | 2838 |
| q06 | ✗ | 2025-01 | 6 | 0 | 0 | 8 | 16k | 10.0k | 421 | 0 | $0.0010 | 16s | 2803 |
| q07 | ✓ | v4.18.0 | 8 | 0 | 0 | 6 | 13k | 9.0k | 367 | 0 | $0.0007 | 12s | 3610 |
| q08 | ✗ | 6.34 | 7 | 0 | 0 | 7 | 15k | 5.8k | 376 | 0 | $0.0012 | 19s | 2890 |
| q09 | ✓ | 0.7869 | 10 | 0 | 0 | 7 | 17k | 6.7k | 488 | 38 | $0.0014 | 22s | 3475 |
| q10 | ✓ | r.svensson | 5 | 0 | 0 | 4 | 7.2k | 2.3k | 262 | 0 | $0.0006 | 9s | 2672 |
| q11 | ✓ | 743 | 5 | 0 | 0 | 5 | 8.7k | 5.5k | 223 | 0 | $0.0005 | 13s | 2471 |
| q12 | ✓ | 54 | 7 | 0 | 0 | 5 | 9.7k | 4.4k | 359 | 0 | $0.0008 | 12s | 2998 |
| q13 | ✓ | Helios Group | 15 | 0 | 0 | 7 | 16k | 6.7k | 1.0k | 46 | $0.0015 | 27s | 4396 |
| q14 | ✓ | 2025-08 | 6 | 0 | 0 | 5 | 9.6k | 3.3k | 368 | 0 | $0.0008 | 13s | 3079 |
| q21 | ✓ | 31 | 4 | 0 | 0 | 5 | 9.1k | 5.5k | 229 | 0 | $0.0005 | 11s | 2918 |
| q22 | ✓ | Helios Grocery | 8 | 0 | 0 | 7 | 11k | 6.1k | 1.1k | 289 | $0.0011 | 36s | 2880 |
| q23 | ✓ | 35 | 6 | 0 | 0 | 4 | 11k | 5.8k | 369 | 33 | $0.0007 | 12s | 4481 |
| q24 | ✓ | 83 | 5 | 0 | 0 | 4 | 3.9k | 0 | 254 | 0 | $0.0005 | 8s | 1890 |
| q15 | ✓ | 2463087.54 | 10 | 0 | 0 | 6 | 14k | 9.7k | 563 | 0 | $0.0008 | 18s | 3458 |
| q16 | ✗ | 2025-W10 | 7 | 0 | 0 | 8 | 16k | 10k | 435 | 0 | $0.0009 | 19s | 2783 |
| q17 | ✗ | 0.0679 | 5 | 0 | 0 | 6 | 12k | 8.6k | 271 | 0 | $0.0006 | 11s | 2802 |
| q18 | ✓ | 100 | 8 | 0 | 0 | 6 | 14k | 6.1k | 357 | 0 | $0.0010 | 12s | 3652 |
| q19 | ✓ | 2025-W20 | 4 | 1 | 0 | 5 | 9.7k | 5.9k | 503 | 172 | $0.0007 | 21s | 2941 |
| q20 | ✓ | 98 | 3 | 0 | 0 | 4 | 6.4k | 3.6k | 230 | 0 | $0.0004 | 7s | 2229 |
| q25 | ✓ | 2025-W38 | 4 | 0 | 0 | 5 | 9.1k | 5.8k | 540 | 195 | $0.0007 | 16s | 2704 |
| q26 | ✗ | Borealis Online | 4 | 0 | 0 | 5 | 9.3k | 3.7k | 293 | 0 | $0.0007 | 11s | 2744 |

Slow SQL (> 1 s) in `luna_stateless_r1`:

- q19 (1256.5 ms): `WITH x AS (SELECT s.settled_at, t.amount_minor, c.exponent, f.eur_per_unit, s.settled_eur_minor, date(s.settled_at) d FROM settlement s JOIN txn t USING(txn_id) JOIN dim_currency c USING(currency_id) JOIN fx_rate_daily f ON f.currency_id=t.currency_id AND f.rate_date=date(s.settled_at)), y AS (SELEC`

## Per-question metrics — `luna_stateless_r2`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 7 | 0 | 0 | 6 | 12k | 8.2k | 334 | 0 | $0.0006 | 14s | 2857 |
| q02 | ✗ | 2025-W50 | 4 | 0 | 0 | 5 | 8.4k | 3.6k | 491 | 208 | $0.0008 | 18s | 2637 |
| q03 | ✓ | 815909.97 | 9 | 0 | 0 | 7 | 16k | 7.8k | 528 | 0 | $0.0012 | 16s | 3369 |
| q04 | ✓ | 0.1014 | 7 | 0 | 0 | 6 | 12k | 8.2k | 384 | 0 | $0.0007 | 12s | 3030 |
| q05 | ✓ | OSX-3 | 6 | 0 | 0 | 5 | 11k | 5.0k | 374 | 0 | $0.0009 | 15s | 3831 |
| q06 | ✓ | 2025-05 | 11 | 0 | 0 | 5 | 12k | 4.4k | 581 | 0 | $0.0011 | 16s | 3624 |
| q07 | ✓ | v4.18.0 | 10 | 0 | 0 | 11 | 27k | 20k | 498 | 0 | $0.0012 | 23s | 3439 |
| q08 | ✓ | 14.96 | 7 | 0 | 0 | 5 | 10k | 6.5k | 487 | 0 | $0.0007 | 14s | 3009 |
| q09 | ✓ | 0.7869 | 13 | 0 | 0 | 6 | 17k | 11k | 564 | 55 | $0.0009 | 20s | 4182 |
| q10 | ✓ | r.svensson | 6 | 0 | 0 | 4 | 7.5k | 1.7k | 282 | 0 | $0.0007 | 9s | 2839 |
| q11 | ✓ | 743 | 4 | 0 | 0 | 5 | 8.8k | 3.8k | 181 | 0 | $0.0006 | 9s | 2404 |
| q12 | ✓ | 54 | 5 | 0 | 0 | 6 | 12k | 8.2k | 286 | 0 | $0.0006 | 12s | 2789 |
| q13 | ✓ | Helios Group | 12 | 0 | 0 | 7 | 11k | 5.2k | 887 | 0 | $0.0011 | 22s | 2872 |
| q14 | ✓ | 2025-08 | 5 | 0 | 0 | 6 | 12k | 5.8k | 270 | 0 | $0.0008 | 13s | 2971 |
| q21 | ✓ | 31 | 4 | 0 | 0 | 5 | 9.1k | 3.7k | 229 | 0 | $0.0007 | 12s | 2918 |
| q22 | ✓ | Helios Grocery | 9 | 0 | 0 | 8 | 13k | 6.5k | 962 | 198 | $0.0012 | 36s | 3046 |
| q23 | ✓ | 35 | 6 | 0 | 0 | 5 | 12k | 5.5k | 347 | 0 | $0.0009 | 12s | 4241 |
| q24 | ✓ | 83 | 4 | 0 | 0 | 5 | 9.1k | 3.8k | 214 | 0 | $0.0007 | 9s | 2800 |
| q15 | ✗ | 2738612.10 | 12 | 0 | 0 | 7 | 19k | 14k | 585 | 0 | $0.0009 | 20s | 3808 |
| q16 | ✓ | 2025-W11 | 9 | 0 | 0 | 10 | 22k | 15k | 706 | 0 | $0.0012 | 26s | 3304 |
| q17 | ✓ | 0.0720 | 6 | 0 | 0 | 7 | 20k | 14k | 343 | 0 | $0.0009 | 15s | 5232 |
| q18 | ✓ | 100 | 7 | 0 | 0 | 5 | 11k | 4.2k | 349 | 0 | $0.0009 | 11s | 3082 |
| q19 | ✗ | 2025-W19 | 6 | 0 | 0 | 4 | 7.8k | 1.7k | 339 | 41 | $0.0008 | 14s | 3012 |
| q20 | ✓ | 98 | 5 | 0 | 0 | 4 | 7.1k | 3.8k | 288 | 0 | $0.0005 | 9s | 2568 |
| q25 | ✓ | 2025-W38 | 3 | 0 | 0 | 4 | 7.0k | 3.8k | 419 | 97 | $0.0006 | 14s | 2657 |
| q26 | ✗ | Borealis Online | 8 | 0 | 0 | 6 | 7.2k | 1.4k | 469 | 0 | $0.0008 | 16s | 2165 |

## Per-question metrics — `luna_stateless_r3`

| q | ok | answer | n_sql | slow | bash | turns | in | cached | out | reason | cost | wall | ctx end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | ✓ | 36531.85 | 8 | 0 | 0 | 9 | 20k | 13k | 549 | 0 | $0.0011 | 21s | 3051 |
| q02 | ✗ | 2025-W50 | 8 | 0 | 0 | 9 | 11k | 2.4k | 576 | 42 | $0.0011 | 25s | 2127 |
| q03 | ✓ | 815909.97 | 15 | 0 | 0 | 7 | 13k | 6.4k | 737 | 13 | $0.0011 | 25s | 3270 |
| q04 | ✓ | 0.1014 | 6 | 0 | 0 | 7 | 15k | 5.8k | 345 | 0 | $0.0011 | 13s | 2847 |
| q05 | ✓ | OSX-3 | 7 | 0 | 0 | 6 | 14k | 9.5k | 453 | 0 | $0.0008 | 17s | 3561 |
| q06 | ✓ | 2025-05 | 10 | 0 | 0 | 5 | 11k | 7.2k | 522 | 0 | $0.0007 | 15s | 3396 |
| q07 | ✓ | v4.18.0 | 6 | 0 | 0 | 7 | 14k | 7.8k | 272 | 0 | $0.0008 | 13s | 2760 |
| q08 | ✓ | 14.96 | 7 | 0 | 0 | 6 | 12k | 5.8k | 430 | 0 | $0.0009 | 13s | 2889 |
| q09 | ✓ | 0.7869 | 8 | 0 | 0 | 5 | 12k | 7.4k | 389 | 0 | $0.0008 | 12s | 4204 |
| q10 | ✓ | r.svensson | 5 | 0 | 0 | 6 | 11k | 5.8k | 253 | 0 | $0.0007 | 51s | 2664 |
| q11 | ✓ | 743 | 4 | 0 | 0 | 5 | 8.8k | 5.8k | 183 | 0 | $0.0005 | 8s | 2404 |
| q12 | ✓ | 54 | 10 | 0 | 0 | 6 | 8.8k | 3.1k | 499 | 0 | $0.0009 | 33s | 2462 |
| q13 | ✓ | Helios Group | 12 | 0 | 0 | 8 | 14k | 7.9k | 994 | 53 | $0.0011 | 35s | 2927 |
| q14 | ✓ | 2025-08 | 6 | 0 | 0 | 5 | 13k | 7.7k | 369 | 22 | $0.0008 | 16s | 4398 |
| q21 | ✓ | 31 | 5 | 0 | 0 | 5 | 9.1k | 5.5k | 271 | 0 | $0.0006 | 15s | 2985 |
| q22 | ✓ | Helios Grocery | 10 | 0 | 0 | 6 | 13k | 6.0k | 1.1k | 157 | $0.0013 | 29s | 4208 |
| q23 | ✓ | 35 | 6 | 0 | 0 | 5 | 12k | 7.7k | 348 | 0 | $0.0007 | 12s | 4235 |
| q24 | ✓ | 83 | 5 | 0 | 0 | 5 | 9.2k | 3.3k | 266 | 0 | $0.0007 | 12s | 3015 |
| q15 | ✓ | 2463087.54 | 14 | 0 | 0 | 7 | 13k | 6.5k | 666 | 0 | $0.0011 | 21s | 3077 |
| q16 | ✗ | 2025-W10 | 4 | 0 | 0 | 5 | 8.9k | 5.5k | 507 | 145 | $0.0006 | 13s | 2655 |
| q17 | ✓ | 0.0720 | 5 | 0 | 0 | 4 | 7.6k | 1.8k | 330 | 0 | $0.0008 | 11s | 2855 |
| q18 | ✓ | 100 | 9 | 0 | 0 | 6 | 14k | 6.3k | 390 | 0 | $0.0010 | 14s | 3737 |
| q19 | ✓ | 2025-W20 | 7 | 0 | 0 | 7 | 15k | 6.9k | 680 | 185 | $0.0013 | 31s | 3404 |
| q20 | ✓ | 98 | 3 | 0 | 0 | 4 | 6.4k | 3.6k | 229 | 0 | $0.0004 | 8s | 2228 |
| q25 | ✗ | 2025-W37 | 4 | 0 | 0 | 5 | 8.7k | 5.6k | 281 | 0 | $0.0005 | 11s | 2466 |
| q26 | ✗ | Borealis Online | 6 | 0 | 0 | 7 | 6.7k | 2.2k | 357 | 0 | $0.0007 | 15s | 1941 |

## ICL: context growth by question

`luna_icl_r1`

| q | context tokens at end | episode input tokens | episode cached |
|---|---|---|---|
| q01 | 1853 | 5.8k | 2.7k |
| q02 | 3797 | 17k | 14k |
| q03 | 4687 | 17k | 12k |
| q04 | 7344 | 26k | 20k |
| q05 | 7776 | 15k | 14k |
| q06 | 8302 | 16k | 15k |
| q07 | 9753 | 37k | 34k |
| q08 | 10704 | 51k | 47k |
| q09 | 11453 | 34k | 32k |
| q10 | 12666 | 49k | 47k |
| q11 | 13114 | 39k | 36k |
| q12 | 13933 | 41k | 39k |
| q13 | 14456 | 28k | 28k |
| q14 | 14906 | 29k | 27k |
| q21 | 15729 | 31k | 29k |
| q22 | 16880 | 49k | 46k |
| q23 | 17218 | 34k | 33k |
| q24 | 17794 | 35k | 34k |
| q15 | 20079 | 208k | 203k |
| q16 | 20733 | 82k | 81k |
| q17 | 21082 | 42k | 41k |
| q18 | 21768 | 86k | 84k |
| q19 | 22251 | 44k | 43k |
| q20 | 22643 | 67k | 67k |
| q25 | 23005 | 46k | 45k |
| q26 | 23673 | 47k | 46k |

`luna_icl_r2`

| q | context tokens at end | episode input tokens | episode cached |
|---|---|---|---|
| q01 | 2171 | 6.6k | 3.2k |
| q02 | 4708 | 17k | 12k |
| q03 | 5142 | 10.0k | 9.2k |
| q04 | 7866 | 28k | 25k |
| q05 | 8297 | 16k | 15k |
| q06 | 8836 | 17k | 10k |
| q07 | 10613 | 49k | 46k |
| q08 | 11357 | 44k | 41k |
| q09 | 12192 | 36k | 34k |
| q10 | 13129 | 38k | 36k |
| q11 | 13576 | 40k | 39k |
| q12 | 14204 | 42k | 41k |
| q13 | 14770 | 29k | 28k |
| q14 | 15223 | 30k | 29k |
| q21 | 16124 | 31k | 30k |
| q22 | 17546 | 51k | 49k |
| q23 | 17880 | 36k | 35k |
| q24 | 18394 | 36k | 35k |
| q15 | 20651 | 156k | 145k |
| q16 | 21535 | 84k | 81k |
| q17 | 21886 | 44k | 43k |
| q18 | 22452 | 67k | 66k |
| q19 | 23091 | 68k | 66k |
| q20 | 23399 | 47k | 46k |
| q25 | 23847 | 47k | 46k |
| q26 | 24480 | 48k | 47k |

## Memory: memory dir size and bash calls by question

`luna_memory_guided_r1`

| q | memory bytes | files | bash calls | post-submit turns |
|---|---|---|---|---|
| q01 | 0 | 0 | 0 | 0 |
| q02 | 0 | 0 | 0 | 0 |
| q03 | 0 | 0 | 0 | 0 |
| q04 | 0 | 0 | 0 | 0 |
| q05 | 0 | 0 | 0 | 0 |
| q06 | 0 | 0 | 0 | 0 |
| q07 | 0 | 0 | 0 | 0 |
| q08 | 0 | 0 | 0 | 0 |
| q09 | 0 | 0 | 0 | 0 |
| q10 | 0 | 0 | 0 | 0 |
| q11 | 0 | 0 | 0 | 0 |
| q12 | 0 | 0 | 0 | 0 |
| q13 | 0 | 0 | 0 | 0 |
| q14 | 0 | 0 | 0 | 0 |
| q21 | 0 | 0 | 0 | 0 |
| q22 | 0 | 0 | 0 | 0 |
| q23 | 0 | 0 | 0 | 0 |
| q24 | 0 | 0 | 0 | 0 |
| q15 | 0 | 0 | 0 | 0 |
| q16 | 0 | 0 | 0 | 0 |
| q17 | 0 | 0 | 0 | 0 |
| q18 | 0 | 0 | 0 | 0 |
| q19 | 0 | 0 | 0 | 0 |
| q20 | 0 | 0 | 0 | 0 |
| q25 | 0 | 0 | 0 | 0 |
| q26 | 0 | 0 | 0 | 0 |

`luna_memory_r1`

| q | memory bytes | files | bash calls | post-submit turns |
|---|---|---|---|---|
| q01 | 0 | 0 | 0 | 0 |
| q02 | 0 | 0 | 0 | 0 |
| q03 | 0 | 0 | 0 | 0 |
| q04 | 0 | 0 | 0 | 0 |
| q05 | 0 | 0 | 0 | 0 |
| q06 | 0 | 0 | 0 | 0 |
| q07 | 0 | 0 | 0 | 0 |
| q08 | 0 | 0 | 0 | 0 |
| q09 | 0 | 0 | 0 | 0 |
| q10 | 0 | 0 | 0 | 0 |
| q11 | 0 | 0 | 0 | 0 |
| q12 | 0 | 0 | 0 | 0 |
| q13 | 0 | 0 | 0 | 0 |
| q14 | 0 | 0 | 0 | 0 |
| q21 | 0 | 0 | 0 | 0 |
| q22 | 0 | 0 | 0 | 0 |
| q23 | 0 | 0 | 0 | 0 |
| q24 | 0 | 0 | 0 | 0 |
| q15 | 0 | 0 | 0 | 0 |
| q16 | 0 | 0 | 0 | 0 |
| q17 | 0 | 0 | 0 | 0 |
| q18 | 0 | 0 | 0 | 0 |
| q19 | 0 | 0 | 0 | 0 |
| q20 | 0 | 0 | 0 | 0 |
| q25 | 0 | 0 | 0 | 0 |
| q26 | 0 | 0 | 0 | 0 |
