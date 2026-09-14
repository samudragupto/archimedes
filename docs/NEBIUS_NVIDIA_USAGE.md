# How Archimedes uses Nebius Token Factory & NVIDIA Nemotron

## The hard constraint (and why it's good engineering)

Every LLM call in Archimedes goes to the **Nebius Token Factory**
(`NEBIUS_BASE_URL`, default `https://api.studio.nebius.com/v1/`) running
**NVIDIA open-source Nemotron models only**. The `openai` Python SDK is used
purely as an OpenAI-*compatible* client — no OpenAI, Anthropic or Google
models exist anywhere in the codebase (grep for it: the only place a model id
is constructed is `Settings.model_id_for_tier`, fed entirely by env vars).

Model ids are configuration, not code: swap a default `.env` value for a newer
catalog entry and the whole product follows — the routing tiers, prompts and
metering don't change.

```env
NEMOTRON_NANO_MODEL=nvidia/Llama-3_1-Nemotron-Nano-8B-v1      # confirm in the Token Factory catalog
NEMOTRON_SUPER_MODEL=nvidia/Llama-3_3-Nemotron-Super-49B-v1   # confirm in the Token Factory catalog
NEMOTRON_ULTRA_MODEL=nvidia/Llama-3_1-Nemotron-Ultra-253B-v1  # confirm in the Token Factory catalog
```

## Task → model → why

| Pipeline step | Task type | Tier | Model (default) | Why this tier |
|---|---|---|---|---|
| Extract requirements (per chunk) | `extraction` | **NANO** | Llama-3_1-Nemotron-Nano-8B | High-volume, small in/out, structure-not-style; temperature 0 for deterministic JSON. Runs once per 6k-token chunk, so cheapness multiplies. |
| Plan research queries | `planning` | **SUPER** | Llama-3_3-Nemotron-Super-49B | Judgment over the whole requirement set ("what evidence persuades this panel?") — beyond Nano, short structured output doesn't need Ultra. |
| Section outline + coverage | `planning` | **SUPER** | Super-49B | A constraint-mapping problem (sections ↔ page budget); mid model is the sweet spot. |
| Draft each proposal section | `drafting` | **ULTRA** | Llama-3_1-Nemotron-Ultra-253B | The only node whose output humans read as prose. Argument quality is the product; drafting is <30% of calls but >85% of tokens — this is where spend belongs. |
| Compliance audit | `audit` | **SUPER** | Super-49B | Whole-draft severity reasoning at temperature 0.2 — stable scores across reruns matter more than eloquence. |
| Revise failing sections | `revision` | **ULTRA** | Ultra-253B | Same skill as drafting (constrained rewrite), same tier — but only for blocker/major sections, max 2 rounds. |
| Title + abstract (finalize) | `formatting` | **NANO** | Nano-8B | Compression of text that already exists. |
| Project chat | `chat` | **NANO** | Nano-8B | Fast grounded Q&A over the project context; streaming SSE. |
| "Tighten to N words" | `formatting` | **NANO** | Nano-8B | Mechanical edit, cheap model. |
| One-click "apply fix" | `revision` | **ULTRA** | Ultra-253B | A targeted rewrite the user explicitly requested. |

Sampling parameters per tier (enforced in `ModelRouter.params_for`, unit-tested):

| Tier | temperature | max_tokens | retries |
|---|---|---|---|
| NANO | 0.0 | 4096 | exponential backoff ×4 on 429/5xx/timeout |
| SUPER | 0.2 | 4096 | same |
| ULTRA | 0.4 | 4096 | same |

## What the router actually does

```python
tier, model = router.route("drafting")          # ("ultra", $NEMOTRON_ULTRA_MODEL)
result = await router.complete("drafting", messages, fixture_key="draft:Statement of Need")
result.tokens_in, result.tokens_out, result.latency_ms, result.estimated_cost_usd
```

Every `complete()` call returns an `LLMCallResult` that the worker writes to
`job_events` — that's the data behind the UI's Model Router panel (per-call
badge, tokens, latency, estimated cost, running total). Tenacity retries only
transient failures (429/5xx/timeouts); 4xx fails fast so a bad key is never
masked by retries.

## Nemotron-specific handling

- **`<think>` blocks.** Nemotron Super/Ultra emit reasoning traces before the
  final answer. `strip_think()` removes them before JSON parsing and before
  drafted Markdown is stored (the trace braces would corrupt JSON extraction).
- **`response_format={"type": "json_object"}`** is requested for all
  structured tasks, but we never trust it blindly: `parse_llm_json` handles
  prose wrappers, code fences, trailing commas, smart quotes and raw control
  characters, with a documented escalation ladder (`repair_json`).
- **Mock mode with a fixture registry.** `MOCK_LLM=true` returns deterministic,
  realistic fixtures per node (`app/agent/fixtures.py`) so the entire product —
  including the demo proposal — runs with zero credits and zero network.

## Cost story (why judges should care)

A full proposal is ~15–25 model calls. With everything on Ultra, a run burns
roughly an order of magnitude more credit than with routing; with routing,
drafting+revision dominate spend *on purpose* because they are the only steps
that produce the artifact. The in-app cost panel makes this auditable per run —
the routing table is not a slide, it's a live chart.

## Tavily (the research half of the loop)

- Pipeline node `run_research` calls `POST https://api.tavily.com/search` with
  `search_depth="advanced"`, `max_results=5`, `include_answer=True`,
  concurrency 4 (`asyncio.Semaphore`).
- The chat agent uses the official `tavily-python` SDK as an on-demand tool.
- **Citation integrity invariant:** findings are stored *only* from results
  Tavily returned (URL-deduped, score-clamped); drafting may cite `[n]`
  exclusively against that numbering; `finalize` builds the reference list from
  the same list. Mock mode labels fixtures with `mock.tavily.local` URLs.

## Nebius Serverless (compute half)

- **Serverless Jobs** run the worker container (`Dockerfile.worker`) per
  proposal: the API submits with `JOB_ID` in the environment; the job writes
  progress to Supabase and exits non-zero on failure. `--poll` mode turns the
  same image into an always-on claim-loop worker if you prefer a long-lived
  container.
- **Serverless Endpoints** host the FastAPI image (`Dockerfile`) when you don't
  want Render/laptop hosting (see `docs/DEPLOYMENT.md`).
