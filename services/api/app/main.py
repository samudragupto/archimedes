"""FastAPI application factory — the Archimedes API.

Prefixes everything with /api/v1 (spec contract), serves /health at the root
for container health checks, and opens CORS for the Next.js frontend. All
auth happens per-route via the get_current_user dependency.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db
from .agent import fixtures  # noqa: F401 — registers MOCK fixtures for offline mode
from .config import get_settings
from .routers import api_router
from .routers import health as health_router

logger = logging.getLogger("archimedes")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Archimedes API",
        version="0.4.0",
        description=(
            "Autonomous grant-writing agent — Nebius Token Factory (NVIDIA Nemotron) "
            "+ Tavily + Supabase."
        ),
    )

    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=False,  # bearer tokens, not cookies
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(api_router, prefix="/api/v1")
    app.include_router(health_router.router)  # /health at the root (container probes)

    @app.exception_handler(db.DatabaseNotConfigured)
    async def _db_not_configured(request: Request, exc: db.DatabaseNotConfigured) -> JSONResponse:
        # Missing Supabase env is an operator problem, not a client error —
        # answer 503 with the fix instead of a 500 stack trace.
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    logger.info(
        "Archimedes API ready · nano=%s super=%s ultra=%s mock=%s",
        settings.nemotron_nano_model,
        settings.nemotron_super_model,
        settings.nemotron_ultra_model,
        settings.mock_llm,
    )
    return app


app = create_app()
