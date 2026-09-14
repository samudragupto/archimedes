"""Node 6/8 · compliance_audit — SUPER.

Task type: "audit" → Super tier. WHY Super: the audit must read the ENTIRE
draft (~4k words) and reason about severity — beyond Nano's reliable capacity,
but nowhere near Ultra's price point for a structured judgment output.

The node is the scoring authority: the model proposes issues, the node
validates severities, resolves section/requirement foreign keys, computes
compliance_score = 100 − (blockers·25 + majors·10 + minors·3) clamped 0–100,
and marks sections that need revision.
"""

from __future__ import annotations

from ...models.schemas import ComplianceIssue, IssueSeverity, Section
from ...services.nebius_client import JSONRepairError, parse_llm_json
from ..context import PipelineContext, load_prompt, norm_key
from ..state import ProposalState, compute_compliance_score, count_by_severity, needs_revision

_STEP = "compliance_audit"
_VALID_SEVERITIES = {s.value for s in IssueSeverity}


def parse_issues(content: str) -> list[dict]:
    data = parse_llm_json(content)
    raw = data.get("issues", []) if isinstance(data, dict) else []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        description = str(item.get("description") or "").strip()
        if not description:
            continue
        severity = str(item.get("severity") or "minor").strip().lower()
        if severity not in _VALID_SEVERITIES:
            severity = "minor"  # unknown severity must never inflate the penalty
        out.append(
            {
                "severity": severity,
                "section_title": (
                    (str(item.get("section_title")).strip() or None)
                    if item.get("section_title")
                    else None
                ),
                "requirement_key": (
                    (str(item.get("requirement_key")).strip() or None)
                    if item.get("requirement_key")
                    else None
                ),
                "description": description[:1000],
                "suggested_fix": (
                    (str(item.get("suggested_fix")).strip() or None)
                    if item.get("suggested_fix")
                    else None
                ),
            }
        )
    return out


async def compliance_audit(state: ProposalState) -> dict:
    ctx: PipelineContext = state["ctx"]
    await ctx.step_begin(_STEP)

    sections: dict[str, dict] = state.get("sections", {})
    ordered = sorted(sections.values(), key=lambda s: s.get("order_index", 0))
    draft_text = "\n\n".join(
        f"### {s['title']}\n{s.get('content_md') or '(EMPTY — not yet drafted)'}" for s in ordered
    )
    from ..context import requirements_digest  # local import keeps node imports lean

    system = load_prompt("compliance_audit")
    user = (
        "MANDATORY REQUIREMENTS:\n"
        + requirements_digest(state.get("requirements", []), mandatory_only=True)
        + "\n\nALL REQUIREMENTS:\n"
        + requirements_digest(state.get("requirements", []))
        + "\n\nSECTION TITLES (use exactly these for section_title):\n"
        + "\n".join(f"- {s['title']}" for s in ordered)
        + f"\n\nFULL DRAFT:\n{draft_text}"
    )
    result = await ctx.router.complete(
        "audit",  # SUPER — whole-draft severity judgment
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        json_mode=True,
        fixture_key="compliance_audit",
    )
    try:
        raw_issues = parse_issues(result.content)
    except JSONRepairError:
        await ctx.event(
            "warn", _STEP, "Audit returned unparseable JSON — recording a single audit warning"
        )
        raw_issues = [
            {
                "severity": "minor",
                "section_title": None,
                "requirement_key": None,
                "description": "The automated audit could not complete; review requirements manually.",
                "suggested_fix": "Re-run the compliance audit.",
            }
        ]

    # Resolve foreign keys: model speaks in titles/keys, the DB wants uuids.
    requirement_ids: dict[str, str] = state.get("requirement_ids", {})
    section_ids: dict[str, str] = state.get("section_ids", {})
    issues: list[ComplianceIssue] = []
    for raw in raw_issues:
        issues.append(
            ComplianceIssue(
                project_id=state["project_id"],
                section_id=section_ids.get(raw["section_title"]) if raw["section_title"] else None,
                requirement_id=(
                    requirement_ids.get(norm_key(raw["requirement_key"]))
                    if raw["requirement_key"]
                    else None
                ),
                severity=IssueSeverity(raw["severity"]),
                description=raw["description"],
                suggested_fix=raw["suggested_fix"],
            )
        )

    score = compute_compliance_score(raw_issues)
    counts = count_by_severity(raw_issues)

    await ctx.reporter.persist_issues(state["project_id"], issues)
    await ctx.reporter.update_project(state["project_id"], compliance_score=score)

    # Sections referenced by blocker/major issues get flagged for revision.
    revised_targets = {
        raw["section_title"]
        for raw in raw_issues
        if needs_revision([raw]) and raw["section_title"] in sections
    }
    updated_sections = dict(sections)
    for title in revised_targets:
        section = Section(**{**updated_sections[title], "status": "needs_revision"})
        await ctx.reporter.upsert_section(state["project_id"], section)
        updated_sections[title] = section.model_dump()

    await ctx.model_event(
        _STEP,
        result,
        f"Audit complete: {counts['blocker']} blockers · {counts['major']} majors · "
        f"{counts['minor']} minors → compliance score {score}/100",
    )
    if revised_targets:
        await ctx.event("info", _STEP, f"Marked for revision: {', '.join(sorted(revised_targets))}")
    # State carries BOTH the resolved foreign keys and the human-facing
    # section_title/requirement_key — the revise node matches targets by title.
    state_issues = []
    for model, raw in zip(issues, raw_issues, strict=False):
        entry = model.model_dump()
        entry["section_title"] = raw["section_title"]
        entry["requirement_key"] = raw["requirement_key"]
        state_issues.append(entry)

    await ctx.step_end(_STEP)
    return {
        "compliance_issues": state_issues,
        "compliance_score": score,
        "sections": updated_sections,
    }
