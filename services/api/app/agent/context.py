"""PipelineContext — the process objects nodes need, carried through state.

Nodes stay pure: they receive everything via ``state["ctx"]`` and return data
only. The context bundles:

  * settings — the shared Settings object (models, keys, knobs)
  * router   — the ModelRouter (all LLM calls, already cost-routed per tier)
  * tavily   — the research tool
  * reporter — the event/progress sink (Supabase in production, in-memory in
               tests and the CLI demo)

It also owns the step→progress map (the single source of truth for the job
progress bar) and the prompt loader.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import Settings
from ..models.schemas import LLMCallResult
from .reporter import RunReporter

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a system prompt from agent/prompts/<name>.md.

    Prompts live as files (not string constants) so they can be reviewed,
    diffed and improved without touching node logic.
    """
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"prompt file missing: {path}")
    return path.read_text(encoding="utf-8")


# step → (progress_start, progress_end, project_status)
# The single source of truth for the job progress bar and the project status
# enum transitions the UI keys its timeline off.
STEP_META: dict[str, tuple[int, int, str]] = {
    "extract_requirements": (5, 20, "extracting"),
    "plan_research": (20, 30, "researching"),
    "run_research": (30, 45, "researching"),
    "outline": (45, 55, "drafting"),
    "draft_sections": (55, 75, "drafting"),
    "compliance_audit": (75, 85, "auditing"),
    "revise": (85, 92, "revising"),
    "finalize": (92, 100, "complete"),
}


@dataclass
class PipelineContext:
    settings: Settings
    router: Any  # ModelRouter (typed as Any to avoid a circular import)
    tavily: Any  # TavilyService
    reporter: RunReporter

    async def step_begin(self, step: str) -> None:
        start, _, status = STEP_META[step]
        await self.reporter.set_step(step, start, status)

    async def step_end(self, step: str) -> None:
        _, end, _ = STEP_META[step]
        await self.reporter.set_step(step, end)

    async def set_progress(self, step: str, progress: int) -> None:
        start, end, _ = STEP_META[step]
        await self.reporter.set_step(step, max(start, min(end, progress)))

    async def event(self, level: str, step: str, message: str, **metrics) -> None:
        await self.reporter.event(level=level, step=step, message=message, **metrics)

    async def model_event(self, step: str, result: LLMCallResult, message: str) -> None:
        """Every model call becomes a job_event with its metering — this is the
        data behind the UI's Model Router panel."""
        await self.reporter.event(
            level="model",
            step=step,
            message=message,
            model_used=result.model,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            latency_ms=result.latency_ms,
        )


# ---------------------------------------------------------------------------
# Prompt-context builders (pure string assembly shared by several nodes)
# ---------------------------------------------------------------------------
def requirements_digest(requirements: list[dict], *, mandatory_only: bool = False) -> str:
    """Compact requirement list for prompts: one line per rule."""
    lines: list[str] = []
    for r in requirements:
        if mandatory_only and not r.get("is_mandatory"):
            continue
        mand = "MANDATORY" if r.get("is_mandatory") else "optional"
        lines.append(
            f"- [{r.get('category', 'other')}] {r.get('key', '')}: {r.get('value', '')} ({mand})"
        )
    return "\n".join(lines) or "- (none extracted)"


def findings_block(findings: list[dict]) -> str:
    """Numbered findings for drafting prompts — the [n] here is the citation
    space the draft must stay inside (never invent other numbers)."""
    if not findings:
        return "(no web research findings available — write without citations)"
    lines = []
    for i, f in enumerate(findings, start=1):
        snippet = (f.get("snippet") or "").strip()
        lines.append(f"[{i}] {f.get('title', '')} — {snippet} (source: {f.get('url', '')})")
    return "\n".join(lines)


def words_from_pages(value: str | None, words_per_page: int = 500) -> int | None:
    """ "max 3 pages" → 1500. The outline node derives word budgets from page
    limits so sections land inside hard page gates (~500 words/page)."""
    import re

    if not value:
        return None
    m = re.search(r"(\d+)\s*page", value, flags=re.IGNORECASE)
    return int(m.group(1)) * words_per_page if m else None


def norm_key(key: str | None) -> str:
    return (key or "").strip().lower()
