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
