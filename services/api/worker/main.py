"""ARCHIMEDES worker entrypoint — one container/script, four execution modes.

    # 1. Single job (Nebius Serverless Job sets JOB_ID; the API's local-subprocess
    #    mode does the same):
    JOB_ID=<uuid> python worker/main.py

    # 2. Explicit job id:
    python worker/main.py --job-id <uuid>

    # 3. Long-lived claim loop (docker-compose `worker` service / `make worker`):
    python worker/main.py --poll

    # 4. Zero-dependency demo run on the bundled fixture (no Supabase, no keys):
    python worker/main.py --demo [--live]

Flags:
    --dry-run   force MOCK_LLM for this invocation (deterministic fixtures,
                no credits) — same effect as MOCK_LLM=true in the environment.
    --live      (with --demo) use real Nebius/Tavily keys if configured.

Exit codes: 0 success · 1 job failed · 2 configuration error.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Allow `python worker/main.py` from any CWD (worker/ is a script dir, and
# Nebius Serverless Jobs + docker set WORKDIR=/app, not /app/worker).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def run_job(job_id: str, settings) -> int:
    from app import db
    from app.agent.reporter import SupabaseRunReporter
    from app.agent.runner import run_pipeline

    job = await asyncio.to_thread(db.get_job, job_id)
    if not job:
        print(f"worker: job {job_id} not found", file=sys.stderr)
        return 2
    project_id = job["project_id"]
    reporter = SupabaseRunReporter(job_id=job_id, project_id=project_id)
    await reporter.event(
        "info",
        "worker",
        f"Worker picked up job (runtime={job.get('runtime', 'local')}, "
        f"mock={settings.mock_llm})",
    )
    try:
        final = await run_pipeline(project_id, job_id, reporter, settings)
        print(f"worker: job {job_id} succeeded · compliance {final.get('compliance_score', 0)}/100")
        return 0
    except Exception as e:  # the pipeline already traced + marked the job failed
        print(f"worker: job {job_id} failed: {e}", file=sys.stderr)
        return 1


async def poll_loop(settings) -> int:
    from app import db
    from app.agent.reporter import SupabaseRunReporter  # noqa: F401 — fail fast if unconfigured

    if db._client is None:  # touch the client factory: raise DatabaseNotConfigured early
        db._client()
    print("worker: polling for queued jobs (ctrl-c to stop)…")
    idle_pause = 0
    while True:
        job = await asyncio.to_thread(db.claim_next_queued_job)
        if job:
            idle_pause = 0
            rc = await run_job(job["id"], settings)
            if rc == 1:
                # keep the loop alive: one bad job must not kill the worker
                continue
        else:
            idle_pause += 1
            if idle_pause == 1:
                print("worker: queue empty, waiting…")
            await asyncio.sleep(2)


async def run_demo(settings, live: bool) -> int:
    from app.agent.demo_fixture import DEMO_ORG, DEMO_PROJECT_TITLE, DEMO_SOLICITATION
    from app.agent.reporter import MemoryRunReporter
    from app.agent.runner import run_pipeline

    if not live:
        settings = settings.model_copy(update={"mock_llm": True})

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  ARCHIMEDES · demo pipeline run (bundled CRPG-2026 fixture)  ║")
    print(
        f"║  mode: {'LIVE (Nebius + Tavily)' if not settings.mock_llm else 'MOCK_LLM (deterministic fixtures, no credits)':<47} ║"
    )
    print("╚══════════════════════════════════════════════════════════════╝")

    reporter = MemoryRunReporter(echo=True)
    final = await run_pipeline(
        project_id="demo-project",
        job_id="demo-job",
        reporter=reporter,
        settings=settings,
        solicitation_text=DEMO_SOLICITATION,
        org_text=DEMO_ORG,
        project_title=DEMO_PROJECT_TITLE,
    )

    drafted = sorted(
        (s for s in final.get("sections", {}).values() if s.get("content_md")),
        key=lambda s: s.get("order_index", 0),
    )
    total_calls = sum(1 for e in reporter.events if e.get("level") == "model")
    print("\n──────────────────────── summary ─────────────────────────")
    print(f"  title:            {final.get('title')}")
    print(f"  requirements:     {len(final.get('requirements', []))}")
    print(f"  research queries: {len(final.get('research_plan', []))}")
    print(f"  findings cited:   {len(final.get('findings', []))}")
    print(f"  sections drafted: {len(drafted)}/{len(final.get('sections', {}))}")
    print(
        f"  compliance score: {final.get('compliance_score')}/100 "
        f"({sum(1 for i in final.get('compliance_issues', []) if i['severity'] == 'blocker')} blockers · "
        f"{sum(1 for i in final.get('compliance_issues', []) if i['severity'] == 'major')} majors · "
        f"{sum(1 for i in final.get('compliance_issues', []) if i['severity'] == 'minor')} minors)"
    )
    print(f"  model calls:      {total_calls} · revision rounds: {final.get('revision_round')}")
    print(f"  final document:   {len(final.get('final_markdown', '').split()):,} words")
    print("───────────────────────────────────────────────────────────")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARCHIMEDES pipeline worker")
    parser.add_argument("--job-id", help="run this specific job")
    parser.add_argument("--poll", action="store_true", help="long-lived claim loop")
    parser.add_argument(
        "--demo", action="store_true", help="in-memory demo run on the bundled fixture"
    )
    parser.add_argument("--live", action="store_true", help="with --demo: use real API keys")
    parser.add_argument(
        "--dry-run", action="store_true", help="force MOCK_LLM (deterministic fixtures)"
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        os.environ["MOCK_LLM"] = "true"

    from app.agent import fixtures  # noqa: F401 — registers MOCK fixtures (idempotent)
    from app.config import get_settings

    settings = get_settings()

    try:
        if args.demo:
            return asyncio.run(run_demo(settings, live=args.live))
        if args.poll:
            return asyncio.run(poll_loop(settings))
        job_id = args.job_id or os.environ.get("JOB_ID")
        if not job_id:
            parser.error("one of --job-id, JOB_ID env, --poll or --demo is required")
        return asyncio.run(run_job(job_id, settings))
    except KeyboardInterrupt:
        print("\nworker: stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
