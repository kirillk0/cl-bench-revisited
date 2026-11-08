# PRIVATE: temporal operations SQLite benchmark

This entire directory belongs to the trusted harness. **Never mount or copy this directory into an agent sandbox.** `generate.py`, `definitions.py`, `gold.json`, manifests, seed, scorer and audit are private. The study and benchmark roots have mode 0700; the seed config has mode 0600. Filesystem permissions are not isolation from a process running under the same UID: use a separate UID/container/mount namespace, with no access to the private tree or this conversation.

New, locally authored synthetic questions and data; no copied published task set and no external/API calls. There is no claim of a worldwide exhaustive novelty search. Seed is drawn once with Python `secrets.token_bytes(32)`, committed to `private/generated_config.json` with SHA-256 **before any database population**, and reused by default. Do not delete that file to reroll a run. Seed randomness permutes failure/retry membership and tenant identities; deliberately designed metric totals and confounding relationships are fixed. Private files must not be fed to tested models, including through conversation history.

## Build and audit (Python standard library only)

```sh
cd /workspace/memory_sql_study/bench
./generate.py
./audit.py
```

Generation replaces the two snapshots and task/gold manifests, never the preexisting seed. Byte reproducibility is tested with the same Python/SQLite runtime. Cross-version SQLite binary layout or Python random implementation is not promised; logical metrics are audited. `pre.db` is built first; `post.db` starts as an actual copy and receives the migration. There are no network libraries, API/model invocations or git commits in this workflow.

### Artifacts

* `manifests/tasks.json`: W1 → W2 → T1 → T2 → T3, English instructions and per-task JSON Schema.
* `manifests/arms.json`: identical task-to-snapshot SHA-256 bindings for `no_memory`, `raw_history`, `distilled_memory`.
* `snapshots/pre.db`, `snapshots/post.db`: 20/22 tables, clean FKs, explicit temporal intervals, normalized reference dimensions. **T3 uses post.db in every arm and every fresh baseline.**
* `agent/README.md`: short, invariant, agent-visible data contract. No warmup-only definitions.
* `gold.json`: every exact answer value, section-by-section runnable SQL evidence, numeric tolerances, factual verdict rubric. JSON array order is not meaningful.
* `private/gold_summary.md`: complete human-readable exact gold values.
* `private/audit_report.json`: generated hidden audit output and row counts.
* `private/generated_config.json`: seed and seed hash; `private/migration_v2.sql`: DDL companion to full migration implementation `migrate()` in `generate.py`.
* `stage.py`: strict allowlist exporter; `grade.py`: deterministic metric scorer and read-only evidence execution checks.

## Safe staging: three arms, exactly the same snapshots

```sh
./stage.py --task T3 --arm no_memory --dest /some/isolated/new-run/task
```

Destination must be empty and outside the private root. Only **current.db, README.md, TASK.json** are exposed, byte-identical across arms for the same task. `TASK.json` contains no gold, source path, seed or snapshot filename. Give the tested agent its contents as instructions and access to these three files. Evidence SQL uses literal bounds and must run read-only without setup or other files. No answer can require prior task state. Keep each task DB immutable; snapshot paths must not be agent-selected.

Arm semantics are a harness responsibility: fresh context per task for `no_memory`; prior raw interaction for `raw_history`; permitted distilled prior memory for `distilled_memory`. Task content, README, model settings, tools and snapshots are otherwise held equal. Do not let memory contain private gold or trusted audit output. A T3 fresh agent gets post.db, **not the earlier snapshot**. Benchmark scripts do not execute model calls or implement a memory algorithm.

### Migration / challenge design (private)

* W1 calibrates operation/attempt/final-failure grain and alias-to-pool aggregation.
* W2 applies the event-time policy change on idx-north: 250→80 ms, with stable upstream p95. Multiple route aliases and historical profile segments make a timeless join wrong.
* T1 has a deterministic Simpson-style reversal. Candidate is worse in every matched period×region×class slice, but pooled candidate and aggregate time trend look favorable because exposures and workload mix differ. No arbitrary causal “correct opinion”: both the standardized contrast and its observational limitation are explicit.
* T2 retains the DEADLINE symptom, but affected sync-south has unchanged 250 ms policy and observed worker-limit/queue pressure. The measured facts contradict reuse of W2's deadline-tightening explanation.
* T3 silently receives a migrated schema: outcome_events is current operation-grain instrumentation, joined through actual execution cells. attempt_events is intact genuine history, not a fabricated stale result feed. Registry intervals identify canonical coverage. Legacy routing assignments end at migration; 80% of new operations execute outside their intended route's former pool. Multiple execution cells per physical pool require aggregation. This is a real discoverable path/grain/attribution change, not an undocumented scoring rule. The public task does not announce a migration.

### Scope and auditing

The 40–100k event budget counts attempt_events + outcome_events (logical_operations is a separate request identity fact). Even including request rows, both snapshots remain under 100k operational fact rows. Every included request is complete; no duplicate IDs, broken FKs or overlapping effective mappings. Small synthetic categorical cardinalities and 2-period windows keep tasks tractable: typically schema/registry inspection plus 2–5 aggregation queries and telemetry/change checks, not a many-hour reverse engineering exercise. The intended 5–25 shell calls is a design target, **not measured model performance**.

Audit verifies integrity/FKs, budgets, per-request temporal joins, retry invariants, feed coverage, outcome elapsed times, full old-attempt preservation, current T3 data, and byte-identical staged artifacts across all arms. Every answer is checked both by SQL and by an independent Python reconstruction over base tables, with additional manually specified anchors. SQL evidence is executed inside fresh staged directories for every task and arm, proving there are no external data dependencies. This is a structural/numerical independence test, not a claim that agents were empirically benchmarked.

## Grading recommendation

Score T1–T3 equally; report W1/W2 calibration separately, not in the primary memory-effect score.

* **70 points deterministic metrics:** equal weight per named answer section; within a section compare categorical dimensions and metric leaves, not row order. Integer counts/IDs/timestamps exact. Other numbers pass if `abs(error) <= max(1e-4, 1e-6 * abs(gold))`. JSON before/after config strings may be equivalent parsed JSON with different formatting. Missing/duplicate/extra groups do not earn full credit.
* **10 points SQL evidence:** executable read-only SQL with actual table reads; correct scope, grain and attribution; reproduces substantive claims. Table-reading yet unrelated/constant evidence receives no support credit. `grade.py` checks safe execution, **not full semantic entailment**.
* **20 points factual assessment/caveats:** use each task's explicit rubric in gold.json, equal weight among criteria; award for supported facts and calibrated uncertainty, not exact phrasing. Alternative hypotheses are acceptable if labeled and not contradicting measured values. Do not require an invented mechanism beyond the available evidence. W1's criteria can be expressed in caveats.

```sh
./grade.py --task T1 --response /path/to/response.json
```

The scorer emits metrics, schema diagnostics and evidence checks; intentionally no invented automated qualitative score. Invalid final JSON/schema cannot receive full credit. Record failure modes separately (wrong snapshot, retry double counting, non-temporal joins, pooled-only inference, transferred W2 cause, stale-feed or intended-route attribution).
