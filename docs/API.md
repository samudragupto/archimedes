# ARCHIMEDES — API Reference

Base URL: `{NEXT_PUBLIC_API_URL}/api/v1` · Interactive schema: `GET /openapi.json` (Swagger UI at `/docs`).

**Authentication.** Every route except `GET /health` requires `Authorization: Bearer <Supabase access token>`. The API verifies the JWT against `SUPABASE_JWT_SECRET` (HS256) or Supabase's JWKS endpoint (ES256/RS256), requiring `exp` + `sub` and audience `authenticated`. Ownership is enforced per request: touching another user's project, section, issue, or job answers **404** (never 403 — existence is not disclosed).

**Errors** are `{"detail": "human-readable message"}`. Notable codes: 401 unauthenticated · 403/404 ownership · 400 malformed request · 409 export with no drafted sections · 413 file > 20 MB · 422 unparseable document · 502 upstream failure (storage, Nebius Jobs) · 503 database/auth not configured or provider keys invalid on deep health.

---

## Projects

### `POST /projects` → 201
```bash
curl -X POST $API/api/v1/projects \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title": "Flood-Sensor Network", "funder_name": "Community Resilience Fund"}'
```
Returns the project row (owner stamped from the token's `sub`).

### `GET /projects` → 200
List of the caller's projects, newest first. `[Project]`.

### `GET /projects/{project_id}` → 200
The aggregate payload the workspace binds to — one round trip:
```json
{
  "id": "…", "title": "…", "status": "complete", "compliance_score": 84, "abstract": "…",
  "requirements": [ … ], "sections": [ … ], "compliance_issues": [ … ],
  "research_findings": [ … ], "jobs": [ … ]
}
```
Foreign project → 404.

### `GET /projects/{project_id}/requirements-digest` → 200
Condensed rule sheet for prompts and the Requirements headline cards:
`{deadline, budget, page_limit, eligibility[], sections[{title, requirements[]}], total_requirements}`.

## Documents

### `POST /projects/{project_id}/documents` → 201 (multipart)
Fields: `kind` (`solicitation` | `organization`) + `file` (PDF/TXT/MD, ≤ 20 MB).
The document is parsed **immediately** (the wizard shows the extracted-text preview on the next screen), the raw file goes to the private storage bucket at `{user_id}/{project_id}/{kind}/…`, and any previous document of the same kind is replaced.
Response: `{document, preview (first 1500 chars), total_chars, chunks}`.
Errors: 400 missing/empty file or `kind=supporting` · 413 too large · 422 no extractable text (scanned PDFs) · 502 storage failure.

### `POST /projects/{project_id}/documents/url` → 201
```json
{ "source_url": "https://funder.example.org/rfp.pdf", "kind": "solicitation" }
```
Same parse/persist path, fetching from the URL (422 if the fetch or parse fails).

## Jobs (the agent run)

### `POST /projects/{project_id}/run` → **202**
```json
{ "job_id": "…", "runtime": "local", "detail": "job accepted; watch GET /jobs/{job_id}/events" }
```
`runtime` is `local` (worker subprocess; `LOCAL_WORKER_MODE=true`) or `nebius_serverless` (submitted to Nebius Serverless Jobs). Launch failure → job row marked `failed` + **502**. Re-running a project is safe: the pipeline replaces requirements/issues/sections wholesale.

### `GET /jobs/{job_id}` → 200
`{status: queued|running|succeeded|failed, progress: 0–100, current_step, error, runtime, …}` — the progress bar's data source.

### `GET /jobs/{job_id}/events?since=<iso8601>&limit=500` → 200
The live console feed (newest last). Each event:
```json
{ "id": "…", "level": "model", "step": "draft_sections",
  "message": "Drafted \"Statement of Need\" — 214 words, 3 inline citations",
  "model_used": "nvidia/Llama-3_1-Nemotron-Ultra-253B-v1",
  "tokens_in": 3890, "tokens_out": 1150, "latency_ms": 21344, "ts": "…" }
```
The UI polls this (2.5 s while active) and additionally refetches on Supabase Realtime events.

## Sections (the live editor)

### `PATCH /sections/{section_id}` → 200
```json
{ "content_md": "## Budget\n\n…" }
```
Returns the updated section. This is the Draft tab's **Save** button.

## Compliance

### `POST /compliance-issues/{issue_id}/fix` → 200
One-click fix: Nemotron **Ultra** rewrites the issue's section against the specific rule. Marks the section `done` and the issue `resolved`; records the model used.
Response: `{issue, section, model_used, tokens_out}`.
Errors: 404 unknown/foreign · 400 issue has no linked section (draft-wide) or is already resolved.

## Chat (writing assistant)

### `POST /projects/{project_id}/chat` → 200 `text/event-stream`
```bash
curl -N -X POST $API/api/v1/projects/$PID/chat \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message": "What are the hard deadlines?"}'
```
Frame sequence (SSE, `data:` lines):
```
data: {"delta": "Propos"}
data: {"delta": "als are due"}
…                                        ← Nemotron tokens stream
data: {"needs_web": true}                ← only when a Tavily round ran
data: {"done": true, "model": "nvidia/…", "tokens_in": 940, "tokens_out": 312, "latency_ms": 2103}
data: [DONE]
```
Flow: **Nano** classifies `needs_web` → if true, one Tavily `advanced` search; findings are labeled `[W1]…` in the context → **Super** streams the grounded answer. Answers cite requirements, findings (`[n]`), and draft sections from the project itself.

## Export

### `GET /projects/{project_id}/export?format=md|docx|pdf` → 200 (file)
Composes the final markdown (title, abstract, table of contents, drafted sections in outline order, references) and renders it:
- `md` — `text/markdown; charset=utf-8`
- `docx` — real headings/bold/italic/lists/links via python-docx
- `pdf` — cover page + serif body via reportlab (markup-escaped)

`Content-Disposition: attachment; filename="<slug>.<fmt>"`. **409** if no section has been drafted yet.

## Health

### `GET /health` (also at `/api/v1/health`) → 200
```json
{ "status": "ok", "version": "…", "mock_llm": false, "worker": {"local_worker_mode": true, "nebius_serverless_enabled": false},
  "models": {"nano": "nvidia/…", "super": "nvidia/…", "ultra": "nvidia/…"},
  "keys": {"nebius": true, "tavily": false} }
```
Container/liveness probe — always fast, no external calls.

### `GET /health?deep=true` → 200
Additionally validates both provider keys with one cheap live call each (Nebius `GET /models`, Tavily `POST /search`), cached 60 s. Per-provider: `{ok: true}` or `{ok: false, error}`; `{"skipped": "MOCK_LLM"}` in offline mode. Returns **503** only if the response itself fails.
