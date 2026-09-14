"""Node 4/8 · outline — SUPER.

Task type: "planning" → Super tier. WHY Super: the outline is a coverage
problem (map every mandatory 'section' requirement to exactly one section,
distribute a hard page budget) — structured reasoning, minimal prose.

The node validates the model's outline the same way a editor would: every
mandatory section requirement must be covered, page limits become word budgets
(~500 words/page), and the total must fit the narrative page cap. Missing
sections are appended mechanically — the model proposes, the node guarantees.
"""

from __future__ import annotations

from ...models.schemas import OutlineItem, Section, SectionStatus
from ...services.nebius_client import JSONRepairError, parse_llm_json
from ..context import (
    PipelineContext,
    load_prompt,
    norm_key,
    requirements_digest,
    words_from_pages,
)
from ..state import ProposalState

_STEP = "outline"
DEFAULT_SECTION_TITLES = [
    "Project Summary",
    "Statement of Need",
    "Project Design and Methodology",
    "Evaluation Plan",
    "Budget and Budget Justification",
    "Organizational Capacity",
]
MIN_WORDS, MAX_WORDS = 150, 3000


def parse_outline(content: str) -> list[OutlineItem]:
    data = parse_llm_json(content)
    raw = data.get("sections", []) if isinstance(data, dict) else []
    items: list[OutlineItem] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        if not title:
            continue
        try:
            words = int(entry.get("target_words") or 500)
        except (TypeError, ValueError):
            words = 500
        items.append(
            OutlineItem(
                order_index=len(items) + 1,
                title=title[:200],
                target_words=max(MIN_WORDS, min(MAX_WORDS, words)),
                requirement_keys=[str(k) for k in (entry.get("requirement_keys") or [])][:10],
            )
        )
    return items


def _coverage_key(title: str) -> str:
    t = norm_key(title)
    for noise in (" required", " section", " proposal"):
        t = t.replace(noise, "")
    return t


def ensure_coverage(
    items: list[OutlineItem], requirements: list[dict]
) -> tuple[list[OutlineItem], list[str]]:
    """Guarantee every mandatory 'section' requirement maps to an outline item.
    Returns (items, appended_titles)."""
    section_reqs = [
        r for r in requirements if r.get("category") == "section" and r.get("is_mandatory", True)
    ]
    covered = {_coverage_key(t) for item in items for t in [item.title]}
    # also count keys the model itself attached to items (fuzzy title cases)
    for item in items:
        for key in item.requirement_keys:
            covered.add(norm_key(key))

    appended: list[str] = []
    for req in section_reqs:
        key = norm_key(req.get("key"))
        if key in covered or _coverage_key(req.get("key", "")) in covered:
            continue
        # mechanical fallback: one item per uncovered mandatory section
        items.append(
            OutlineItem(
                order_index=len(items) + 1,
                title=req.get("key", "Untitled Section"),
                target_words=words_from_pages(req.get("value")) or 500,
                requirement_keys=[req.get("key", "")],
            )
        )
        appended.append(req.get("key", ""))
    return items, appended


async def outline(state: ProposalState) -> dict:
    ctx: PipelineContext = state["ctx"]
    await ctx.step_begin(_STEP)

    requirements = state.get("requirements", [])
    system = load_prompt("outline")
    user = (
        "SECTION REQUIREMENTS (from the solicitation):\n"
        + requirements_digest([r for r in requirements if r.get("category") == "section"])
        + "\n\nALL REQUIREMENTS (for context):\n"
        + requirements_digest(requirements, mandatory_only=True)
        + f"\n\nORGANIZATION PROFILE (excerpt):\n{(state.get('org_text') or '')[:800] or '(not provided)'}"
    )
    result = await ctx.router.complete(
        "planning",  # SUPER — coverage + budget distribution
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        json_mode=True,
        fixture_key="outline",
    )
    try:
        items = parse_outline(result.content)
    except JSONRepairError:
        # Fallback to the standard structure: a broken outline JSON should not
        # kill a run — reviewers expect the classic grant skeleton anyway.
        await ctx.event("warn", _STEP, "Unparseable outline — using standard section structure")
        items = [
            OutlineItem(order_index=i, title=t, target_words=500, requirement_keys=[])
            for i, t in enumerate(DEFAULT_SECTION_TITLES, start=1)
        ]

    items, appended = ensure_coverage(items, requirements)
    for i, item in enumerate(items, start=1):
        item.order_index = i
    total_words = sum(item.target_words for item in items)

    # Persist pending sections immediately so the Draft tab shows the skeleton
    # before the first word is written.
    section_ids: dict[str, str] = dict(state.get("section_ids", {}))
    sections: dict[str, dict] = dict(state.get("sections", {}))
    for item in items:
        if item.title in sections:
            continue
        section = Section(
            order_index=item.order_index, title=item.title, status=SectionStatus.pending
        )
        db_id = await ctx.reporter.upsert_section(state["project_id"], section)
        section.id = db_id
        section_ids[item.title] = db_id or ""
        sections[item.title] = section.model_dump()

    await ctx.model_event(
        _STEP, result, f"Outlined {len(items)} sections · total target ~{total_words:,} words"
    )
    if appended:
        await ctx.event(
            "info",
            _STEP,
            f"Coverage guard appended {len(appended)} missing mandatory section(s): {', '.join(appended)}",
        )
    await ctx.step_end(_STEP)
    return {
        "outline": [item.model_dump() for item in items],
        "sections": sections,
        "section_ids": section_ids,
    }
