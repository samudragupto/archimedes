"""Supabase data access (service role, server-side only).

Every function here is *synchronous* (supabase-py is a blocking client) and is
called from the async pipeline through ``asyncio.to_thread`` — see
agent/reporter.py. The service-role key bypasses RLS by design: the API and
worker are trusted server components; the browser never sees this key.

Access pattern kept deliberately thin: dict-shaped rows in/out so PostgREST
remains the single source of truth for shape (mirrored by Pydantic models and
apps/web/lib/types.ts).
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from .config import get_settings
from .models.schemas import ComplianceIssue, Requirement, ResearchFinding, Section


class DatabaseNotConfigured(RuntimeError):
    """Raised when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are missing."""


@lru_cache
def _client() -> Any:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise DatabaseNotConfigured(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set. Add them to .env "
            "(Supabase dashboard → Project Settings → API), or use --demo / MOCK_LLM "
            "for an in-memory run."
        )
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _one(res: Any) -> dict | None:
    """maybe_single() returns None (not a response) on zero rows in postgrest>=2.x."""
    return res.data if res is not None else None


# ---------------------------------------------------------------------------
# jobs + job_events
# ---------------------------------------------------------------------------
def get_job(job_id: str) -> dict | None:
    res = _client().table("jobs").select("*").eq("id", job_id).maybe_single().execute()
    return _one(res)


def update_job(job_id: str, **fields) -> None:
    if fields.get("finished_at") == "now":
        fields["finished_at"] = _now()
    if fields.get("progress") is None:
        fields.pop("progress", None)
    if fields.get("error") is None and "error" in fields:
        fields.pop("error")
    fields["updated_at"] = _now()
    _client().table("jobs").update(fields).eq("id", job_id).execute()


def emit_job_event(
    job_id: str,
    level: str,
    step: str | None,
    message: str,
    *,
    model_used: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    latency_ms: int | None = None,
) -> None:
    _client().table("job_events").insert(
        {
            "job_id": job_id,
            "level": level,
            "step": step,
            "message": message,
            "model_used": model_used,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms,
        }
    ).execute()


def claim_next_queued_job() -> dict | None:
    """Atomically claim the oldest queued job.

    The compare-and-swap (update … where status='queued') makes this safe with
    any number of concurrent workers: PostgREST only returns the row for the
    worker that actually flipped the status, so exactly one worker ever runs a
    given job — the property the Nebius Serverless deployment relies on.
    """
    sb = _client()
    queued = (
        sb.table("jobs")
        .select("id")
        .eq("status", "queued")
        .order("created_at")
        .limit(1)
        .execute()
        .data
    )
    if not queued:
        return None
    res = (
        sb.table("jobs")
        .update({"status": "running", "started_at": _now(), "updated_at": _now()})
        .eq("id", queued[0]["id"])
        .eq("status", "queued")  # the CAS guard
        .execute()
    )
    return res.data[0] if res.data else None


# ---------------------------------------------------------------------------
# projects
# ---------------------------------------------------------------------------
def get_project(project_id: str) -> dict | None:
    res = _client().table("projects").select("*").eq("id", project_id).maybe_single().execute()
    return _one(res)


def update_project(project_id: str, **fields) -> None:
    fields["updated_at"] = _now()
    _client().table("projects").update(fields).eq("id", project_id).execute()


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------
def get_document(project_id: str, kind: str) -> dict | None:
    res = (
        _client()
        .table("documents")
        .select("id, kind, filename, source_url, extracted_text, page_count")
        .eq("project_id", project_id)
        .eq("kind", kind)
        .maybe_single()
        .execute()
    )
    return _one(res)


# ---------------------------------------------------------------------------
# requirements — replaced wholesale on each extraction run
# ---------------------------------------------------------------------------
def replace_requirements(project_id: str, requirements: list[Requirement]) -> list[str]:
    sb = _client()
    sb.table("requirements").delete().eq("project_id", project_id).execute()
    if not requirements:
        return []
    rows = [{**r.model_dump(exclude={"id"}), "project_id": project_id} for r in requirements]
    res = sb.table("requirements").insert(rows).execute()
    return [row["id"] for row in (res.data or [])]


# ---------------------------------------------------------------------------
# research findings — appended per run (URL dedupe already applied upstream)
# ---------------------------------------------------------------------------
def insert_findings(project_id: str, findings: list[ResearchFinding]) -> None:
    if not findings:
        return
    rows = [{**f.model_dump(exclude={"id"}), "project_id": project_id} for f in findings]
    _client().table("research_findings").insert(rows).execute()


# ---------------------------------------------------------------------------
# sections — upserted one-by-one so the UI fills in live during drafting
# ---------------------------------------------------------------------------
def upsert_section(project_id: str, section: Section) -> str:
    sb = _client()
    payload = section.model_dump(exclude={"id", "project_id"})
    existing = (
        sb.table("sections")
        .select("id")
        .eq("project_id", project_id)
        .eq("order_index", section.order_index)
        .maybe_single()
        .execute()
    )
    if existing and existing.data:
        section_id = existing.data["id"]
        payload["updated_at"] = _now()
        sb.table("sections").update(payload).eq("id", section_id).execute()
        return section_id
    payload["project_id"] = project_id
    res = sb.table("sections").insert(payload).execute()
    return (res.data or [{}])[0].get("id", "")


# ---------------------------------------------------------------------------
# compliance issues — replaced wholesale per audit round
# ---------------------------------------------------------------------------
def replace_issues(project_id: str, issues: list[ComplianceIssue]) -> None:
    sb = _client()
    sb.table("compliance_issues").delete().eq("project_id", project_id).execute()
    if not issues:
        return
    rows = [{**i.model_dump(exclude={"id"}), "project_id": project_id} for i in issues]
    sb.table("compliance_issues").insert(rows).execute()


# ---------------------------------------------------------------------------
# API-facing queries (routers) — all filtered by the authenticated user
# because the service-role client bypasses RLS by design
# ---------------------------------------------------------------------------
def create_project(user_id: str, title: str, funder_name: str | None = None) -> dict:
    res = (
        _client()
        .table("projects")
        .insert({"user_id": user_id, "title": title, "funder_name": funder_name})
        .execute()
    )
    return (res.data or [{}])[0]


def list_projects(user_id: str) -> list[dict]:
    res = (
        _client()
        .table("projects")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def create_job(project_id: str, kind: str, runtime: str) -> dict:
    res = (
        _client()
        .table("jobs")
        .insert({"project_id": project_id, "kind": kind, "runtime": runtime})
        .execute()
    )
    return (res.data or [{}])[0]


def list_jobs(project_id: str) -> list[dict]:
    res = (
        _client()
        .table("jobs")
        .select("*")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def list_job_events(job_id: str, since: str | None = None, limit: int = 500) -> list[dict]:
    q = _client().table("job_events").select("*").eq("job_id", job_id).order("ts")
    if since:
        q = q.gt("ts", since)
    return (q.limit(limit).execute()).data or []


def list_requirements(project_id: str) -> list[dict]:
    return (
        _client()
        .table("requirements")
        .select("*")
        .eq("project_id", project_id)
        .order("category")
        .execute()
        .data
        or []
    )


def list_sections(project_id: str) -> list[dict]:
    return (
        _client()
        .table("sections")
        .select("*")
        .eq("project_id", project_id)
        .order("order_index")
        .execute()
        .data
        or []
    )


def list_issues(project_id: str) -> list[dict]:
    return (
        _client().table("compliance_issues").select("*").eq("project_id", project_id).execute().data
        or []
    )


def list_findings(project_id: str) -> list[dict]:
    return (
        _client().table("research_findings").select("*").eq("project_id", project_id).execute().data
        or []
    )


def get_section(section_id: str) -> dict | None:
    res = _client().table("sections").select("*").eq("id", section_id).maybe_single().execute()
    return _one(res)


def update_section(section_id: str, **fields) -> dict:
    fields["updated_at"] = _now()
    res = _client().table("sections").update(fields).eq("id", section_id).execute()
    return (res.data or [{}])[0]


def get_issue(issue_id: str) -> dict | None:
    res = (
        _client().table("compliance_issues").select("*").eq("id", issue_id).maybe_single().execute()
    )
    return _one(res)


def update_issue(issue_id: str, **fields) -> dict:
    fields["updated_at"] = _now()
    res = _client().table("compliance_issues").update(fields).eq("id", issue_id).execute()
    return (res.data or [{}])[0]


def upsert_document(project_id: str, kind: str, fields: dict) -> dict:
    """Replace the project's document of this kind (one-per-kind unique index)
    and point the project at the new row."""
    sb = _client()
    sb.table("documents").delete().eq("project_id", project_id).eq("kind", kind).execute()
    res = sb.table("documents").insert({"project_id": project_id, "kind": kind, **fields}).execute()
    row = (res.data or [{}])[0]
    pointer = "solicitation_doc_id" if kind == "solicitation" else "org_doc_id"
    update_project(project_id, **{pointer: row.get("id")})
    return row
