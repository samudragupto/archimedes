"""Job launching: Nebius Serverless Jobs or a local worker subprocess.

One decision, two execution paths, same worker script (``worker/main.py``):

  * ``NEBIUS_SERVERLESS_ENABLED=true`` → submit a containerized job to the
    Nebius Jobs API with ``JOB_ID`` in the environment. The worker writes all
    progress to Supabase and exits non-zero on failure, which the Jobs console
    surfaces.
  * ``LOCAL_WORKER_MODE=true`` (the laptop default) → spawn
    ``python worker/main.py`` with ``JOB_ID`` set, detached from this process
    (own session, output to a log file) so a single job outlives API reloads.

The Nebius Jobs REST endpoint/shape is centralized in ``_submit_nebius_job``
so it can be confirmed against the console docs in one place; the local path
needs nothing but the repo's own venv.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import httpx

from ..config import Settings, get_settings

API_ROOT = Path(__file__).resolve().parents[2]  # .../services/api
WORKER_SCRIPT = API_ROOT / "worker" / "main.py"
LOG_DIR = API_ROOT / "tmp"


class JobLaunchError(RuntimeError):
    """Raised when no worker path is configured or submission fails."""


def launch(job_id: str, settings: Settings | None = None) -> dict:
    """Start the worker for this job; returns {"runtime", ...detail}."""
    settings = settings or get_settings()
    if settings.nebius_serverless_enabled and settings.nebius_serverless_job_image:
        return _submit_nebius_job(job_id, settings)
    if settings.local_worker_mode:
        return _spawn_local_worker(job_id, settings)
    raise JobLaunchError(
        "no worker execution path configured — set LOCAL_WORKER_MODE=true "
        "(laptop default) or NEBIUS_SERVERLESS_ENABLED=true"
    )


# ---------------------------------------------------------------------------
# Local subprocess (the judge-on-a-laptop path)
# ---------------------------------------------------------------------------
def _spawn_local_worker(job_id: str, settings: Settings) -> dict:
    if not WORKER_SCRIPT.exists():
        raise JobLaunchError(f"worker script missing at {WORKER_SCRIPT}")
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"worker-{job_id[:8]}.log"
    env = {
        **os.environ,
        "JOB_ID": job_id,
        # the API process may have MOCK_LLM set in-process but not in env —
        # propagate it so the subprocess behaves identically
        "MOCK_LLM": str(settings.mock_llm).lower(),
    }
    log_file = open(log_path, "ab")  # child keeps the fd; we close ours
    try:
        proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
            [sys.executable, str(WORKER_SCRIPT)],
            cwd=str(API_ROOT),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # survive API restarts/reloads
        )
    finally:
        log_file.close()
    return {"runtime": "local", "pid": proc.pid, "log": str(log_path)}


# ---------------------------------------------------------------------------
# Nebius Serverless Jobs
# ---------------------------------------------------------------------------
# Worker env: only secrets/config the job needs — nothing extra crosses the wire.
_WORKER_ENV_KEYS = (
    "NEBIUS_API_KEY",
    "NEBIUS_BASE_URL",
    "NEMOTRON_NANO_MODEL",
    "NEMOTRON_SUPER_MODEL",
    "NEMOTRON_ULTRA_MODEL",
    "TAVILY_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "MOCK_LLM",
)


def _submit_nebius_job(job_id: str, settings: Settings) -> dict:
    if not settings.nebius_api_key:
        raise JobLaunchError("NEBIUS_SERVERLESS_ENABLED=true but NEBIUS_API_KEY is not set")
    if not settings.nebius_project_id:
        raise JobLaunchError("NEBIUS_SERVERLESS_ENABLED=true but NEBIUS_PROJECT_ID is not set")

    env = {"JOB_ID": job_id, "MOCK_LLM": str(settings.mock_llm).lower()}
    for key in _WORKER_ENV_KEYS:
        if os.environ.get(key):
            env[key] = os.environ[key]

    payload = {
        "project_id": settings.nebius_project_id,
        "image": settings.nebius_serverless_job_image,
        "command": ["python", "worker/main.py"],
        "env": env,
        "restart_policy": "never",
    }
    try:
        resp = httpx.post(
            settings.nebius_jobs_api_url,
            headers={"Authorization": f"Bearer {settings.nebius_api_key}"},
            json=payload,
            timeout=30,
        )
    except httpx.HTTPError as e:
        raise JobLaunchError(f"Nebius Jobs API unreachable: {e}") from e
    if resp.status_code >= 400:
        raise JobLaunchError(f"Nebius Jobs API returned HTTP {resp.status_code} for job {job_id}")
    return {"runtime": "nebius_serverless", "submission": resp.json() if resp.content else None}
