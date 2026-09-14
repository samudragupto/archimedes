"""Pipeline runner: loads inputs, invokes the graph, marks the job finished.

This is the only function the worker (and Phase 4's /run endpoint) needs:
``run_pipeline(project_id, job_id, reporter, settings)``. Inputs can be passed
directly (tests, --demo) or are loaded from Supabase (production).
"""

from __future__ import annotations

import asyncio

from ..config import Settings
from ..models.schemas import estimate_tokens
from . import fixtures as _mock_fixtures  # noqa: F401 — registers MOCK fixtures (idempotent)
from .context import PipelineContext
from .reporter import RunReporter
from .state import ProposalState


async def _load_inputs(project_id: str) -> tuple[str, str, str]:
    from .. import db  # service-role client (sync) → to_thread

    project = await asyncio.to_thread(db.get_project, project_id) or {}
    sol = await asyncio.to_thread(db.get_document, project_id, "solicitation")
    org = await asyncio.to_thread(db.get_document, project_id, "organization")
    solicitation_text = (sol or {}).get("extracted_text") or ""
    org_text = (org or {}).get("extracted_text") or ""
    return solicitation_text, org_text, (project or {}).get("title", "Grant Proposal")


async def run_pipeline(
    project_id: str,
    job_id: str,
    reporter: RunReporter,
    settings: Settings,
    *,
    solicitation_text: str | None = None,
    org_text: str | None = None,
    project_title: str | None = None,
) -> ProposalState:
    """Execute the full agent pipeline for one job.

    Failure contract: any node exception is traced as an error event, the job
    is marked failed, the project status flips to 'failed', and the exception
    re-raises so the worker process exits non-zero (Nebius Jobs surfaces that
    in the console; the API surfaces it in the job row).
    """
    from ..services.nebius_client import ModelRouter
    from ..services.tavily_service import TavilyService
    from .graph import build_graph

    if solicitation_text is None or org_text is None or project_title is None:
        loaded_sol, loaded_org, loaded_title = await _load_inputs(project_id)
        solicitation_text = solicitation_text if solicitation_text is not None else loaded_sol
        org_text = org_text if org_text is not None else loaded_org
        project_title = project_title or loaded_title

    ctx = PipelineContext(
        settings=settings,
        router=ModelRouter(settings=settings),
        tavily=TavilyService(settings=settings),
        reporter=reporter,
    )
    state: ProposalState = {
        "project_id": project_id,
        "job_id": job_id,
        "project_title": project_title,
        "ctx": ctx,
        "solicitation_text": solicitation_text,
        "org_text": org_text,
        "requirements": [],
        "requirement_ids": {},
        "research_plan": [],
        "findings": [],
        "outline": [],
        "sections": {},
        "section_ids": {},
        "compliance_issues": [],
        "compliance_score": 100,
        "revision_round": 0,
    }

    await reporter.event(
        "info",
        "pipeline",
        f"Pipeline started · drafting={settings.nemotron_ultra_model.split('/')[-1]} · "
        f"audit={settings.nemotron_super_model.split('/')[-1]} · "
        f"extraction={settings.nemotron_nano_model.split('/')[-1]}"
        + (" · MOCK_LLM" if settings.mock_llm else ""),
    )

    graph = build_graph()
    try:
        final = await graph.ainvoke(state)
        drafted = [s for s in final.get("sections", {}).values() if s.get("content_md")]
        total_words = sum(len((s.get("content_md") or "").split()) for s in drafted)
        await reporter.event(
            "info",
            "pipeline",
            f"Pipeline finished · compliance {final.get('compliance_score', 0)}/100 · "
            f"{len(final.get('requirements', []))} requirements · {len(drafted)}/{len(final.get('sections', {}))} "
            f"sections drafted · ~{total_words:,} words · "
            f"~{estimate_tokens(final.get('final_markdown', '')):,} tokens",
        )
        await reporter.finish("succeeded")
        return final
    except Exception as e:
        await reporter.event("error", "pipeline", f"Pipeline failed: {e}")
        try:
            await reporter.update_project(project_id, status="failed")
        except Exception:  # noqa: BLE001 — never mask the original failure
            pass
        await reporter.finish("failed", error=str(e))
        raise
