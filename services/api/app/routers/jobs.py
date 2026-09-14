"""jobs router — start a run, poll status, fetch the event stream.

POST /projects/{id}/run creates the job row (runtime chosen from settings)
and hands it to job_launcher, which either submits a Nebius Serverless Job or
spawns the local worker subprocess. The browser then subscribes to Supabase
Realtime; the two GET endpoints are the polling fallback.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import db
from ..auth import User, get_current_user
from ..config import get_settings
from ..models.schemas import JobStatus
from ..services.job_launcher import JobLaunchError, launch
from .projects import require_project

router = APIRouter(tags=["jobs"])


@router.post("/projects/{project_id}/run", status_code=202)
async def run_project(project_id: str, user: User = Depends(get_current_user)) -> dict:
    require_project(project_id, user)
    settings = get_settings()

    runtime = "nebius_serverless" if settings.nebius_serverless_enabled else "local"
    job = db.create_job(project_id, kind="full_pipeline", runtime=runtime)
    try:
        detail = launch(job["id"], settings)
    except JobLaunchError as e:
        # mark the job failed so the UI never shows a phantom queued row
        db.update_job(job["id"], status=JobStatus.failed.value, error=str(e))
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"job_id": job["id"], "runtime": runtime, "detail": detail}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, user: User = Depends(get_current_user)) -> dict:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    require_project(job["project_id"], user)
    return job


@router.get("/jobs/{job_id}/events")
async def get_job_events(
    job_id: str,
    since: str | None = Query(default=None, description="ISO timestamp; returns events after it"),
    user: User = Depends(get_current_user),
) -> list[dict]:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    require_project(job["project_id"], user)
    return db.list_job_events(job_id, since=since)
