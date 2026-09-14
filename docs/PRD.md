# ARCHIMEDES — Product Requirements Document

**Product:** Archimedes — autonomous grant-writing agent
**Track:** Nebius × NVIDIA Global AI Hackathon — Best Apps and Agents Track
**Status:** implemented as described (see README for run instructions)
**License:** MIT

---

## 1. Problem

Grant writing is the gatekeeping tax on civil society. A competitive federal or
foundation proposal takes 40–120 hours of skilled work; professional grant
writers charge **$100–200/hour**. The organizations that most need the money —
small non-profits, first-time PIs, early-stage research teams — are precisely
the ones that cannot afford that, so they either write grants at midnight after
their real jobs or they don't apply at all.

Meanwhile the documents themselves are compliance exercises: solicitations are
dense, page limits are hard gates, and review panels score against explicit
criteria. This is exactly the shape of problem LLM agents are good at:
**structured extraction → evidence gathering → long-form drafting under
constraints → adversarial self-review.**

## 2. Target user

| Persona | Context | Pain |
|---|---|---|
| **Small non-profit program director** (primary) | 1–10 FTE org, no development staff, applies to 2–5 grants/year | Doesn't know the unwritten rules; loses grants to avoidable compliance errors |
| **University researcher / first-time PI** | Lab of 2–10 people, needs seed funding | Time is research time; each failed proposal costs a quarter |
| **Early-stage startup founder** | Applying for non-dilutive funding (SBIR-style) | Same compliance maze, zero grant experience |

Non-goals: we do not replace grant *strategy* (which funder, which program) or
submit on the user's behalf. Archimedes produces a submission-ready draft with
a provable compliance trail; the human stays the author of record.

## 3. Product definition

Upload (a) a grant solicitation (PDF or URL) and (b) an organization profile
(PDF or pasted text). Archimedes then runs an autonomous pipeline:

1. **Extract requirements** — deadline, budget cap, eligibility, required
   sections with page limits, formatting rules, evaluation criteria. Every
   requirement carries its verbatim source quote and a confidence score.
2. **Research the web** (Tavily) — hazard/demographic statistics, prior funded
   projects, regulatory facts — each query planned against a target section.
3. **Draft the full proposal** — every required section, sized to the page
   limits, with inline citations `[n]` that resolve to real fetched sources.
4. **Audit compliance** — the draft is scored against every mandatory
   requirement (`100 − blockers·25 − majors·10 − minors·3`), issues get
   severities and concrete fixes, and blocking sections are **rewritten
   automatically** (max 2 rounds).
5. **Deliver** — a live-editable draft (Markdown), exportable to DOCX and PDF
   with a cover page, plus a chat agent that answers questions about the
   project using only grounded context.

The user watches the whole thing run live: a terminal-style agent trace with a
badge per call showing which Nemotron model handled it, tokens, latency, and
estimated cost.

## 4. Why an agent (and not a chatbot)

A chatbot produces one lucky draft. A grant is a *constraint-satisfaction*
problem: the value is in (a) not missing a requirement, (b) evidence with real
citations, (c) iterating until the draft passes its own audit. That requires
state, tools, and a control loop — i.e., an agent. The LangGraph state machine
makes the loop inspectable: each node is a pure function, routing is one
function, and every model call is metered to the UI.

## 5. Functional requirements

| ID | Requirement | Where |
|---|---|---|
| F1 | Upload solicitation (PDF/TXT/MD) or ingest URL; parse to clean chunked text | `POST /projects/{id}/documents`, `services/document_parser.py` |
| F2 | Upload org profile (file or pasted text) | same endpoint, `kind=organization` |
| F3 | Extract structured requirements w/ source quotes, categories, confidence | `nodes/extract_requirements.py` |
| F4 | Plan 4–8 targeted web searches w/ rationale | `nodes/plan_research.py` |
| F5 | Execute searches (advanced depth, concurrency 4); store findings w/ URLs | `nodes/run_research.py` |
| F6 | Outline covering every mandatory section; word budgets from page limits | `nodes/outline.py` |
| F7 | Draft each section (ULTRA) with inline `[n]` citations from findings only | `nodes/draft_sections.py` |
| F8 | Compliance audit w/ severity, requirement linkage, suggested fix, score | `nodes/compliance_audit.py` |
| F9 | Auto-revise sections with blocker/major issues; ≤ 2 rounds | `nodes/revise.py` + graph edge |
| F10 | Finalize: title, 150-word abstract, TOC, references | `nodes/finalize.py` |
| F11 | Live progress: job row + event stream over Supabase Realtime; polling fallback | `jobs`, `job_events`, reporter |
| F12 | Model-router panel: per-call model, tokens in/out, latency, est. cost | `LLMCallResult` → `job_events` |
| F13 | Edit any section (rich text); regenerate (ULTRA) / tighten (NANO) | Draft tab (Phase 5) |
| F14 | One-click apply-fix per compliance issue (ULTRA rewrite) | `POST /compliance-issues/{id}/fix` |
| F15 | Export MD / DOCX / PDF (serif, cover page) | `/export` + `services/exporter.py` |
| F16 | Project chat (NANO, SSE) grounded in requirements + sections; Tavily as tool | `/projects/{id}/chat` |
| F17 | Demo in one click: bundled mock solicitation + non-profit, runnable offline | `worker/main.py --demo`, seed.sql, demo button |
| F18 | Run with zero credits: `MOCK_LLM=true` full-fidelity fixtures | end-to-end |

## 6. Non-functional requirements

- **Cost discipline:** model routing (Nano/Super/Ultra) with per-call cost
  telemetry; a full run should cost single-digit cents of Token Factory credit.
- **Honesty:** citations only from Tavily results; requirement quotes verbatim;
  mock data unmistakably labeled (`mock.tavily.local`, `MOCK_LLM`).
- **Security:** Supabase RLS on every table; per-user storage folders;
  service-role key server-side only.
- **Runnability:** 10-minute setup on a laptop; docker compose one-command
  stack; tests run fully offline (`make test`).
- **Openness:** MIT license, no proprietary assets (logo is our own SVG).

## 7. Success metrics (for judges to poke)

- Time from "upload" to "complete draft with audit" — target < 5 minutes live,
  < 15 seconds in mock mode.
- Requirement coverage: 100% of mandatory `section` requirements appear in the
  outline (enforced by the coverage guard, unit-tested).
- Compliance score improvement after auto-revision, shown per run.
- Cost per run visible in the UI (sum of `estimated_cost_usd` on events).

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Model returns malformed JSON | `repair_json` escalation + `parse_llm_json`; per-node fallbacks (standard outline, single audit warning) |
| Tavily query fails / returns junk | Per-query try/except with warn events; drafting proceeds citation-free |
| Extraction misses a requirement | Overlapping chunks; dedupe keeps best-confidence; audit re-checks coverage against the draft |
| Audit over-flags (wasted revisions) | Severity calibrated in prompt; revise only blocker/major; hard 2-round cap |
| Solo-run cost blowup | Tiered routing + max_tokens caps + revision budget |
| Judge has no API credits | `MOCK_LLM=true` full pipeline, `--demo` CLI, SQL seed for the UI |
