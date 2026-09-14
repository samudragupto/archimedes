# ARCHIMEDES — Running Guide (complete, every path)

Every way to run the product, from a zero-credit terminal tour to the full
three-process stack. Deployment to cloud hosts is covered separately in
[DEPLOYMENT.md](DEPLOYMENT.md); this page is about running it yourself.
**On Windows?** Jump to [§7 — Running on Windows](#7--running-on-windows-wsl2-or-native).

---

## 0. What you need

| Tool | Needed for | Check |
|---|---|---|
| Python **3.11+** (3.13 verified) | API + worker + scripts | `python3 --version` |
| Node.js **18+** (20 verified) + npm | web UI | `node --version` |
| pnpm (optional) | faster web installs — npm works everywhere | `pnpm --version` |
| Docker + compose v2 (optional) | one-command full stack | `docker compose version` |

Accounts (only for the full product, not for the offline tour):

- **Nebius Token Factory** — https://studio.nebius.com → **API key** (all LLM calls)
- **Tavily** — https://app.tavily.com → **API key** (live web research; free credits suffice)
- **Supabase** — https://supabase.com → create a project (free tier: database, auth, storage, realtime)

## 1 · Offline tour — zero accounts, zero credits (~2 minutes)

```bash
git clone <your-fork> archimedes && cd archimedes
make setup                # python venv + web deps + .env from .env.example
make demo                 # full agent pipeline in your terminal (fixtures)
make test                 # 147 offline tests
make smoke                # 9-check smoke test -> SMOKE PASS
```

`make demo` prints the entire agent trace: extraction with Nemotron Nano,
research planning with Super, Tavily calls, Ultra drafting, the compliance
audit (score 84/100), a revision round, and finalize. `MOCK_LLM` fixtures make
it deterministic — nothing leaves your machine.

## 2 · Full local stack (the real product, ~10 minutes)

### 2.1 Provision Supabase (one-time)

1. Create a project at supabase.com (free tier).
2. **SQL Editor** → paste `supabase/migrations/0001_init.sql` → **Run**.
   This creates the 9 tables, row-level-security policies, realtime
   publications, and the private `documents` storage bucket.
3. (Optional demo data) **SQL Editor** → run `supabase/seed.sql`.
4. **Authentication → Providers**: Email (magic link) is on by default. For
   GitHub login: create an OAuth App on GitHub (callback
   `https://<project-ref>.supabase.co/auth/v1/callback`), paste the client
   id/secret into the GitHub provider.
5. **Authentication → URL Configuration**: Site URL `http://localhost:3000`,
   redirect URLs `http://localhost:3000/**`.
6. **Project Settings → API**: copy the **Project URL**, the **anon** key, the
   **service_role** key, and (if shown) the **JWT secret**.

### 2.2 Configure `.env`

`make setup` already copied `.env.example` → `.env`. Fill:

```env
NEBIUS_API_KEY=nvapi-...                      # studio.nebius.com
TAVILY_API_KEY=tvly-...                       # app.tavily.com
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=eyJ...                      # anon (public) key
SUPABASE_SERVICE_ROLE_KEY=eyJ...              # service role — server-side only
SUPABASE_JWT_SECRET=<JWT secret>              # or leave empty to use JWKS
# browser-facing values:
NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Everything else has working defaults (worker mode, model ids, tuning knobs —
all documented in `.env.example`).

### 2.3 Run the three processes

```bash
make api        # FastAPI on http://localhost:8000  (Swagger docs at /docs)
make worker     # polling worker (claims queued jobs) — even with a polling
                # worker, keep LOCAL_WORKER_MODE=true on a laptop so jobs run
                # without it; either path works alone, both never double-run
make web        # Next.js on http://localhost:3000
```

Or everything at once with Docker:

```bash
make dev        # docker compose: api :8000 · worker · web :3000
```

### 2.4 Sign in and write your first proposal

1. Open **http://localhost:3000** → sign in (magic link to your email, or GitHub).
2. **New proposal** → upload a solicitation PDF (or paste a URL) → describe
   your organization → name the project → **Create**.
3. The **Requirements** tab fills immediately (server-side extraction).
4. **Agent Run** tab → **Run agent** → watch the live console: every model
   call with its tier badge and token cost.
5. **Draft** tab: edit any section, **Save**; ask the writing assistant
   questions (it runs live Tavily rounds when needed).
6. **Compliance** tab: scored report; **Apply fix** rewrites a section with
   Nemotron Ultra in one click.
7. **Export** tab: preview the exact markdown, download **.md / .docx / .pdf**.

Want a ready-made proposal without uploading anything? Press **Try the demo
project** on the dashboard — or seed one from the CLI with `make seed-demo`
(offline fixtures; `--live` spends credits for a real run:
`services/api/.venv/bin/python scripts/demo_seed.py --live`).

## 3 · Live vs. offline mode

| `MOCK_LLM` in `.env` | Behavior |
|---|---|
| `false` (default) | Real Nebius + Tavily calls. A full proposal costs a few cents of Nebius credit across ~15–25 model calls. |
| `true` | Deterministic fixtures everywhere — UI, tests, demo all run with zero credits and zero network. Mock citations use `mock.tavily.local` so they can never be mistaken for real research. |

Flip it any time; restart the processes after editing `.env`.

## 4 · Verifying a running stack

```bash
curl localhost:8000/health                 # fast config snapshot
curl "localhost:8000/health?deep=true"     # validates Nebius + Tavily keys live (60s cache)
make smoke                                 # offline suite must stay green
services/api/.venv/bin/python scripts/smoke_test.py --live http://localhost:8000
```

The worker logs each job to `tmp/worker-<job-id>.log` as well as to the
database (the Agent Run console reads the database, so history survives
restarts).

## 5 · Troubleshooting

| Symptom | Cause & fix |
|---|---|
| `401` from the UI on every action | Token verification misconfigured: set `SUPABASE_JWT_SECRET` (project's JWT secret, **not** the anon key) — or leave it empty and the JWKS path uses `SUPABASE_URL` alone. |
| `503 … SUPABASE_URL / SERVICE_ROLE are not set` | `.env` missing/incomplete — the API answers with this message on purpose instead of a stack trace. |
| Magic link never arrives | Supabase **Authentication → Email**; the free tier's built-in SMTP is rate-limited. Check **Authentication → Users** for the created user. |
| Login works but the project list errors | `supabase/migrations/0001_init.sql` was not run — RLS policies ship with the schema, not the code. |
| Run button → `502` | Job launch failed: read the API log; in serverless mode check `NEBIUS_SERVERLESS_JOB_IMAGE` and `NEBIUS_PROJECT_ID`. |
| Progress stuck at 0% | No worker: start `make worker` (compose path) or keep `LOCAL_WORKER_MODE=true` so the API spawns workers itself. |
| Tabs update slowly / not at all | Realtime free-tier frames can drop — the UI also polls every 4 s during runs; ensure the realtime publication exists (the migration creates it). |
| PDF export shows odd glyphs | By design it cannot: non-WinAnsi characters (emoji, arrows) are mapped to ASCII or stripped at export time. |
| `make web` / pnpm problems | The Makefile falls back to npm automatically; manually: `cd apps/web && npm install && npm run dev`. |

## 6 · Command reference

| Command | What it does |
|---|---|
| `make setup` | venv + web deps + `.env` (idempotent) |
| `make dev` / `make up` / `make down` / `make logs` | docker compose lifecycle |
| `make api` / `make worker` / `make web` | bare-metal processes with hot reload |
| `make demo` | offline agent pipeline trace in the terminal |
| `make test` | 147 offline pytest |
| `make lint` / `make format` | ruff + black + mypy + web typecheck (or fix mode) |
| `make smoke` | 9-check smoke test (`scripts/smoke_test.py --live <url>` for deployed stacks) |
| `make migrate` / `make seed-sql` | apply the schema migration / demo seed SQL |
| `make seed-demo` | create the demo project through the real pipeline (needs Supabase) |
| `make build-images` | build the api + worker container images |

---

## 7 · Running on Windows (WSL2 or native)

Both paths work. **WSL2 is the recommended one** — you get the exact
`make`-driven flow the rest of this guide describes, and the local-worker
spawn was tested against POSIX semantics first. Native PowerShell works too
(the job launcher auto-detects Windows and detaches worker processes
appropriately), but `make` isn't available, so you run the commands directly.

### Option A — WSL2 (recommended)

One-time setup — in an **Administrator** PowerShell:

```powershell
wsl --install          # installs WSL2 + Ubuntu; reboot when asked
```

Then open Ubuntu (Start menu) and set up the toolchain:

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git build-essential
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
# optional, for `make dev`: install Docker Desktop on Windows and enable
# Settings -> Resources -> WSL Integration for this distro
```

Clone into the **Linux filesystem** (not `/mnt/c/...` — file I/O there is
~10x slower and venvs misbehave):

```bash
cd ~
git clone <your-fork> archimedes && cd archimedes
git config core.autocrlf input   # keep LF line endings inside WSL
make setup && make demo          # then continue with §2 for the full stack
```

Everything else is identical to the Linux flow: `make api`, `make worker`,
`make web`, `make smoke`, `make seed-demo`. Open the UI from your Windows
browser at **http://localhost:3000** — WSL2 forwards localhost automatically.

Tips:

- Edit `.env` from Windows: the repo is at `\\wsl$\Ubuntu\home\<you>\archimedes`,
  or just run `code .` inside WSL (VS Code + WSL extension).
- Keep the venv, node_modules and repo inside WSL's own filesystem.
- If `localhost:3000` doesn't respond after a Windows reboot, restart the
  distro: `wsl --shutdown`, then reopen Ubuntu.

### Option B — native PowerShell (no WSL)

Prerequisites: **Python 3.11+** from python.org (tick "Add python.exe to
PATH") and **Node.js 18+** from nodejs.org. `git` from git-scm.com.

```powershell
git clone <your-fork> archimedes; cd archimedes
Copy-Item .env.example .env        # then fill your keys (see §2.2)

# Python deps
python -m venv services\api\.venv
services\api\.venv\Scripts\python -m pip install -r services\api\requirements.txt -r services\api\requirements-dev.txt

# Web deps
cd apps\web; npm install; cd ..\..
```

Run each process in its own terminal (activate the venv first for API/worker;
if script execution is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`):

```powershell
# terminal 1 — API (http://localhost:8000, docs at /docs)
cd services\api
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000

# terminal 2 — worker (optional; with LOCAL_WORKER_MODE=true the API also
# spawns workers itself — this is fully supported on Windows)
cd services\api
.\.venv\Scripts\Activate.ps1
python worker\main.py --poll

# terminal 3 — web (http://localhost:3000)
cd apps\web
npm run dev
```

Equivalent verification commands (no `make` on Windows):

```powershell
services\api\.venv\Scripts\python -m pytest services\api\tests -q      # 148 offline tests
$env:MOCK_LLM="true"; services\api\.venv\Scripts\python scripts\smoke_test.py
services\api\.venv\Scripts\python worker\main.py --demo               # offline pipeline tour
```

Or skip processes entirely and use the containers (Docker Desktop with WSL2
backend): `docker compose up --build` — no `make` needed, same `docker-compose.yml`.
