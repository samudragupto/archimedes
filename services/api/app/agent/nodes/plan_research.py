"""Node 2/8 · plan_research — SUPER.

Task type: "planning" → Super tier. WHY Super (not Nano): choosing *which*
evidence will persuade a review panel is a judgment task over the whole
requirement set; and not Ultra because it is a short structured output where
the mid model is more than capable — this is exactly the middle of the routing
curve.
"""

from __future__ import annotations

from ...models.schemas import ResearchQuery
from ...services.nebius_client import JSONRepairError, parse_llm_json
from ..context import PipelineContext, load_prompt, requirements_digest
from ..state import ProposalState

_STEP = "plan_research"

# Spec: 4–8 queries. We clamp hard at 8 (cost discipline) and accept fewer —
# a tight two-page local grant may genuinely need 4 sharp searches.
MAX_QUERIES = 8


def parse_queries(content: str) -> list[ResearchQuery]:
    data = parse_llm_json(content)
    raw = data.get("queries", []) if isinstance(data, dict) else []
    out: list[ResearchQuery] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query") or "").strip()
        if len(query) < 3:
            continue
        out.append(
            ResearchQuery(
                query=query[:300],
                rationale=str(item.get("rationale") or "").strip()[:500],
                target_section=str(item.get("target_section") or "").strip()[:200],
            )
        )
    return out[:MAX_QUERIES]


async def plan_research(state: ProposalState) -> dict:
    ctx: PipelineContext = state["ctx"]
    await ctx.step_begin(_STEP)

    # A trimmed org profile keeps the prompt small: the planner only needs the
    # org's geography, mission and program area to target searches — not its
    # full history.
    org_summary = (state.get("org_text") or "").strip()[:1500]
    system = load_prompt("plan_research")
    user = (
        f"EXTRACTED REQUIREMENTS:\n{requirements_digest(state.get('requirements', []))}\n\n"
        f"ORGANIZATION PROFILE (excerpt):\n{org_summary or '(not provided)'}"
    )
    result = await ctx.router.complete(
        "planning",  # SUPER — evidence-strategy judgment
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        json_mode=True,
        fixture_key="plan_research",
    )
    try:
        queries = parse_queries(result.content)
    except JSONRepairError:
        queries = []
        await ctx.event(
            "warn", _STEP, "Unparseable research plan — continuing without web research"
        )

    await ctx.model_event(_STEP, result, f"Planned {len(queries)} research queries")
    for q in queries:
        target = f" → {q.target_section}" if q.target_section else ""
        await ctx.event("tool", _STEP, f"query: “{q.query}”{target}")
    await ctx.step_end(_STEP)
    return {"research_plan": [q.model_dump() for q in queries]}
