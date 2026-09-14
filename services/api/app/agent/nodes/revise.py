"""Node 7/8 · revise — ULTRA.

Task type: "revision" → Ultra tier. WHY Ultra: revision must *rewrite
persuasively* under constraints — same skill as drafting, so same tier.

Cost discipline (the whole point of this node): only sections referenced by
blocker/major issues are rewritten, and the graph caps this loop at 2 rounds.
Minors never trigger revisions — they are surfaced to the user as one-click
fixes in the Compliance tab instead of burning tokens invisibly.
"""

from __future__ import annotations

from ...models.schemas import Section
from ...services.nebius_client import strip_think
from ..context import PipelineContext, load_prompt
from ..state import ProposalState

_STEP = "revise"
_BLOCKING = {"blocker", "major"}


def revision_targets(issues: list[dict], sections: dict[str, dict]) -> list[str]:
    """Section titles with blocker/major issues, in outline order."""
    titles = {
        i.get("section_title")
        for i in issues
        if i.get("severity") in _BLOCKING and i.get("section_title") in sections
    }
    return [
        s["title"]
        for s in sorted(sections.values(), key=lambda x: x.get("order_index", 0))
        if s["title"] in titles
    ]


async def revise(state: ProposalState) -> dict:
    ctx: PipelineContext = state["ctx"]
    await ctx.step_begin(_STEP)

    sections: dict[str, dict] = dict(state.get("sections", {}))
    issues = state.get("compliance_issues", [])
    targets = revision_targets(issues, sections)
    if not targets:
        await ctx.event("info", _STEP, "No blocking issues target a section — nothing to revise")
        await ctx.step_end(_STEP)
        return {"revision_round": state.get("revision_round", 0) + 1}

    system = load_prompt("revise_section")
    round_no = state.get("revision_round", 0) + 1
    await ctx.event(
        "info",
        _STEP,
        f"Revision round {round_no}: rewriting {len(targets)} section(s) — {', '.join(targets)}",
    )

    for title in targets:
        fixes = "\n".join(
            f"- [{i.get('severity')}] {i.get('description')}"
            + (f"\n  FIX: {i['suggested_fix']}" if i.get("suggested_fix") else "")
            for i in issues
            if i.get("section_title") == title and i.get("severity") in _BLOCKING
        )
        current = sections[title].get("content_md") or "(empty section)"
        user = (
            f"SECTION: {title}\n\nCURRENT SECTION MARKDOWN:\n{current}\n\n"
            f"COMPLIANCE FIXES TO APPLY:\n{fixes}"
        )
        result = await ctx.router.complete(
            "revision",  # ULTRA — constrained persuasive rewrite
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            fixture_key=f"revise:{title}",
        )
        content = strip_think(result.content).strip() or current
        section = Section(
            **{
                **sections[title],
                "content_md": content,
                "model_used": result.model,
                "token_count": result.tokens_out or sections[title].get("token_count", 0),
                "status": "done",
            }
        )
        await ctx.reporter.upsert_section(state["project_id"], section)
        sections[title] = section.model_dump()
        await ctx.model_event(
            _STEP, result, f"Revised “{title}” — {len(content.split())} words after fixes"
        )

    await ctx.step_end(_STEP)
    return {"sections": sections, "revision_round": round_no}
