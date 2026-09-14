"""export router — GET /projects/{id}/export?format=md|docx|pdf

The Markdown is assembled from the same stored parts the agent's finalize node
uses (title + abstract + ordered sections + references from findings), so the
export always matches what the editor shows. DOCX and PDF render from that
Markdown via services/exporter.py; the PDF gets a serif cover page.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from .. import db
from ..agent.nodes.finalize import compose_final_markdown
from ..auth import User, get_current_user
from ..services.exporter import markdown_to_docx_bytes, markdown_to_pdf_bytes
from .projects import require_project

router = APIRouter(tags=["export"])


def _assemble_markdown(project: dict) -> str:
    sections = sorted(db.list_sections(project["id"]), key=lambda s: s.get("order_index", 0))
    drafted = [s for s in sections if (s.get("content_md") or "").strip()]
    if not drafted:
        raise HTTPException(
            status_code=409,
            detail="Nothing to export yet — run the agent first (Draft tab shows progress).",
        )
    findings = db.list_findings(project["id"])
    return compose_final_markdown(
        title=project.get("title") or "Grant Proposal",
        abstract=project.get("abstract") or "",
        ordered_sections=drafted,
        findings=findings,
    )


def _slug(project: dict) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in (project.get("title") or "proposal").lower())
    return "-".join(slug.split("-")[:8]).strip("-") or "proposal"


@router.get("/projects/{project_id}/export")
async def export_project(
    project_id: str,
    format: str = Query(default="md", pattern="^(md|docx|pdf)$"),
    user: User = Depends(get_current_user),
) -> Response:
    project = require_project(project_id, user)
    markdown = _assemble_markdown(project)
    slug = _slug(project)

    if format == "md":
        return Response(
            content=markdown,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{slug}.md"'},
        )
    if format == "docx":
        return Response(
            content=markdown_to_docx_bytes(
                markdown, title=project.get("title"), organization=project.get("funder_name")
            ),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{slug}.docx"'},
        )
    return Response(
        content=markdown_to_pdf_bytes(
            markdown, title=project.get("title"), organization=project.get("funder_name")
        ),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{slug}.pdf"'},
    )
