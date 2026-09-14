# ARCHIMEDES — Security & Privacy Model

Archimedes handles two sensitive classes of data: **grant documents** (often confidential pre-publication RFPs and org profiles with budgets) and **provider credentials**. The design keeps both locked down with the smallest possible trust boundaries.

## Identity

- Sign-in is Supabase Auth only (magic link or GitHub OAuth). Archimedes never sees or stores passwords.
- The browser presents a short-lived Supabase JWT to the API on every call. The API verifies it with `SUPABASE_JWT_SECRET` (HS256) or Supabase's published JWKS (ES256/RS256, cached client), enforcing:
  - signature + `exp` (30 s leeway for clock skew),
  - required claims `sub` and `aud="authenticated"`,
  - 401 with a specific message for expired vs. invalid tokens.
- There are no API keys, cookies-with-personal-data, or sessions on the FastAPI side — a verified JWT per request is the whole story.

## Authorization

Two independent layers; both must say yes:

1. **Row-Level Security (Postgres).** All 9 tables carry `auth.uid()`-scoped policies (owner-only; child rows scoped through `projects`). Validated during development with role-playback probes (`SET LOCAL role authenticated; SET LOCAL request.jwt.claim.sub = …`).
2. **Application checks.** Every router resolves the requested resource and calls `require_project(project_id, user)` before touching data. A foreign resource is a **404**, not 403 — the API never confirms that someone else's project exists.

The **service role key** (bypasses RLS by design) exists only in two server-side processes — the API and the worker. It never reaches the browser; `NEXT_PUBLIC_*` env vars carry only the anon key, whose powers are exactly what RLS allows.

## Documents & storage

- Uploads land in a **private** Supabase Storage bucket (no public URL can be constructed).
- Object paths are `{user_id}/{project_id}/{kind}/…`, and `storage.objects` policies pin `(storage.foldername(name))[1] = auth.uid()` — users can only touch their own folder even with a direct Storage client.
- Upload cap: 20 MB; server-side parsing (pypdf) — no execution of uploaded content.
- Org profiles pasted as text are stored like any document; nothing is logged at INFO level except step/event metadata (no document bodies, no prompts).

## Secrets & provider boundaries

| Secret | Where it lives | Never in |
|---|---|---|
| `NEBIUS_API_KEY`, `TAVILY_API_KEY` | API + worker env | browser bundles, logs, job_events |
| `SUPABASE_SERVICE_ROLE_KEY` | API + worker env | browser (`NEXT_PUBLIC_*` is anon-only) |
| `SUPABASE_JWT_SECRET` | API env | worker (worker trusts the DB, not callers) |

`job_launcher` passes the worker an **allowlisted** env subset (`JOB_ID`, `MOCK_LLM`, provider keys) — never the whole environment.

## LLM/tool layer

- All inference goes to **Nebius Token Factory** (`NEBIUS_BASE_URL`, default `https://api.studio.nebius.com/v1/`) with NVIDIA Nemotron models; there is no code path to any other provider.
- Web results come **only** from Tavily API responses; findings persist the returned URL/snippet verbatim. The product cannot emit a citation that Tavily did not return, and prompts instruct drafting to cite only numbered findings.
- Prompts instruct extraction to quote source text verbatim (`source_excerpt`) so every extracted rule is provable against the uploaded solicitation.

## Threat model notes (explicit non-goals / known limits)

- The worker executes with service-role DB rights by design (it writes results for the job row); it is triggered only by the API or Nebius Jobs, never by user input directly.
- Rate limiting and per-org quotas are not implemented (single-tenant deployments / hackathon scope); the Supabase and Nebius free tiers are the practical ceiling.
- Prompt-injection from solicitation text is mitigated structurally (extraction is schema-validated JSON; drafting cites numbered findings, not instructions found in text) but not adversarially hardened.
