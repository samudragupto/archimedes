"""RunReporter — the pipeline's only write interface.

Every side effect a node produces (trace events, progress, persisted rows,
status changes) goes through this one seam. Two implementations:

  * SupabaseRunReporter — production. Writes jobs / job_events / sections /
    requirements / research_findings / compliance_issues / projects with the
    service-role client (bypasses RLS by design; the worker is trusted).
    Blocking supabase-py calls are wrapped in asyncio.to_thread so the async
    pipeline never stalls the event loop.
  * MemoryRunReporter — tests + the CLI demo. Keeps everything in lists, and
    optionally echoes a formatted trace line to stdout so `worker/main.py
    --demo` looks like the real Agent Run console.

The pipeline emits; it never knows where the writes land.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

from ..models.schemas import ComplianceIssue, Requirement, ResearchFinding, Section

LEVEL_TAGS = {"info": "INFO", "model": "MODEL", "tool": "TOOL", "warn": "WARN", "error": "ERROR"}


def tier_label(model_used: str | None) -> str:
    """Human-facing tier for the console trace: Nano / Super / Ultra / Tavily."""
    m = (model_used or "").lower()
    if "nano" in m:
        return "NANO"
    if "super" in m:
        return "SUPER"
    if "ultra" in m:
        return "ULTRA"
    if not m:
        return "TOOL"
    return model_used or ""  # pragma: no cover — custom model ids


class RunReporter:
    """Interface + shared formatting. Subclass or replace in tests."""

    async def event(self, level: str, step: str, message: str, **metrics) -> None:
        raise NotImplementedError

    async def set_step(self, step: str, progress: int, project_status: str | None = None) -> None:
        raise NotImplementedError

    async def persist_requirements(
        self, project_id: str, requirements: list[Requirement]
    ) -> list[str]:
        return []

    async def persist_findings(self, project_id: str, findings: list[ResearchFinding]) -> None:
        return

    async def upsert_section(self, project_id: str, section: Section) -> str | None:
        return None

    async def persist_issues(self, project_id: str, issues: list[ComplianceIssue]) -> None:
        return

    async def update_project(self, project_id: str, **fields) -> None:
        return

    async def finish(self, status: str, error: str | None = None) -> None:
        return


class MemoryRunReporter(RunReporter):
    """In-memory sink for tests and `--demo`. With echo=True it prints the same
    trace the Supabase-backed Agent Run console renders."""

    def __init__(self, echo: bool = False, stream=None) -> None:
        self.echo = echo
        self.stream = stream or sys.stdout
        self.events: list[dict] = []
        self.requirements: list[Requirement] = []
        self.findings: list[ResearchFinding] = []
        self.sections: dict[int, Section] = {}
        self.issues: list[ComplianceIssue] = []
        self.project_updates: list[dict] = []
        self.progress: int = 0
        self.step: str | None = None
        self.project_status: str | None = None
        self.final_status: str | None = None
        self.final_error: str | None = None
        self._id_counter = 0

    def _next_id(self) -> str:
        self._id_counter += 1
        return f"mem-{self._id_counter:04d}"

    async def event(self, level, step, message, **metrics):
        self.events.append({"level": level, "step": step, "message": message, **metrics})
        if self.echo:
            ts = datetime.now(UTC).strftime("%H:%M:%S")
            model = metrics.get("model_used")
            badge = (
                f" {tier_label(model):<5}"
                if level == "model"
                else f" {LEVEL_TAGS.get(level, level.upper()):<5}"
            )
            tok = ""
            if metrics.get("tokens_out"):
                tok = f" · {metrics.get('tokens_in', 0)}→{metrics['tokens_out']} tok · {metrics.get('latency_ms', 0)} ms"
            print(
                f"[{ts}] {badge} [{step:<20}] {message}{tok}",
                file=self.stream,
                flush=True,
            )

    async def set_step(self, step, progress, project_status=None):
        self.step = step
        self.progress = progress
        if project_status:
            self.project_status = project_status
        if self.echo:
            ts = datetime.now(UTC).strftime("%H:%M:%S")
            filled = round(progress / 10)
            bar = "█" * filled + "░" * (10 - filled)
            print(f"[{ts}] {bar} {progress:3d}%  {step}", file=self.stream, flush=True)

    async def persist_requirements(self, project_id, requirements):
        self.requirements = list(requirements)
        ids = {}
        for r in requirements:
            if r.id is None:
                r.id = self._next_id()
            ids[r.key.strip().lower()] = r.id
        return ids

    async def persist_findings(self, project_id, findings):
        self.findings = list(findings)
        for f in findings:
            if f.id is None:
                f.id = self._next_id()

    async def upsert_section(self, project_id, section):
        key = section.order_index
        self.sections[key] = section.model_copy()
        if section.id is None:
            section.id = self.sections[key].id or self._next_id()
            self.sections[key].id = section.id
        return section.id

    async def persist_issues(self, project_id, issues):
        self.issues = [i.model_copy() for i in issues]

    async def update_project(self, project_id, **fields):
        self.project_updates.append(fields)

    async def finish(self, status, error=None):
        self.final_status = status
        self.final_error = error


class SupabaseRunReporter(RunReporter):
    """Production sink — every call lands in Supabase via the service role."""

    def __init__(self, job_id: str, project_id: str) -> None:
        from .. import db  # local import avoids a cycle at module load

        self.job_id = job_id
        self.project_id = project_id
        self.db = db

    def _run(self, fn, *args, **kwargs):
        return asyncio.to_thread(fn, *args, **kwargs)

    async def event(self, level, step, message, **metrics):
        await self._run(self.db.emit_job_event, self.job_id, level, step, message, **metrics)

    async def set_step(self, step, progress, project_status=None):
        await self._run(self.db.update_job, self.job_id, current_step=step, progress=progress)
        if project_status:
            await self._run(self.db.update_project, self.project_id, status=project_status)

    async def persist_requirements(self, project_id, requirements):
        rows, ids = await self._run(self.db.replace_requirements, project_id, requirements)
        return ids

    async def persist_findings(self, project_id, findings):
        await self._run(self.db.insert_findings, project_id, findings)

    async def upsert_section(self, project_id, section):
        return await self._run(self.db.upsert_section, project_id, section)

    async def persist_issues(self, project_id, issues):
        await self._run(self.db.replace_issues, project_id, issues)

    async def update_project(self, project_id, **fields):
        await self._run(self.db.update_project, project_id, **fields)

    async def finish(self, status, error=None):
        await self._run(
            self.db.update_job,
            self.job_id,
            status=status,
            error=error,
            progress=100 if status == "succeeded" else None,
            finished_at="now" if status in ("succeeded", "failed") else None,
        )
