"""Node 3/8 · run_research — Tavily (no model).

The only node that touches the live web. Calls the Tavily Search API with
search_depth="advanced", max_results=5, include_answer=True, at concurrency 4
(a rate-limit-friendly floor that still keeps 6 queries under ~10s).

Citation integrity invariant: findings are stored EXACTLY as returned by
Tavily (title/url/snippet/score, deduped by URL). The drafting node may cite
only these — this is where "never fabricated citations" is enforced.
"""

from __future__ import annotations

import asyncio

from ...models.schemas import ResearchFinding, TavilySearchResult
from ...services.tavily_service import TavilyError
from ..context import PipelineContext
from ..state import ProposalState

_STEP = "run_research"
CONCURRENCY = 4


async def run_research(state: ProposalState) -> dict:
    ctx: PipelineContext = state["ctx"]
    await ctx.step_begin(_STEP)

    plan = state.get("research_plan", [])
    if not plan:
        await ctx.event(
            "warn", _STEP, "No research plan — drafting will proceed without web citations"
        )
        await ctx.step_end(_STEP)
        return {"findings": []}

    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def search_one(query: str) -> tuple[TavilySearchResult | None, str | None]:
        async with semaphore:
            try:
                return (
                    await ctx.tavily.search(
                        query, max_results=5, search_depth="advanced", include_answer=True
                    ),
                    None,
                )
            except TavilyError as e:
                # One failed query must not sink the run — the remaining
                # queries usually still cover the Statement of Need.
                return None, str(e)

    results = await asyncio.gather(*(search_one(q["query"]) for q in plan))
    for err in (err for _, err in results if err):
        await ctx.event("warn", _STEP, f"search failed: {err}")

    # Merge, dedupe by URL (Tavily returns the same page for overlapping
    # queries), preserve first-seen order → that order becomes the citation
    # numbering [1..n] used across the whole draft.
    seen: set[str] = set()
    findings: list[ResearchFinding] = []
    raw_results = sum(len(res.findings) for res, _ in results if res)
    for (res, _err), planned in zip(results, plan, strict=False):
        if not res:
            continue
        for f in res.findings:
            if f.url in seen:
                continue
            seen.add(f.url)
            f.used_in_sections = (
                [planned.get("target_section", "")] if planned.get("target_section") else []
            )
            findings.append(f)

    await ctx.reporter.persist_findings(state["project_id"], findings)
    await ctx.event(
        "tool",
        _STEP,
        f"Tavily advanced search: {len(plan)} queries · {raw_results} results · "
        f"{len(findings)} findings kept (concurrency {CONCURRENCY})",
    )
    if not findings:
        await ctx.event(
            "warn", _STEP, "All searches failed or returned nothing — drafting without citations"
        )
    await ctx.step_end(_STEP)
    return {"findings": [f.model_dump() for f in findings]}
