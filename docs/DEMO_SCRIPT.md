# ARCHIMEDES — 5-Minute Judge Walkthrough

Everything below runs **offline** (fixtures, no credits) by default; flip `MOCK_LLM=false` in `.env` with real keys for a live run. Total: one terminal, one browser.

## 0 · Setup (before the judges arrive)

```bash
make setup                       # venv + web deps + .env
make migrate && make seed-sql    # schema (only needed once per Supabase project)
make seed-demo                   # offline demo project under demo@archimedes.dev
make api &                       # terminal 1 — FastAPI on :8000
make worker &                    # terminal 2 — polling worker (compose path)
make web &                       # terminal 3 — Next.js on :3000
make smoke                       # green bar: 9/9 checks
```

No Supabase project handy? `make demo` still shows the full pipeline trace in
the terminal, and every pytest (`make test`, 147 tests) runs offline.

## 1 · Landing (30 s)

`http://localhost:3000` — **"Win grants, not paperwork."** Point out the
framing: grant writers cost $100–200/hour; small non-profits compete without
them. Note the model-tier badges — every AI action in the product names the
exact Nemotron model that did it. Sign in with the demo login
(`demo@archimedes.dev` / `archimedes-demo`) via the magic link.

## 2 · Wizard (45 s)

**New proposal** → drop `services/api/app/agent/fixtures/` solicitation or
paste a URL → one-paragraph org profile → name it → **Create project**.
The API parses the PDF immediately; the workspace opens with the extracted
requirement sheet already filling in.

## 3 · Agent Run — the centerpiece (90 s)

Press **Run agent**. The live console streams every step with its model badge
and token cost:

- `extract_requirements` — **Nano** (green): cheap, structured extraction;
  hover any row in Requirements to see the verbatim source quote.
- `plan_research` / `run_research` — **Super** (blue) plans, **Tavily**
  (orange) executes live web searches; findings keep real URLs.
- `outline` — **Super** with a coverage guard against the extracted rules.
- `draft_sections` — **Ultra** (purple): 85% of tokens, hence the router.
- `compliance_audit` — **Super**: scored report (100 − 25·blocker − 10·major − 3·minor).
- `revise` — only if blockers/majors remain (max 2 rounds), then **Nano** finalizes.

**Why this wins the technical criterion:** one `TASK_ROUTES` table decides all
of this; the graph is 8 pure nodes over a typed state; the run executes on
Nebius Serverless Jobs (or a local subprocess — same code path), with progress
streamed through Supabase Realtime.

## 4 · Draft + assistant (45 s)

**Draft tab:** sections carry their model badge; edit a sentence, **Save**
(PATCH). Open the **writing assistant**: ask *"What are the hard deadlines?"* —
Nano answers from project context; ask something external and it runs a live
Tavily round first, answering with `[W1]`-style citations.

## 5 · Compliance one-click fixes (45 s)

**Compliance tab:** score ring + severity-sorted issues. Press **Apply fix**
on one — Ultra rewrites that section against the specific rule, the issue
flips to *resolved*, the Draft tab already shows the new text. This is the
"scored report with one-click fixes" loop, end to end.

## 6 · Export (30 s)

**Export tab:** the exact markdown source in preview, then download **.docx**
and **.pdf** — cover page, contents, sections, references. A submission-ready
document that would have cost $5–10k at human rates.

## If asked for the SRE view

- `GET /health?deep=true` validates both provider keys live (60 s cache).
- `docker compose up` runs the whole stack; `NEBIUS_SERVERLESS_ENABLED=true`
  swaps local subprocess execution for Nebius Serverless Jobs with zero code
  changes (`job_launcher.py` is the only switch).
- `make smoke` (offline, 9 checks) and `--live` mode prove deployment health.
