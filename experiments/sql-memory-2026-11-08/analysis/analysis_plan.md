# Case-oriented analysis plan (before evaluation)

This is an exploratory mechanism study, not a leaderboard or powered statistical test. protocol.md is authoritative. One five-task sequence per model/arm; Luna is used first to debug methodology. Any adaptive extension/version is logged and all attempts retained. No best-of-N selection.

## Comparisons
- Compare all three arms on the same task wording and exact current DB hash.
- Primary outcome: required numeric fields and interpretation against deterministic SQL and frozen rubric. Report field-level and whole-task correctness, plus manual evidence review. A format-only issue is separate from a wrong analytical conclusion.
- No evaluator feedback is sent to agents during the sequence; results cannot leak to later tasks.
- Report all disagreements and all matching outcomes, not only memorable examples. Sample size is case count; calls and model tokens are not independent observations.
- Guards, API errors, incomplete responses and truncation are flagged. A guard-censored case is not clean evidence of memory harm and may receive a separately labelled larger-guard diagnostic.

## Causal diagnostics, selected after inspecting discrepancies
1. First preserve a pre-target checkpoint (native history, allowed memory files, DB hash). A repeat never advances the original trajectory.
2. Inspect divergence: what fact/plan was retrieved or repeated, whether it was true at recording, whether current evidence contradicted it, first consequential SQL choice, and whether answer itself follows from the actual results.
3. For an unclear discordance, run intact repeat of both relevant conditions before interpreting one flip. If a concrete memory is implicated, compare intact with minimal deletion/correction and, where practical, irrelevant deletion of similar length (sham). All interventions are explicitly exploratory and chosen after seeing the error.
4. Full-history reset estimates the total effect of available context, not a specific note or reasoning mechanism. Native checkpoints must retain opaque state; no silent substitution with text summaries.
5. Markdown transplant/no-memory can test sensitivity to memory contents. Avoid fabricating a helpful note from the target gold: that would be oracle assistance, not natural memory. Preserve edit diffs and exact source checkpoints.
6. At most a few targeted repeats per candidate; stop when mechanism is clear or evidence remains ambiguous. Never continue until desired outcome. Report every attempt. If no robust correctness difference appears, say so; a cost-only result is still informative.

## Cost and time
- Record every API usage response, resolved model/provider, input/cache-read/cache-write tokens, total output and reasoning breakdown where exposed. Reasoning is a component of output, not additive again.
- USD: Anthropic verified rates including cache TTL and >100k tier; OpenRouter usage.cost authoritative. Codex subscription USD unknown, not zero. Distinguish billed/estimated and incomplete usage.
- Record setup/access probes separately; W1/W2 preparation cost; each target marginal cost; whole sequence including preparation; diagnostic incremental cost separately. Prefix reuse is charged by actual calls, not counted twice.
- Split action traces into schema/source reconnaissance, analytical computation, memory read/write, error recovery and final answer. Mixed steps may remain mixed; do not invent exact token attribution.
- Generic bash elapsed and wrapped sqlite3 invocation wall are measured; SQL time is nested in shell time, not additional. CLI may contain multiple SQL statements. Python sqlite3 bypasses wrapper: timing coverage explicitly partial, not zero. Flag each measured invocation >1s and any shell >1s.
- Record prompt bytes/state size and memory file size/diffs. Do not call every historical token 'useless': relevance requires trace inspection.
- Cache settings stable; preserve returned reasoning/native blocks. Actual cache hits, not nominal caching support, determine cost. Provider-wide cache sharing and shared-host contention limit cold-cache and latency comparisons.

## Isolation and disclosure
- Root-only evaluator/generator/native states; tested agents run separate unprivileged UIDs with network syscalls denied and no credentials in environment. Read-only current DB. Per-task scratch reset in ALL arms; only managed-memory directory survives in managed arm.
- Generic bash tool with identical capabilities, no bespoke SQL or memory tool. The sqlite3 executable is a timed read-only wrapper around the real CLI, not a new model-facing API.
- Public repository contains code, deterministic generation, tasks/gold and sanitized traces AFTER evaluation; no credentials or signed/encrypted replay payloads. Private native checkpoints retain opaque blocks for exact replay.
- Fresh data decreases memorized-answer risk but cannot establish absence of template familiarity. Endogenous memory varies in volume, quality and creation cost; three-arm comparison estimates policy packages, not a pure file-format effect.
