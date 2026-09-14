"""Shared Pydantic v2 schemas — the single source of truth for everything that
crosses a process boundary (API → worker → Postgres → browser).

Field names and enums mirror the Supabase schema 1:1 (supabase/migrations/
0001_init.sql). The TypeScript mirror in apps/web/lib/types.ts is kept
field-for-field compatible; if you change a model here, change it there too.

This module also hosts the pure, unit-tested data utilities that operate on
those models (requirement dedupe, token estimation) so the agent nodes stay
thin orchestration code.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums — mirror the Postgres enum types exactly
# ---------------------------------------------------------------------------
class ProjectStatus(StrEnum):
    draft = "draft"
    extracting = "extracting"
    researching = "researching"
    drafting = "drafting"
    auditing = "auditing"
    revising = "revising"
    complete = "complete"
    failed = "failed"


class DocumentKind(StrEnum):
    solicitation = "solicitation"
    organization = "organization"
    supporting = "supporting"


class RequirementCategory(StrEnum):
    deadline = "deadline"
    budget = "budget"
    eligibility = "eligibility"
    section = "section"
    format = "format"
    evaluation = "evaluation"
    other = "other"


class SectionStatus(StrEnum):
    pending = "pending"
    drafting = "drafting"
    done = "done"
    needs_revision = "needs_revision"


class IssueSeverity(StrEnum):
    blocker = "blocker"
    major = "major"
    minor = "minor"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class JobEventLevel(StrEnum):
    info = "info"
    model = "model"
    tool = "tool"
    warn = "warn"
    error = "error"


class JobRuntime(StrEnum):
    nebius_serverless = "nebius_serverless"
    local = "local"


class LLMTier(StrEnum):
    """Routing tiers — see services/nebius_client.py for the rationale."""

    nano = "nano"
    super = "super"
    ultra = "ultra"


# ---------------------------------------------------------------------------
# Entity models (mirror Supabase tables)
# ---------------------------------------------------------------------------
class Profile(BaseModel):
    id: str
    org_name: str = ""
    org_description: str = ""
    website: str | None = None


class Project(BaseModel):
    id: str
    user_id: str
    title: str
    funder_name: str | None = None
    status: ProjectStatus = ProjectStatus.draft
    solicitation_doc_id: str | None = None
    org_doc_id: str | None = None
    compliance_score: int | None = Field(default=None, ge=0, le=100)
    abstract: str | None = None


class Document(BaseModel):
    id: str | None = None
    project_id: str | None = None
    kind: DocumentKind
    filename: str | None = None
    storage_path: str | None = None
    source_url: str | None = None
    extracted_text: str = ""
    page_count: int | None = None


class Requirement(BaseModel):
    """One extracted rule from the solicitation.

    ``source_excerpt`` keeps the verbatim quote the rule came from — the UI
    shows it on hover so every extracted requirement is provable against the
    source document (no hallucinated rules).
    """

    id: str | None = None
    project_id: str | None = None
    category: RequirementCategory = RequirementCategory.other
    key: str = ""
    value: str = ""
    is_mandatory: bool = False
    source_excerpt: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)


class ResearchFinding(BaseModel):
    """One web fact. Only URLs actually returned by Tavily ever become
    findings, which is what keeps proposal citations non-fabricated."""

    id: str | None = None
    project_id: str | None = None
    query: str = ""
    title: str
    url: str
    snippet: str | None = None
    relevance: float = Field(default=0.0, ge=0, le=1)
    used_in_sections: list[str] = Field(default_factory=list)


class TavilySearchResult(BaseModel):
    query: str
    answer: str = ""
    findings: list[ResearchFinding] = Field(default_factory=list)


class ResearchQuery(BaseModel):
    """One planned Tavily query (output of the plan_research node)."""

    query: str = Field(min_length=3)
    rationale: str = ""
    target_section: str = ""


class OutlineItem(BaseModel):
    order_index: int
    title: str
    target_words: int = 500
    requirement_keys: list[str] = Field(default_factory=list)


class Chunk(BaseModel):
    index: int
    text: str
    token_estimate: int


class ParsedDocument(BaseModel):
    text: str = ""
    page_count: int | None = None
    filename: str | None = None
    source_url: str | None = None
    chunks: list[Chunk] = Field(default_factory=list)


class Section(BaseModel):
    id: str | None = None
    project_id: str | None = None
    order_index: int
    title: str
    content_md: str = ""
    model_used: str | None = None
    token_count: int = 0
    status: SectionStatus = SectionStatus.pending


class ComplianceIssue(BaseModel):
    id: str | None = None
    project_id: str | None = None
    section_id: str | None = None
    requirement_id: str | None = None
    severity: IssueSeverity
    description: str
    suggested_fix: str | None = None
    resolved: bool = False


class Job(BaseModel):
    id: str
    project_id: str
    kind: str = "full_pipeline"
    status: JobStatus = JobStatus.queued
    progress: int = Field(default=0, ge=0, le=100)
    current_step: str | None = None
    error: str | None = None
    runtime: JobRuntime = JobRuntime.local
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobEvent(BaseModel):
    """One line of the live agent trace (Agent Run console)."""

    id: str | None = None
    job_id: str | None = None
    level: JobEventLevel = JobEventLevel.info
    step: str | None = None
    message: str
    model_used: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    ts: datetime | None = None


# ---------------------------------------------------------------------------
# LLM telemetry
# ---------------------------------------------------------------------------
class LLMCallResult(BaseModel):
    """Outcome of a single model call through the ModelRouter.

    The tokens/latency/cost fields are what the UI's Model Router panel renders
    to prove cost-aware routing — every call is logged as a job_event.
    """

    task_type: str
    tier: LLMTier
    model: str
    content: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    estimated_cost_usd: float = 0.0
    finish_reason: str | None = None
    attempts: int = 1
    mocked: bool = False

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out


# ---------------------------------------------------------------------------
# Pure data utilities (unit-tested in tests/test_requirement_dedupe.py)
# ---------------------------------------------------------------------------
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def estimate_tokens(text: str) -> int:
    """~4 characters per token. A budgeting heuristic (not billing-grade) —
    good enough for chunk sizing and cost panels; real token counts come from
    the model's usage payload whenever available."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _norm_text(s: str | None) -> str:
    """Lowercase, strip punctuation, collapse whitespace — so 'Page Limit:'
    and 'page limit' compare equal during dedupe."""
    return _WS_RE.sub(" ", _PUNCT_RE.sub("", (s or "").lower())).strip()


def _values_mergeable(a: str, b: str) -> bool:
    """Values merge when equal, or when one contains the other (≥6 chars) —
    '16 pages' and '16 pages across sections (a)-(f)' are the same rule."""
    na, nb = _norm_text(a), _norm_text(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return (len(na) >= 6 and na in nb) or (len(nb) >= 6 and nb in na)


def dedupe_requirements(requirements: list[Requirement]) -> list[Requirement]:
    """Merge near-duplicate requirements extracted from overlapping chunks.

    WHY: the solicitation is chunked (~6k tokens), so the same rule often
    appears in two chunks with slightly different wording. Duplicates would
    inflate the compliance audit (the same violation counted twice) and clutter
    the requirements checklist. Strategy:
      1. group by (category, normalized key) — first-seen order preserved;
      2. within a group, merge values that are equal or contained;
      3. keep the row with the highest confidence, but the first occurrence's
         position, and prefer any source_excerpt already captured.
    """
    groups: dict[tuple[RequirementCategory, str], list[Requirement]] = {}
    for req in requirements:
        groups.setdefault((req.category, _norm_text(req.key)), []).append(req)

    merged: list[Requirement] = []
    for items in groups.values():
        kept: list[Requirement] = []
        for req in items:
            for i, existing in enumerate(kept):
                if _values_mergeable(existing.value, req.value):
                    winner = (
                        req if req.confidence > existing.confidence else existing
                    ).model_copy()
                    # prefer a non-empty verbatim excerpt — first one wins
                    winner.source_excerpt = existing.source_excerpt or req.source_excerpt
                    kept[i] = winner
                    break
            else:
                kept.append(req.model_copy())
        merged.extend(kept)
    return merged
