"""Node 8/8 · finalize — NANO.

Task types: "formatting" (title/abstract) → Nano tier. WHY Nano: the abstract
is a compression task over text that already exists — cheap, deterministic,
no persuasion required. The node then assembles the final document (TOC +
sections + references) in pure Python, since assembling markdown needs zero
intelligence and full determinism.

References are generated ONLY from stored findings — the same list that
numbered the in-text citations — so the reference list can never contain a
source the model invented.
"""

from __future__ import annotations

from ...services.nebius_client import parse_llm_json, strip_think
from ..context import PipelineContext, load_prompt
from ..state import ProposalState

_STEP = "finalize"


def compose_final_markdown(
    title: str, abstract: str, ordered_sections: list[dict], findings: list[dict]
) -> str:
    toc = "\n".join(f"{i}. {s['title']}" for i, s in enumerate(ordered_sections, start=1))
    body = "\n\n".join(s.get("content_md") or "" for s in ordered_sections).strip()
    refs = "\n".join(
        f"[{i}] {f.get('title', '')} — {f.get('url', '')}" for i, f in enumerate(findings, start=1)
    )
    parts = [
        f"# {title}",
        f"## Abstract\n\n{abstract.strip()}",
        f"## Table of Contents\n\n{toc}",
        body,
        f"## References\n\n{refs}" if refs else "",
    ]
    return "\n\n".join(p for p in parts if p.strip()) + "\n"


async def finalize(state: ProposalState) -> dict:
    ctx: PipelineContext = state["ctx"]
    await ctx.step_begin(_STEP)

    system = load_prompt("finalize")
    sections: dict[str, dict] = state.get("sections", {})
    ordered = sorted(sections.values(), key=lambda s: s.get("order_index", 0))
    draft_digest = "\n\n".join(
        f"### {s['title']}\n{(s.get('content_md') or '')[:600]}" for s in ordered
    )
    result = await ctx.router.complete(
        "formatting",  # NANO — compression of existing text
        [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"WORKING TITLE: {state.get('project_title', '')}\n\nOUTLINE AND DRAFT EXCERPTS:\n{draft_digest}",
            },
        ],
        json_mode=True,
        fixture_key="finalize",
    )
    try:
        data = parse_llm_json(strip_think(result.content))
        title = str(data.get("title") or "").strip() or state.get("project_title", "Grant Proposal")
        abstract = str(data.get("abstract") or "").strip()
    except Exception:  # noqa: BLE001 — finalize must never fail the finished draft
        title = state.get("project_title", "Grant Proposal")
        abstract = ""
        await ctx.event("warn", _STEP, "Could not parse title/abstract — using working title")

    findings = state.get("findings", [])
    final_markdown = compose_final_markdown(title, abstract, ordered, findings)

    await ctx.reporter.update_project(state["project_id"], title=title, abstract=abstract or None)
    await ctx.model_event(
        _STEP,
        result,
        f"Finalized: {len(ordered)} sections · {len(findings)} references · abstract "
        f"{len(abstract.split()) if abstract else 0} words",
    )
    await ctx.event("info", _STEP, f"Proposal complete: “{title}”")
    await ctx.step_end(_STEP)  # progress → 100, project status → complete
    return {"title": title, "abstract": abstract, "final_markdown": final_markdown}
