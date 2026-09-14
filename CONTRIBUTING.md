# Contributing to Archimedes

MIT-licensed — issues and PRs welcome. The bar for merging is: **all gates green, no placeholder features, every LLM call still routed through Nebius Token Factory.**

## Development setup

```bash
git clone <your-fork> archimedes && cd archimedes
make setup          # python venv + web deps + .env from .env.example
cp .env .env.local  # (optional) local overrides
```

Useful targets: `make api` · `make worker` · `make web` · `make test` ·
`make lint` · `make format` · `make demo` · `make smoke` · `make seed-demo`.

## The gates (CI parity — run before every push)

```bash
cd services/api
.venv/bin/python -m pytest -q          # 147 tests, offline via MOCK_LLM fixtures
.venv/bin/ruff check app worker tests
.venv/bin/black --check app worker tests
.venv/bin/mypy app worker              # strict-enough; tests excluded by config

cd ../../apps/web
pnpm typecheck                         # tsc --noEmit, strict
pnpm build                             # next build (types must pass)
```

Everything must pass **without network access or API keys** — `MOCK_LLM=true`
fixtures cover the model and Tavily surfaces. If your change needs a new
fixture, add it to `app/agent/fixtures.py`, not a live-call test.

## Architecture rules of the road

1. **All inference through Nebius.** No OpenAI/Anthropic/Google imports, ever.
   Model ids come from env (`NEMOTRON_*_MODEL`) with catalog-confirmed defaults.
2. **No fabricated citations.** Findings only ever come from Tavily responses.
3. **LangGraph owns the loop.** Nodes are pure functions over `ProposalState`;
   routing lives in `TASK_ROUTES` + `route_after_audit`, not in node bodies.
4. **Ownership is 404, not 403.** New endpoints must call `require_project`.
5. **Types end to end.** Pydantic models mirror the SQL schema; keep
   `apps/web/lib/types.ts` in sync when you touch `app/models/schemas.py`.
6. **No dead buttons.** UI elements either work or don't ship.
7. **WHY-comments for judges.** Non-obvious decisions carry a one-line
   rationale where the decision is made.

## Commit style

Conventional-ish, imperative, scope-tagged: `feat(api): …`, `fix(web): …`,
`chore: …`. One logical change per commit; the repo history doubles as the
project log.

## Reporting bugs

Include: which make target, which component (api/worker/web), the relevant
tail of the log (worker logs also land in `tmp/worker-<job>.log`), and whether
`MOCK_LLM` was on. Security issues: see docs/SECURITY.md for scope, then open a
private advisory rather than a public issue.
