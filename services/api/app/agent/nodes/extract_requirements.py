"""Node 1/8 · extract_requirements — NANO.

Task type: "extraction" → Nano tier. WHY Nano: this is high-volume, small
input/output, structure-not-style work at temperature 0 — the cheapest model
does it as well as the big one, and the solicitation can span several chunks,
so the savings multiply.

Strategy: chunk the solicitation (~6k tokens, with overlap so a rule that
straddles a boundary survives), extract strict JSON per chunk, then merge and
dedupe across chunks (same rule often surfaces twice with different wording).
"""

from __future__ import annotations

from ...models.schemas import Requirement, RequirementCategory, dedupe_requirements
from ...services.document_parser import chunk_text
from ...services.nebius_client import JSONRepairError, parse_llm_json, strip_think
from ..context import PipelineContext, load_prompt
from ..state import ProposalState

_STEP = "extract_requirements"


def _valid_category(raw: str) -> RequirementCategory:
    try:
        return RequirementCategory(raw)
    except ValueError:
        # Unknown category from the model → "other", never a crash: a dropped
        # requirement is worse than a mis-filed one.
        return RequirementCategory.other


def parse_requirements_json(content: str, project_id: str | None = None) -> list[Requirement]:
    """Model JSON → validated Requirements. Skips malformed items instead of
    failing the chunk; extraction is best-effort by design (the audit node
    double-checks coverage later)."""
    data = parse_llm_json(strip_think(content))
    items = data.get("requirements", []) if isinstance(data, dict) else []
    out: list[Requirement] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        if not key or not value:
            continue  # a requirement without a rule is noise
        try:
            confidence = min(1.0, max(0.0, float(item.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        out.append(
            Requirement(
                project_id=project_id,
                category=_valid_category(str(item.get("category", "other"))),
                key=key[:200],
                value=value[:500],
                is_mandatory=bool(item.get("is_mandatory", True)),
                source_excerpt=(
                    (str(item.get("source_excerpt")).strip() or None)
                    if item.get("source_excerpt")
                    else None
                ),
                confidence=confidence,
            )
        )
    return out


async def extract_requirements(state: ProposalState) -> dict:
    ctx: PipelineContext = state["ctx"]
    await ctx.step_begin(_STEP)

    text = (state.get("solicitation_text") or "").strip()
    if not text:
        raise ValueError("solicitation text is empty — upload the solicitation document first")

    chunks = chunk_text(text, ctx.settings.chunk_target_tokens, ctx.settings.chunk_overlap_tokens)
    await ctx.event(
        "info",
        _STEP,
        f"Parsed solicitation: {len(chunks)} chunk(s) (~{ctx.settings.chunk_target_tokens} tokens each)",
    )

    system = load_prompt("extract_requirements")
    raw_requirements: list[Requirement] = []
    for i, chunk in enumerate(chunks, start=1):
        result = await ctx.router.complete(
            "extraction",  # NANO — cheap, deterministic JSON extraction
            [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"SOLICITATION CHUNK {i}/{len(chunks)}:\n\n{chunk.text}",
                },
            ],
            json_mode=True,
            fixture_key="extract_requirements",
        )
        try:
            parsed = parse_requirements_json(result.content, state["project_id"])
        except JSONRepairError:
            # One unreadable chunk must not sink the run; coverage is enforced
            # downstream by the compliance audit.
            await ctx.event(
                "warn", _STEP, f"Chunk {i}/{len(chunks)}: unparseable extraction, skipped"
            )
            parsed = []
        raw_requirements.extend(parsed)
        await ctx.model_event(
            _STEP, result, f"Chunk {i}/{len(chunks)}: extracted {len(parsed)} requirements"
        )

    merged = dedupe_requirements(raw_requirements)
    ids = await ctx.reporter.persist_requirements(state["project_id"], merged)
    await ctx.event(
        "info",
        _STEP,
        f"Extracted {len(merged)} requirements ({len(raw_requirements)} raw → {len(merged)} after dedupe)",
    )
    await ctx.step_end(_STEP)
    return {
        "requirements": [r.model_dump() for r in merged],
        "requirement_ids": ids,
    }
