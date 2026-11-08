# Amendments / infrastructure deviations

## Before first model evaluation
- Reduced drafted allocation of four seeds to ONE exploratory sequence as requested by user; final protocol committed before evaluations.
- Removed overt anti-memory warning in T2 and conspicuous CURRENT/empty-feed warnings in T3. Ordinary data contract/registry remain visible in all tasks. No advance migration notification at task boundary.
- Numeric tolerance set to abs .01 / rel 1e-5 for non-count numbers, matching ordinary two-decimal reports; exact integer counts. This was in gold before evaluations; scorer implementation subsequently aligned with that configuration.
- Synthetic task/seed/reference package committed for reproducible freeze before model evaluation, not after as an earlier draft suggested. Tested agents have no network and cannot read repository. This does not create plausible model pretraining exposure to these new generated values.

## Pilot v1 invalidated (2026-11-08)
- Generic bash ran as separate unprivileged UIDs with no network and evaluator/credential directories protected, but absolute `/tmp` remained host-shared.
- Stateless Luna wrote `/tmp/q.py` as 0644. Managed Luna attempted same path, failed to overwrite (different owner), then read/executed the other's script. This is a real cross-arm contamination confound.
- Canceled all three `pilot-luna-*` jobs; retain traces/usage as infrastructure-development attempts, exclude ALL v1 tasks from memory comparisons. Inflight canceled request token usage may be unavailable; Codex marginal USD is unknown anyway.
- Replaced sandbox with a real chroot per arm: normal bash/coreutils/SQLite/Python stdlib, private `/tmp`, `/var/tmp`, `/dev/shm`, per-task cleanup; only managed `memory` persists. Network syscalls still denied; no keys passed. No proxy or tool semantics changed.
- Tested same `/tmp/q.py` path in two jails (A/B values remain isolated), scratch reset, standard SQLite/Python execution, credentials absence and network denial. Tests passed.
- `build_jail.py` included for reproducibility. SQLite library/runtime shared read-only via filesystem hardlinks; databases and writable directories separate. New jobs named `pilot2-luna-*`.


## Post-run evaluation/guard diagnostics
The frozen exact-label grader rejects arbitrary but unambiguous period labels although the schema permits strings. Preserve strict grades and add separately documented semantic-normalized grading, never correcting numbers. Haiku stateless T1 stopped at max_tokens=8192 after successful tool work: censored, not memory failure. Add explicit CLI output-token override (default unchanged), run T1-only fresh diagnostic with 32768; run unattempted stateless T2/T3 at original settings in a separately named continuation. Error-response usage is in ledger even when absent from successful-turn totals.

## Selected diagnostic: GLM T2 inherited aggregation error
Selected after observing primary ICL W1/W2/T2 reuse operation-to-attempt fanout and COUNT(*) at attempt grain, versus fresh/managed trajectories. Run two additional exact pre-T2 native-history replays and two additional fresh T2 runs, identical database/prompts/defaults. Preserve initial runs separately. Test numerical correctness and presence of the specific fanout, not merely overall scores. Selection is exploratory; no population significance claim or inference that memory generally hurts. A reset removes all prior experience, not only the faulty SQL, hence isolates history treatment but not single-token mechanism. No gold correction or evaluator feedback supplied.


## Selected diagnostic: memory adoption/lifecycle clarity
Primary minimal instruction produced no notes in Luna/Haiku and one unconsumed answer.json in GLM. Separate Luna five-task sequence with explicit generic lifecycle wording (fresh conversations, only ../memory persists, no automatic injection), no prescribed note content, memory tool, mandatory write, or answers. Flag memory_instruction_variant=lifecycle. This changes instructions and is not pooled into primary three-arm outcome. Frozen dataset unchanged.


## Final recovered amendments (reconstructed from parent conversation)
After the already committed lifecycle-only diagnostic, one Luna managed sequence added generic maintain instruction; content still agent-selected, no gold. Actual Haiku effort was API-default (adaptive), not explicitly medium; provider_config now describes the actual request and matches pre-crash audit hash. GLM optional memory was read at T3, unlike earlier T1/T2. Final source runner reconstructed byte-for-byte against pre-crash hash.

All model calls completed before final container loss. See RECOVERY.md and recovery_inventory.json; 45 original complete traces hash-match pre-crash inventory, 15 full traces missing, aggregated costs and all448 shell commands preserved in uploaded audit. No model API calls after loss. Five lost GLM command trajectories (50 commands) were executed tool-only on exact regenerated databases; 50/50 exit codes match. These new outputs are explicitly not original traces. Full late semantic-grader files and private native checkpoints lost; strict existing grades are not final accuracy.
