"""Node 5/8 · draft_sections — ULTRA.

Task type: "drafting" → Ultra tier. WHY Ultra: this is the only node whose
output a human reviewer reads as prose — argument quality, cadence and
persuasion are the product here, and it's where the token budget should go
(<30% of pipeline calls, >85% of tokens).

Sections are drafted as independent coroutines (parallel-safe by construction)
at concurrency 2 — gentle on rate limits, 2× faster than sequential. Each
finished section is persisted IMMEDIATELY, so the browser's Draft tab fills in
live during the run.

Citation discipline: the prompt provides the numbered findings block; the
section may cite [n] only within it. The audit node later verifies the numbers.
"""

from __future__ import annotations

import asyncio
import re

from ...models.schemas import Section, SectionStatus, estimate_tokens
from ...services.nebius_client import strip_think
from ..context import (
    PipelineContext,
    findings_block,
    load_prompt,
    norm_key,
    requirements_digest,
)
from ..state import ProposalState

_STEP = "draft_sections"
CONCURRENCY = 2
_CITATION_RE = re.compile(r"\[(\d{1,2})\]")


def _relevant_requirements(item: dict, requirements: list[dict]) -> list[dict]:
    """Requirements whose key the outline item references, plus category-level
    matches on the section title (e.g. format rules mentioning the section)."""
    keys = {norm_key(k) for k in item.get("requirement_keys", [])}
    title_key = norm_key(item.get("title"))
    out = [r for r in requirements if norm_key(r.get("key")) in keys]
    for r in requirements:
        if r in out:
            continue
        value = norm_key(r.get("value"))
        if title_key and title_key in value:
            out.append(r)
    return out


async def draft_sections(state: ProposalState) -> dict:
    ctx: PipelineContext = state["ctx"]
    await ctx.step_begin(_STEP)

    outline_items = state.get("outline", [])
    requirements = state.get("requirements", [])
    findings = state.get("findings", [])
    sections: dict[str, dict] = dict(state.get("sections", {}))
    section_ids: dict[str, str] = dict(state.get("section_ids", {}))
    org_text = (state.get("org_text") or "").strip()[:2400]

    system = load_prompt("draft_section")
    req_digest = requirements_digest(requirements)
    refs = findings_block(findings)
    total = len(outline_items)
    semaphore = asyncio.Semaphore(CONCURRENCY)
    progress_lock = asyncio.Lock()
    done = 0

    async def draft_one(item: dict) -> None:
        nonlocal done
        async with semaphore:
            title = item.get("title", "Untitled Section")
            await ctx.event(
                "info", _STEP, f"Drafting “{title}” — target ~{item.get('target_words', 500)} words"
            )
            relevant = _relevant_requirements(item, requirements)
            user = (
                f"SECTION: {title}\n"
                f"TARGET LENGTH: ~{item.get('target_words', 500)} words\n\n"
                f"REQUIREMENTS THIS SECTION MUST SATISFY:\n"
                + requirements_digest(relevant)
                + f"\n\nFULL SOLICITATION REQUIREMENTS (context):\n{req_digest}\n\n"
                f"ORGANIZATION PROFILE:\n{org_text or '(not provided)'}\n\n"
                f"RESEARCH FINDINGS (cite as [n], n from this list only):\n{refs}"
            )
            result = await ctx.router.complete(
                "drafting",  # ULTRA — long-form persuasive prose
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                fixture_key=f"draft:{title}",
            )
            content = strip_think(result.content).strip()
            citations = len(set(_CITATION_RE.findall(content)))
            section = Section(
                order_index=item.get("order_index", 0),
                title=title,
                content_md=content,
                model_used=result.model,
                token_count=result.tokens_out or estimate_tokens(content),
                status=SectionStatus.done,
                id=section_ids.get(title),
            )
            db_id = await ctx.reporter.upsert_section(state["project_id"], section)
            if db_id:
                section_ids[title] = db_id
                section.id = db_id
            sections[title] = section.model_dump()

            await ctx.model_event(
                _STEP,
                result,
                f"Drafted “{title}” — {len(content.split())} words · {citations} inline citation(s)",
            )
            async with progress_lock:
                done += 1
                await ctx.set_progress(_STEP, 55 + int(20 * done / max(1, total)))

    await asyncio.gather(*(draft_one(item) for item in outline_items))
    await ctx.step_end(_STEP)
    return {"sections": sections, "section_ids": section_ids}
