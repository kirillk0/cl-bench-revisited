# Start here: completed experiment and recovery notice

- [Results in Russian](REPORT.md)
- [Standalone HTML evidence viewer](public_results/report.html) (download/open locally)
- [Archive completeness and recovery](RECOVERY.md)
- [Costs and all 448 archived shell commands](analysis/cost_audit.md)

**Final container loss:** 45 original full traces are recovered and hash-verified (43 primary + 2 diagnostic). For the other 15 attempts, commands and cost audit survive, not full dialogues. Five GLM tool-only replays are distinctly labeled. No fabricated original traces or private checkpoints. The old summary/strict grades are an interim snapshot, not a final accuracy score. Browser stress-testing was not repeated after recovery; recovered HTML is static, has no JavaScript/external dependencies, and was parsed locally.

---

# SQL agent memory: exploratory three-arm case study

Repository: `kirillk0/cl-bench-revisited`, branch `experiment/sql-memory-2026-11-08`.

New synthetic operational analytics data, not public CL-Bench questions. A read-only SQLite warehouse has relational reference tables, temporal route assignments, retries, telemetry and configuration changes. Five tasks: counting calibration, early incident, stratified trend, different incident, and an unannounced instrumentation/schema migration. All tasks independently recoverable from the CURRENT snapshot. The migration retains true historical tables but changes current source/grain/attribution.

Models verified by real native tool calls: Anthropic `claude-haiku-5-5`; OpenRouter `z-ai/glm-5.3-flash`; ChatGPT/Codex `gpt-6-luna` (Responses Lite, client 0.167.0). Three treatments: stateless; full native ICL history including returned reasoning blocks; fresh sessions with agent-managed notes in `../memory`. Same generic bash tool, no bespoke SQL/memory tools. No automatic note injection and no correctness feedback between tasks.

No query-count reward. SQL CLI invocation timing, long calls >1s, model tokens/cache usage, money and latency are secondary diagnostics. Guards: 60k characters output, 60s shell, 80 model turns/15min per task; censored cases separately flagged. Generic shell uses separate unprivileged UIDs, denied network syscalls, no credential environment, root-only evaluator. SQLite CLI wrapper preserves its normal interface and logs invocation wall time. Python SQLite timing coverage is partial.

Plan and limits: `analysis/protocol.md`, `analysis/analysis_plan.md`. This is exploratory and adaptively diagnosable, not a statistically powered benchmark. All versions/attempts retained; no cherry-picked score claim. Numeric grading tolerates ordinary rounding (absolute .01 for non-count numbers), exact integer counts. Qualitative causality/evidence reviewed separately.

Generation (stdlib Python): `python bench/generate.py`; validation: `python bench/audit.py`. Snapshot hashes and reference SQL stored in `bench/`. Generator/gold are inaccessible to tested shells; synthetic seed/config and reproducibility code may be published after freezing. No actual model call has access to repository/network.

Execution: `python run_study.py --provider codex --arm stateless --job pilot-luna-stateless` (provider credentials are supplied externally). Native opaque replay states stay local/private; public results redact signatures/encrypted payloads but retain visible actions/results, usage and final answers. Credentials NEVER go into the repository.

USD accounting: Anthropic verified model rates and cache/long-context tier; OpenRouter actual `usage.cost`; Codex USD unknown (subscription), not zero. Budgets across all probes/experiments <=$20 Anthropic and <=$5 OpenRouter; stop guards reserve headroom. Environment/setup work is not represented as free API usage.
