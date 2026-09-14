"""FastAPI routers — thin HTTP adapters over the service/db layers.

The spec fixes this exact set: projects (incl. section edits + issue fixes),
documents (uploads), jobs (run + status + events), chat (SSE), export
(md/docx/pdf) and health.
"""

from fastapi import APIRouter

from . import chat, documents, export, health, jobs, projects

api_router = APIRouter()
api_router.include_router(projects.router)
api_router.include_router(documents.router)
api_router.include_router(jobs.router)
api_router.include_router(chat.router)
api_router.include_router(export.router)
api_router.include_router(health.router)

__all__ = ["api_router"]
