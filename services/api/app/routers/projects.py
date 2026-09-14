"""projects router — project CRUD, the aggregate workspace payload, section
edits (PATCH /sections/{id}) and one-click compliance fixes
(POST /compliance-issues/{id}/fix).

Ownership rule: the API uses the service-role client (RLS bypass), so every
handler re-checks that the authenticated user owns the row's project — and
returns 404 (not 403) on mismatch so row existence never leaks.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from .. import db
from ..agent.context import load_prompt, requirements_digest
from ..auth import User, get_current_user
from ..models.schemas import ComplianceIssue, ProjectCreate, Section, SectionUpdate
from ..services.nebius_client import ModelRouter, strip_think

router = APIRouter(tags=["projects"])


def require_project(project_id: str, user: User) -> dict:
    """Fetch the project and enforce ownership; 404 on any mismatch."""
    project = db.get_project(project_id)
    if not project or project.get("user_id") != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("/projects", status_code=201)
async def create_project(body: ProjectCreate, user: User = Depends(get_current_user)) -> dict:
    return db.create_project(user.id, title=body.title.strip(), funder_name=body.funder_name)


@router.get("/projects")
async def list_projects(user: User = Depends(get_current_user)) -> list[dict]:
    return db.list_projects(user.id)


@router.get("/projects/{project_id}")
async def get_project(project_id: str, user: User = Depends(get_current_user)) -> dict:
    project = require_project(project_id, user)
    # The aggregate payload the workspace tabs bind to — one round trip.
    return {
        **project,
        "requirements": db.list_requirements(project_id),
        "sections": db.list_sections(project_id),
        "compliance_issues": db.list_issues(project_id),
        "research_findings": db.list_findings(project_id),
        "jobs": db.list_jobs(project_id)[:5],
    }


# ---------------------------------------------------------------------------
# Section edits — the Draft tab's save
# ---------------------------------------------------------------------------
@router.patch("/sections/{section_id}")
async def update_section(
    section_id: str,
    body: SectionUpdate,
    user: User = Depends(get_current_user),
) -> dict:
    section = db.get_section(section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    require_project(section["project_id"], user)
    fields: dict = {"content_md": body.content_md}
    if body.title is not None:
        fields["title"] = body.title
    return db.update_section(section_id, **fields)


# ---------------------------------------------------------------------------
# One-click compliance fix — ULTRA applies the suggested fix to the section
# ---------------------------------------------------------------------------
@router.post("/compliance-issues/{issue_id}/fix")
async def fix_compliance_issue(issue_id: str, user: User = Depends(get_current_user)) -> dict:
    issue = db.get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Compliance issue not found")
    require_project(issue["project_id"], user)
    if not issue.get("section_id"):
        raise HTTPException(
            status_code=400,
            detail="This issue is draft-wide and has no single section to fix",
        )
    section = db.get_section(issue["section_id"])
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    if issue.get("resolved"):
        raise HTTPException(status_code=409, detail="Issue already resolved")

    # ULTRA revision — same prompt family as the agent's revise node, applied
    # to exactly one section with exactly one fix.
    router = ModelRouter()
    system = load_prompt("revise_section")
    fix = issue.get("suggested_fix") or issue["description"]
    user_msg = (
        f"SECTION: {section['title']}\n\n"
        f"CURRENT SECTION MARKDOWN:\n{section.get('content_md') or '(empty)'}\n\n"
        f"COMPLIANCE FIXES TO APPLY:\n- [{issue.get('severity')}] {issue['description']}\n"
        f"  FIX: {fix}"
    )
    result = await router.complete(
        "revision",  # ULTRA — a targeted persuasive rewrite
        [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
        fixture_key=f"revise:{section['title']}",
    )
    updated = db.update_section(
        section["id"],
        content_md=strip_think(result.content).strip() or section.get("content_md", ""),
        model_used=result.model,
        token_count=result.tokens_out or section.get("token_count", 0),
        status="done",
    )
    resolved = db.update_issue(issue["id"], resolved=True)
    return {
        "issue": ComplianceIssue(**{**issue, **resolved}).model_dump(),
        "section": Section(**updated).model_dump(),
        "model_used": result.model,
        "tokens_out": result.tokens_out,
    }


# ---------------------------------------------------------------------------
# Agent-run convenience: latest requirements digest for the chat UI
# ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/requirements-digest")
async def requirements_digest_endpoint(
    project_id: str, user: User = Depends(get_current_user)
) -> dict:
    require_project(project_id, user)
    return {"digest": requirements_digest(db.list_requirements(project_id))}
