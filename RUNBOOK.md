# RUNBOOK — how the experiment is executed and analysed

## Phases
0. Access checks (done 2026-11-08): Anthropic (claude-haiku-5-5), OpenRouter (z-ai/glm-5.3-flash),
   Codex endpoint (gpt-6-luna; refresh token rotates — kept only in container), GitHub push.
1. Build: providers / dataset / runner (parallel), live smoke tests.
2. Calibration on gpt-6-luna `stateless`: aim for ~40–70 % accuracy on pre-drift questions.
   Too easy → harden questions (more hops, hierarchy, date-range joins); too hard → simplify
   wording, not the schema.
   Result 2026-11-08: 18/20 on `data/questions.json` (both misses = ISO-week trap) → second
   catalogue `data/questions_v2.json` (same GT for q01..q20, business wording without schema
   hints, + q21..q26 investigative questions; 18 pre / 8 post → `--drift-after 18`).
   `python -m clrev.dataset.build --out data/ [--skip-db]` regenerates both catalogues.
3. Main runs, one sequence per (model × mode): stateless, icl, memory; drift after the last
   pre-drift question. Order: luna (method), then haiku (≤ $20), then glm (≤ $5).
4. Divergence triage per question (paired across the three modes):
   * all correct → compare *cost structure* (exploration SQL count, context size, tokens).
   * any divergence → read the trajectories; classify the cause with evidence:
     - `memory_helped` / `icl_helped`: stateless failed on a fact/approach that the stateful
       run had from history/notes (quote the note / earlier turn).
     - `memory_hurt` / `icl_hurt`: the stateful run reused a stale/wrong fact or skipped
       verification that the stateless run performed (quote).
     - `unrelated`: arithmetic/SQL slip, format, sampling noise.
   * when causality is unclear → `replay --from-snapshot --repeats 3` for the stateful mode
     and 3 stateless repeats; if still unclear → edit the memory note / state and replay.
5. Report: reports/REPORT.md — per-model paired tables, case studies with quotes, cost
   structure, drift behaviour, limitations.

## Budget guard
Track cumulative cost per model from summary.json after every sequence; stop haiku at $18,
glm at $4.5.
