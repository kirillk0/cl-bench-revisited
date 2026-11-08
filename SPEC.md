# SPEC — memory modes experiment (cl-bench-revisited, branch memory-modes-2026-11)

Goal: qualitative, paired comparison of three ways of carrying experience across a
sequence of SQL-analysis questions over one database:

* `stateless` — fresh conversation per question, nothing carried over.
* `icl`       — one continuous conversation for the whole sequence (full history,
                native tool calls/results, **reasoning preserved natively**, prompt caching).
* `memory`    — fresh conversation per question, but the agent has a `bash` tool in a
                persistent working directory (mini-swe-agent style) and a *general* hint
                that the directory persists across sessions. Nothing else is carried.

Primary outcome = correctness of the final answer. Cost (tokens, USD, wall-clock, SQL
count, slow SQL) is secondary and reported for the structure-of-cost analysis.
We do NOT penalise the number of SQL queries. Row cap for SQL results is generous
(default 300 rows / 24 000 chars). Queries slower than 1.0 s wall clock are flagged.

Second phase: a *silent schema migration* applied after question N (no notice to the
agent). Post-migration questions test stale ICL context / stale memory notes.

Everything must be reproducible from this repo (seeded generators), except API calls.

## Models

| key      | provider        | model id            | prices (USD per 1M tok)                                   | budget |
|----------|-----------------|---------------------|-----------------------------------------------------------|--------|
| luna     | openai_codex    | gpt-6-luna          | in 0.10, cached 0.01, cache-write 0.125, out 0.50 (imputed; subscription) | unlimited (method dev here) |
| haiku    | anthropic       | claude-haiku-5-5    | ≤100k prompt: in 0.10, cache-read 0.01, 5m cache-write 0.125, out 0.50; >100k prompt: 0.50/0.05/0.625/2.50 | ≤ $20 |
| glm      | openrouter      | z-ai/glm-5.3-flash  | in 0.0335, out 0.083 (use OpenRouter `usage.cost` when present) | ≤ $5 |

Codex endpoint details (verified 2026-11-08):
* Token exchange: `POST https://auth.openai.com/oauth/token` json
  `{grant_type: refresh_token, client_id: app_EMoamEEZ73f0CkXaXp7hrann, refresh_token}`.
  **Refresh tokens rotate** — persist the whole response to `secrets/openai-tokens.json`
  (chmod 600, gitignored) and always use the latest refresh_token. Access token lasts ~10 days.
* Account id = JWT claim `https://api.openai.com/auth`.`chatgpt_account_id`.
* `POST https://chatgpt.com/backend-api/codex/responses`, headers
  `Authorization: Bearer <access>`, `chatgpt-account-id: <id>`, `OpenAI-Beta: responses=experimental`,
  `originator: codex_cli_rs`, `accept: text/event-stream`. Body is Responses API:
  `{model, instructions, input:[...], tools, store:false, stream:true,
    include:["reasoning.encrypted_content"], reasoning:{effort:"medium", summary:"auto"},
    prompt_cache_key:<conversation id>}`. Non-streaming is not supported; parse SSE and take
  `response.completed`. Reasoning items come back with `encrypted_content` → must be fed back
  in `input` on the next call (this is how reasoning is preserved).
* Model list: `GET https://chatgpt.com/backend-api/codex/models?client_version=1.0.0`.

Anthropic: Messages API, `claude-haiku-5-5`, adaptive thinking (default effort). Keep
`thinking` blocks returned in the assistant turn inside the history (required for tool use
anyway). Prompt caching via `cache_control: {type: ephemeral}` on the system block and on the
last block of the most recent user/tool_result message (re-marked each turn). Native `tools`.

OpenRouter: `POST https://openrouter.ai/api/v1/chat/completions`, model `z-ai/glm-5.3-flash`,
native `tools`, `usage: {include: true}`, `reasoning: {enabled: true}` and **pass
`reasoning_details` back** in assistant messages (OpenRouter "preserving reasoning blocks").
Check which upstream provider(s) serve it and whether tool calling works; pin a provider via
`provider: {order:[...], allow_fallbacks:false}` if results are inconsistent.

## Provider interface (clrev/providers/base.py)

```python
@dataclass
class ToolSpec:   name: str; description: str; parameters: dict           # JSON schema
@dataclass
class ToolCall:   id: str; name: str; arguments: dict
@dataclass
class Usage:      input_tokens: int; cached_input_tokens: int; cache_write_tokens: int
                  output_tokens: int; reasoning_tokens: int; cost_usd: float | None; raw: dict
@dataclass
class TurnResult: text: str | None; tool_calls: list[ToolCall]; reasoning_summary: str | None
                  usage: Usage; stop_reason: str; latency_s: float; raw: dict

class Conversation:            # one provider-native message history
    def add_user(self, text: str) -> None
    def add_tool_results(self, results: list[tuple[str, str]]) -> None   # (call_id, output_text)
    def step(self) -> TurnResult   # one model call with the full history; appends the
                                   # assistant turn (incl. native reasoning carrier) to history
    def export_state(self) -> dict # JSON-serialisable; restore_conversation(state) must
                                   # reproduce the exact provider-native history
    def history_view(self) -> list[dict]  # provider-agnostic rendering for logs:
                                   # {role, text, tool_calls, tool_results, reasoning_summary}
    def context_tokens_estimate(self) -> int  # last known prompt size (from usage)

class Provider:
    key: str; model: str
    def new_conversation(self, system_prompt: str, tools: list[ToolSpec], conv_id: str) -> Conversation
    def restore_conversation(self, state: dict) -> Conversation
```

Retries: exponential backoff on 429/5xx/network, max ~6 attempts, log every attempt.
Every raw request/response pair is appended to a JSONL raw log (path given by the runner)
with secrets redacted.

## Tools exposed to the model

* `run_sql(sql: str)` — read-only SQLite (`PRAGMA query_only`, authorizer denies writes).
  Returns header + up to ROW_CAP rows as aligned text, "(showing first N of M rows)" when
  truncated (M via a wrapped COUNT when cheap, otherwise "more"), execution wall time in ms.
  Statement timeout 30 s (progress handler). Result also capped at CHAR_CAP characters.
* `submit_answer(answer: str)` — final answer. Returns feedback text:
  `CORRECT` or `INCORRECT. Correct answer: <gt>` (CL-Bench style; no GT SQL is revealed).
  In `stateless` mode the episode ends right after. In `icl`/`memory` the model may keep
  acting (e.g. write notes); episode ends when a turn has no tool calls or after
  MAX_POST_SUBMIT_TURNS (default 8).
* `bash(command: str)` — **memory mode only**. Runs `bash -lc` as unprivileged user
  `memuser`, cwd = the run's memory dir (persistent across questions of the run),
  timeout 30 s, output capped at 16 000 chars, stdout+stderr. The SQLite files are
  chmod 600 root → not readable from bash. Nothing else sandboxed; note it in the report.

Max tool-call turns per question: 40. Hard stop → counted as incorrect ("no answer").

## System prompts (keep general; identical across models)

stateless / icl:
> You are a data analyst agent with read-only SQL access to a SQLite database. The schema
> is not provided — explore it with SQL (sqlite_master, PRAGMA table_info, sampling).
> Answer the question by running queries with `run_sql`, then call `submit_answer` with the
> final value only, in the format the question asks for. You may run as many queries as you
> need. After submitting you will be told whether the answer was correct.
icl adds: "You will be asked a series of questions about the same database in this
conversation."
memory adds: "You also have a `bash` tool. It runs in a persistent working directory that
is kept between sessions (each question is a separate session with no conversation
history). Anything you write there is available in later sessions, and anything from
earlier sessions is already there. Using it is optional; what to keep, if anything, is up
to you."

## Sequence protocol

Fixed question order (no shuffle) so the three modes are paired per question.
`stateless`: Q_k alone. `icl`: Q_1..Q_n in one conversation; after `submit_answer`
feedback (tool result) the next user message is Q_{k+1}. `memory`: Q_k in a fresh
conversation with the memory dir as left by Q_{k-1}.

Silent migration: after question `drift_after` the runner swaps the DB file to the
migrated one. No notice of any kind.

Snapshots for ablations: after each question store (a) icl: `export_state()`,
(b) memory: tar.gz of the memory dir. `runner.py replay --from-snapshot` re-runs a single
question from a snapshot (repeatable; used to test causality on divergent cases, including
edited memory notes).

## Logging / outputs

`runs/<run_id>/config.json`, `runs/<run_id>/episodes/q<NN>.json(.gz)`:
`{question_id, mode, model, correct, answer, gt, n_sql, n_bash, slow_sql:[{sql, ms}],
  turns:[{text, reasoning_summary, tool_calls:[{name,args,result_preview,ms}], usage}],
  totals:{input, cached, cache_write, output, reasoning, cost_usd, wall_s}, context_tokens_end,
  error}` plus full `history_view`. `runs/<run_id>/summary.json` aggregates.
Raw API logs → `runs/<run_id>/raw/*.jsonl` (gitignored; keep locally).

Grading: GT has `answer`, `type` (int|float|str), `tolerance` (abs for numbers; for str
case/space-insensitive exact). Accept numbers with thousands separators / currency symbols
stripped.

## Dataset (clrev/dataset/build.py → data/payops.db, data/payops_v2.db, data/questions.json, data/questions_v2.json)

Domain: a card-payment processing platform ("PayOps"), 2025-01-01..2025-12-31.
Emphasis: convoluted *reference* schemas (dictionaries), trend/correlation questions and
incident investigation over logs — not broken data. Realistic quirks are allowed when they
are the kind analysts meet every day (effective-dated dictionaries, currency exponents,
hierarchical groups, versioned code dictionaries). Deterministic (seed 20261108), SQLite
file ≲ 80 MB, every GT query < 5 s.

Reference tables (all surrogate keys): dim_region, dim_country(region_id), dim_currency
(iso_code, exponent incl. JPY=0, KWD=3), fx_rate(rate_date, currency_id, rate_to_eur),
dim_merchant_group(parent_group_id self-ref, 3 levels), dim_mcc_category, dim_mcc,
dim_merchant(group_id, mcc_id, country_id), dim_acquirer, dim_processor,
route(acquirer_id, processor_id, priority), dim_terminal_model(vendor, model_name,
firmware_family), dim_terminal(model_id, acquirer_id), terminal_assignment(terminal_id,
merchant_id, valid_from, valid_to NULL=open) — terminals DO move between merchants, so
historic joins must use the date range; response_code_dict(code, scheme_version, meaning,
is_decline, is_timeout, valid_from, valid_to) — version 2 from 2025-07-01 changes the
meaning of a few codes; txn_status_dict; fee_schedule(acquirer_id, pct_bps, fixed_minor,
valid_from, valid_to); dim_component(team_id), dim_team, dim_severity, dim_event_type,
dim_root_cause, operator(team_id).

Facts: txn(ts_utc ISO text, terminal_id, amount_minor, currency_id, status_id,
response_code, route_id, latency_ms, card_scheme) ~250k rows; settlement(txn_id,
settled_at, fee_minor, fee_schedule_id); service_event(ts_utc, component_id, level,
event_type_id, correlation_id, route_id NULL, message) ~150k rows; deployment(component_id,
version, deployed_at, operator_id, rolled_back_at); config_change(component_id, key,
old_value, new_value, changed_at, operator_id, ticket); incident(code 'INC-2025-NNNN',
opened_at, closed_at, severity_id, component_id, root_cause_id, summary);
incident_link(incident_id, correlation_id).

Planted, documented phenomena (data/STORIES.md, never shown to models): a bad deployment
causing a latency/timeout spike on one component → incident; a config change
(cache TTL) on fx-service causing stale fx and settlement discrepancies; an acquirer
outage window → timeouts on its routes; a terminal firmware family with elevated declines
from a date; weekly seasonality + growth trend for one merchant group; a merchant group
whose terminals were re-assigned mid-year (so naive "current assignment" joins are wrong).

Questions (data/questions.json; ~14 pre-drift + ~6 post-drift; each with id, text,
expected answer format, gt_sql, answer, type, tolerance, knowledge_tags, difficulty):
mix of trend (which ISO week / month peaked; first month exceeding X), correlation
(terminal model vs decline rate; deployment vs latency), incident investigation (which
deployment/config change preceded; timeout share on acquirer routes during the window;
operator with most incidents within 60 min after their changes), reference-heavy
aggregation (EUR volume via fx + exponent + hierarchy). Knowledge that *recurs* across
questions so memory can matter: group hierarchy, date-range assignment join, decline
classification via versioned dictionary, exponent/fx conversion, incident↔event linkage.
Answers are single values (number, YYYY-Www, YYYY-MM, an id/code, a name).

Migration (payops_v2.db): clean renames, not traps — terminal_assignment →
terminal_merchant_link(start_ts, end_ts); dim_merchant.group_id → merchant_group_id;
service_event split into service_event_h1 / service_event_h2 with no unifying view;
response_code_dict gains scheme_version 3 (valid from 2025-10-01) that re-maps two codes;
fx_rate → fx_rate_daily(rate_date, currency_id, eur_per_unit) same semantics. Post-drift
questions are answerable only against the new schema; GT SQL is written for v2.

### Question catalogues: `questions.json` (explicit) vs `questions_v2.json` (hard)

Calibration (gpt-6-luna, stateless) on `questions.json` gave 18/20 — too easy, because the texts
explain the schema mechanics ("assigned at the time of each transaction", "dictionary version valid
at the transaction's timestamp", "EUR per unit", "through correlation ids"). `build.py` therefore
also writes `data/questions_v2.json` over the *same* databases:

* q01..q20: same ids, `gt_sql`, answers and tolerances; business wording only — the metric stays
  unambiguous (interval bounds, UTC, rounding, status, "including all sub-groups at any level") but
  nothing says how the schema encodes it (effective-dated assignments, versioned code dictionary,
  exponents, incident↔event linkage, h1/h2 split are latent; DDL comments are the only hint).
* q21..q26: investigative / trend questions requiring a candidate scan (rolled-back release with most
  errors while live, division with the steepest weekly OLS trend, retries after timeouts on the outage
  day, config change followed by the largest error burst, platform-wide weekly error peak, chain
  with the largest H1→H2 loss). Margins to the runner-up are recorded in `rationale`.
* every question has `naive_variants: [{description, sql, answer, discriminative}]` for error triage.
* file order = run order: 18 pre-drift (q01..q14, q21..q24) then 8 post-drift (q15..q20, q25..q26)
  → run with `--questions data/questions_v2.json --drift-after 18`.

## Repo layout

```
SPEC.md  README.md  requirements.txt  .gitignore(secrets/, *.db, runs/**/raw/)
clrev/providers/{base,anthropic_p,openai_codex,openrouter_p}.py
clrev/dataset/build.py   clrev/tools.py   clrev/grade.py   clrev/runner.py   clrev/analyze.py
data/questions.json  data/questions_v2.json  data/STORIES.md  data/schema_v1.sql data/schema_v2.sql (DDL dumps)
runs/<run_id>/...   reports/
tests/
```
