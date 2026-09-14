# ARCHIMEDES — Deployment & Running Guide

Everything below assumes you are in the repository root. Total setup time from
zero: **~10 minutes** (plus one-time Supabase project creation). For local
running instructions see [RUNNING.md](RUNNING.md).

---

## Go-live checklist (in this order — each step verifies the next)

1. [ ] **Supabase provisioned** — `0001_init.sql` run in the SQL editor
      (tables + RLS + realtime + storage bucket). Verify: Table Editor shows
      the 9 tables; Storage shows the private `documents` bucket.
2. [ ] **Auth configured** — Site URL + redirect URLs include your web domain
      (localhost and/or Vercel); GitHub provider filled if used. Verify: the
      magic-link email arrives and lands you on the dashboard.
3. [ ] **Secrets ready** — `NEBIUS_API_KEY`, `TAVILY_API_KEY`,
      `SUPABASE_URL/ANON_KEY/SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` (or the
      JWKS path). Verify: `curl "$API/health?deep=true"` reports both
      providers `ok`.
4. [ ] **Web deployed → Vercel** — root `apps/web`; env:
      `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`,
      `NEXT_PUBLIC_API_URL` (the API's public URL). Verify: landing page loads
      and login redirects back correctly.
5. [ ] **API deployed → Nebius Serverless Endpoint** (or Render blueprint) —
      image `ghcr.io/<owner>/archimedes-api` (release.yml publishes it), port
      `8000`, all server env vars set. Verify: `curl https://<api-host>/health`
      returns `"status":"ok"`.
6. [ ] **Worker → Nebius Serverless Jobs** — image
      `ghcr.io/<owner>/archimedes-worker`, command `python worker/main.py`,
      env per §7, restart never. Then on the API:
      `NEBIUS_SERVERLESS_ENABLED=true`, `NEBIUS_SERVERLESS_JOB_IMAGE=…`,
      `NEBIUS_PROJECT_ID=…`, `LOCAL_WORKER_MODE=false`. Verify: run a project;
      the UI shows runtime `nebius_serverless` and the run completes.
7. [ ] **Demo seeded & end-to-end pass** — `make seed-demo` against the
      production Supabase; sign in on the deployed web, open the demo project,
      run the agent, export a PDF. Verify:
      `services/api/.venv/bin/python scripts/smoke_test.py --live https://<api-host>`
      → `SMOKE PASS`.

---
## 0. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.11+ (3.13 verified) | `python3 --version` |
| pnpm | 8+ | `pnpm --version` (or `npm i -g pnpm`) |
| Docker | with compose v2 | `docker compose version` — *optional* (bare-metal path below) |

Accounts (all free tiers / hackathon credits):
- **Nebius Token Factory** — https://studio.nebius.com → API key
- **Tavily** — https://app.tavily.com → API key (free credits suffice)
- **Supabase** — https://supabase.com → create a project (free tier)

## 1. Get the code + dependencies

```bash
git clone <your-fork> archimedes && cd archimedes
make setup          # creates services/api/.venv, installs python + web deps, copies .env
```

<details><summary>or manually</summary>

```bash
python3 -m venv services/api/.venv
services/api/.venv/bin/pip install -r services/api/requirements.txt -r services/api/requirements-dev.txt
pnpm --dir apps/web install
cp .env.example .env
```
</details>

## 2. Provision Supabase (one-time, ~5 minutes)

1. Open your Supabase project → **SQL Editor** → paste and run
   `supabase/migrations/0001_init.sql` (schema, RLS, realtime, storage bucket).
2. *(optional, demo UI data)* run `supabase/seed.sql` the same way.
3. **Authentication → Providers**: *Email* is on by default (magic link). To
   enable GitHub OAuth: **Auth → Providers → GitHub**, create an OAuth App on
   GitHub with callback `https://<project-ref>.supabase.co/auth/v1/callback`,
   paste client id/secret.
4. **Auth → URL Configuration**: set Site URL to `http://localhost:3000` for
   local dev (and your Vercel URL later).
5. **Project Settings → API**: copy the URL, the `anon` key and the
   `service_role` key into `.env`:

```env
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...          # server-side only
NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
```

> Self-hosted Postgres instead? `DATABASE_URL=postgres://… make migrate` and
> `DATABASE_URL=… make seed-sql` apply the same files with psql.

## 3. Fill the remaining `.env`

```env
NEBIUS_API_KEY=nkey-...                    # studio.nebius.com
NEBIUS_BASE_URL=https://api.studio.nebius.com/v1/
NEMOTRON_NANO_MODEL=nvidia/Llama-3_1-Nemotron-Nano-8B-v1      # confirm ids in the
NEMOTRON_SUPER_MODEL=nvidia/Llama-3_3-Nemotron-Super-49B-v1   # Token Factory catalog
NEMOTRON_ULTRA_MODEL=nvidia/Llama-3_1-Nemotron-Ultra-253B-v1
TAVILY_API_KEY=tvly-...
LOCAL_WORKER_MODE=true                     # API spawns the worker per job (laptop)
MOCK_LLM=false                             # true = deterministic offline mode
```

No credits at all? Set `MOCK_LLM=true` — every model call and Tavily search
returns deterministic fixtures. Everything works; citations point at
`mock.tavily.local`.

## 4. Run it

### Option A — Docker (one command)

```bash
make dev            # api :8000 · worker · web :3000  (hot reload)
```

### Option B — Bare metal (three terminals)

```bash
make api            # FastAPI with reload  → http://localhost:8000  (docs at /docs)
make worker         # local worker: --poll claim loop (claims jobs from any producer)
make web            # Next.js dev server   → http://localhost:3000
```

> With `LOCAL_WORKER_MODE=true` you don't even need `make worker`: the API
> spawns a worker subprocess per job. Use `make worker` when you want a
> separate always-on claim loop (that's what compose runs).

### First check

```bash
curl -s localhost:8000/health | python3 -m json.tool
# → nebius/tavily key validity, configured model ids, mock flag, worker mode
make smoke          # 9-check offline smoke (fixtures, exporter, auth); add --live <url> to probe a running stack
```

## 5. The 60-second demo (no UI needed)

```bash
make demo           # = python worker/main.py --demo
```

Runs the full agent pipeline on the bundled CRPG-2026 mock solicitation with a
live terminal trace (tier badges, tokens, progress bar) and prints a summary.
Add `--live` to run the same fixture against real Nebius + Tavily keys.

## 6. Tests & lint (offline, no credits)

```bash
make test           # pytest — unit + full-graph integration (MOCK_LLM fixtures)
make lint           # ruff · black --check · mypy · eslint
make format         # black + ruff --fix + prettier
```

## 7. Deploying

### CI/CD (GitHub Actions, included)

| Workflow | Trigger | What it does |
|---|---|---|
| **ci.yml** | every PR / push to `main` | The exact repo gates, no secrets needed: ruff + black + mypy + 147 offline pytest + `scripts/smoke_test.py` (API job) and `tsc --noEmit` + `next build` (web job). |
| **release.yml** | push to `main`, tags `v*` | Builds and publishes `ghcr.io/<owner>/archimedes-api` and `ghcr.io/<owner>/archimedes-worker` (tags: branch, tag, `sha-<short>`, `latest`), then boots the pushed API image and asserts `GET /health` answers `ok`. |
| **dependabot.yml** | weekly | pip / npm / docker / actions version bumps. |

Badges: the README carries the CI badge; the release images appear under your
repo's **Packages** once `main` has built once. Everything below can use the
published images instead of building locally — substitute
`ghcr.io/<owner>/archimedes-<api|worker>:latest` for the `docker build`/push
commands.

### Frontend → Vercel

1. Import the repo; **Root Directory**: `apps/web`; framework auto-detects Next.js.
2. Env vars: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`,
   `NEXT_PUBLIC_API_URL` (your FastAPI URL).
3. Deploy. Add the Vercel domain to Supabase **Auth → URL Configuration**
   (Site URL + redirect list) so magic links/OAuth land correctly.

### API → your choice of three

| Target | How |
|---|---|
| **Nebius Serverless Endpoint** (preferred for the hackathon) | Use the published `ghcr.io/<owner>/archimedes-api:latest` (or `docker build -f services/api/Dockerfile -t archimedes-api .` → push) → create an Endpoint from the image, port `8000`, set the env vars from `.env` (service-role key included) → point `NEXT_PUBLIC_API_URL` at the endpoint URL. |
| **Render.com** (documented fallback) | One click: New → **Blueprint** → pick the repo (the bundled `render.yaml` sets the Docker build, `/health` health check and env slots). Or manually: New → Web Service → Docker → root `services/api` → health check `/health` → same env vars. Free instance sleeps; first request warms it. |
| **Any container host** | The image listens on `$PORT`-agnostic `8000`; set env, done. |

### Worker → Nebius Serverless Jobs

```bash
# build & push yourself…
docker build -f services/api/Dockerfile.worker -t archimedes-worker services/api
# …or skip the build: release.yml already publishes ghcr.io/<owner>/archimedes-worker
# create a Job in the Nebius console:
#   image: <registry>/archimedes-worker   (GHCR needs a registry secret for the private pull)
#   command: python worker/main.py            (JOB_ID injected per run by the API)
#   env: NEBIUS_*, SUPABASE_* (service role), TAVILY_API_KEY, MOCK_LLM
#   restart: never · timeout: 30 min
```

Then in the API env set:

```env
NEBIUS_SERVERLESS_ENABLED=true
NEBIUS_SERVERLESS_JOB_IMAGE=<registry>/archimedes-worker:latest
NEBIUS_PROJECT_ID=<your-nebius-project-id>
LOCAL_WORKER_MODE=false
```

`POST /projects/{id}/run` now submits a Nebius Job and the UI shows
“Running on Nebius Serverless Job”. Leave `NEBIUS_SERVERLESS_ENABLED=false`
for the local-subprocess fallback — identical code path either way.

### Verifying a deployed stack

```bash
curl -s https://<api-host>/health
services/api/.venv/bin/python scripts/smoke_test.py --live https://<api-host>
#   validates /health?deep=true (both provider keys) and 401-on-anonymous against the deployed API
```

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `/health` says `nebius_key: missing` | `.env` not loaded — run from repo root, or set vars in the host console |
| 401 from Token Factory | wrong key, or model id not enabled for your account — confirm ids in the catalog |
| Job stuck `queued` | no worker running: start `make worker`, or set `LOCAL_WORKER_MODE=true` |
| Realtime events not arriving | run `0001_init.sql` (it adds tables to the publication); check the browser allows WSS to your Supabase host |
| `DatabaseNotConfigured` in the worker | `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` missing in the *worker's* env |
| Magic link redirects to localhost | set Auth Site URL to the domain you're actually browsing |
| Everything else | `MOCK_LLM=true` isolates model/network issues from app issues |

## 9. Repo conventions

- Python: `ruff` + `black` (line 100) + `mypy` (lenient profile), tests offline
  by design (`tests/conftest.py` pins `MOCK_LLM=true`).
- SQL: single migration `0001_init.sql` + optional `seed.sql` (idempotent,
  fixed UUIDs).
- Commits: one phase/topic per commit; `make lint && make test` before pushing.
