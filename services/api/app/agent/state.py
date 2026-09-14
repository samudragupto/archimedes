"""ProposalState — the typed state that flows through the LangGraph pipeline.

Design rules:
  * Every field is JSON-friendly data (dicts/lists/str/int) EXCEPT ``ctx``,
    which carries live process objects (model router, tavily, reporter). LangGraph
    passes object references through untouched, and no node ever serializes the
    state — this is what keeps nodes pure functions of (state) → (partial state).
  * Nodes never mutate the input state; they return partial updates that
    LangGraph merges (last-value-wins channels).
"""

from __future__ import annotations

from typing import Any, TypedDict


class ProposalState(TypedDict, total=False):
    # -- identity -------------------------------------------------------------
    project_id: str
    job_id: str
    project_title: str  # current DB title (finalize may refine it)
    ctx: Any  # PipelineContext: settings, router, tavily, reporter

    # -- inputs (loaded by the runner before the graph starts) ----------------
    solicitation_text: str
    org_text: str

    # -- pipeline artifacts, in production order -------------------------------
    requirements: list[dict]  # deduped Requirement dicts
    requirement_ids: dict[str, str]  # normalized requirement key -> DB uuid
    research_plan: list[dict]  # ResearchQuery dicts
    findings: list[dict]  # ResearchFinding dicts, citation order (1-based)
    outline: list[dict]  # OutlineItem dicts
    sections: dict[str, dict]  # title -> section dict (order, content, status…)
    section_ids: dict[str, str]  # title -> DB uuid (for issue linking)

    # -- audit loop -------------------------------------------------------------
    compliance_issues: list[dict]  # ComplianceIssue dicts
    compliance_score: int
    revision_round: int  # max 2 (graph routing enforces the ceiling)

    # -- finalize outputs --------------------------------------------------------
    title: str
    abstract: str
    final_markdown: str
    error: str


# ---------------------------------------------------------------------------
# Compliance scoring — the exact formula from the product spec, as a pure
# function so the API, the agent and the tests all agree on the arithmetic.
# ---------------------------------------------------------------------------
SEVERITY_WEIGHTS: dict[str, int] = {"blocker": 25, "major": 10, "minor": 3}


def count_by_severity(issues: list[dict]) -> dict[str, int]:
    counts = {"blocker": 0, "major": 0, "minor": 0}
    for issue in issues:
        severity = str(issue.get("severity", "minor"))
        if severity in counts:
            counts[severity] += 1
    return counts


def compute_compliance_score(issues: list[dict]) -> int:
    """score = 100 − (blockers·25 + majors·10 + minors·3), clamped to 0–100.

    WHY these weights: a blocker is a desk-reject (missing mandatory section,
    past deadline), a major is a competitive penalty a reviewer will notice,
    a minor is polish. The ratio 25:10:3 mirrors how review panels actually
    deduct points — and guarantees any single blocker caps the score at 75.
    """
    counts = count_by_severity(issues)
    penalty = sum(SEVERITY_WEIGHTS[s] * n for s, n in counts.items())
    return max(0, min(100, 100 - penalty))


def needs_revision(issues: list[dict]) -> bool:
    """The audit→revise loop only spins for blockers and majors — minors are
    surfaced to the user in the Compliance tab (with one-click fixes) but never
    burn Ultra tokens on their own."""
    return any(i.get("severity") in ("blocker", "major") for i in issues)
