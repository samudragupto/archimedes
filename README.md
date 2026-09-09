<div align="center">

# 🏛️ ARCHIMEDES

**Win grants, not paperwork.**

An autonomous grant-writing agent for non-profits, university researchers, and
startups. Upload a solicitation and your organization profile — Archimedes
extracts every requirement, researches the web, drafts a complete proposal,
audits it for compliance, and hands you an export-ready document.

Grant writers cost \$100–200/hour. Archimedes costs a few API credits.

*Built for the **Nebius × NVIDIA Global AI Hackathon** — Best Apps & Agents Track.*

`NVIDIA Nemotron on Nebius Token Factory` · `LangGraph` · `Tavily` · `Supabase` ·
`FastAPI` · `Next.js 14` · `Nebius Serverless Jobs`

</div>

---

## How it works

```
solicitation + org profile
        │
        ▼
 extract_requirements ──► plan_research ──► run_research (Tavily)
        (Nano)                (Super)          (advanced search)
                                                     │
 finalize ◄── compliance_audit ◄── draft_sections ◄── outline
 (Nano)          (Super)              (Ultra)        (Super)
     ▲                │
     └── revise ◄─────┘   (only failing sections, max 2 rounds)
       (Ultra)
```

Every LLM call is **routed to the cheapest Nemotron tier that can do the job**
(Nano → Super → Ultra), and every call logs model, tokens, latency, and
estimated cost into a live event stream the UI renders as an agent trace.

## Status

| Phase | Scope | Status |
|------|-----------------------------------------------------------|--------|
| 1 | Repo scaffold, Supabase schema + RLS, Docker, Makefile | ✅ done |
| 2 | Nebius client + ModelRouter, Tavily, document parsing (+ tests) | 🔨 |
| 3 | LangGraph agent pipeline, worker, live job events | 🔨 |
| 4 | FastAPI routers, Supabase auth, MD/DOCX/PDF export | 🔨 |
| 5 | Next.js workspace UI (5 tabs) + Supabase Realtime | 🔨 |
| 6 | Docs, demo seed, smoke tests, README polish | 🔨 |

## Repository map

```
archimedes/
├── apps/web/          Next.js 14 frontend (workspace UI)
├── services/api/      FastAPI + LangGraph agent + worker (shared package)
├── supabase/          SQL migrations (RLS) + seed data
├── docs/              PRD, architecture, Nebius/NVIDIA usage, deployment
└── scripts/           setup, demo seed, smoke test
```

## Quickstart (10 minutes, once all phases land)

```bash
cp .env.example .env        # add Nebius, Tavily, and Supabase keys
make setup                  # python venv + pnpm install
make dev                    # docker compose: api :8000 · web :3000 · worker
make test                   # full agent graph offline via MOCK_LLM=true
```

No credits? Set `MOCK_LLM=true` — every model call returns deterministic
fixtures so the entire product is demonstrable offline.

## License

MIT — see [LICENSE](LICENSE).
