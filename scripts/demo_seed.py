#!/usr/bin/env python3
"""Seed the Archimedes demo project into a real Supabase project.

What it does (idempotent — safe to run repeatedly):
  1. ensures the demo login exists            demo@archimedes.dev / archimedes-demo
  2. deletes any previous demo projects for that user
  3. creates the Riverbend flood-resilience demo project owned by that user
  4. runs the FULL agent pipeline against it (MOCK_LLM fixtures by default,
     --live to spend Nebius/Tavily credits for a real run)
  5. leaves you a signed-in-ready demo: log in and open the dashboard

Usage (from the repo root):
    make seed-demo                      # offline, deterministic
    services/api/.venv/bin/python scripts/demo_seed.py --live

Requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (+ keys for --live) in .env.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "services" / "api"
sys.path.insert(0, str(API_DIR))

DEMO_EMAIL = "demo@archimedes.dev"
DEMO_PASSWORD = "archimedes-demo"
DEMO_TITLE = "Riverbend Community Flood-Resilience Network (Demo)"


def fail(message: str) -> None:
    print(f"[!] {message}")
    sys.exit(1)


def load_env() -> None:
    """Read services/api/.env (config.get_settings also does this; we need
    the raw values for the Auth admin calls, which bypass the app config)."""
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def service_client():
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        fail(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set.\n"
            "  Add them to .env (Supabase dashboard → Project Settings → API),\n"
            "  then run:  make seed-demo"
        )
    return create_client(url, key)


def anon_client():
    from supabase import create_client

    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


def ensure_demo_user(admin) -> str:
    """Return the demo user's id, creating the login if needed."""
    session = anon_client().auth.sign_in_with_password(
        {"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
    )
    if session and session.user:
        print(f"[ok] demo login exists ({DEMO_EMAIL})")
        return session.user.id

    created = admin.auth.admin.create_user(
        {"email": DEMO_EMAIL, "password": DEMO_PASSWORD, "email_confirm": True}
    )
    print(f"[ok] created demo login ({DEMO_EMAIL} / {DEMO_PASSWORD})")
    return created.user.id


def delete_previous_demos(admin, user_id: str) -> int:
    """Remove earlier demo projects (children first — explicit and boring
    beats relying on cascade definitions)."""
    rows = (
        admin.table("projects")
        .select("id")
        .eq("user_id", user_id)
        .eq("title", DEMO_TITLE)
        .execute()
        .data
    )
    for row in rows:
        pid = row["id"]
        job_ids = [
            j["id"]
            for j in admin.table("jobs")
            .select("id")
            .eq("project_id", pid)
            .execute()
            .data
        ]
        for jid in job_ids:
            admin.table("job_events").delete().eq("job_id", jid).execute()
        admin.table("jobs").delete().eq("project_id", pid).execute()
        for table in (
            "compliance_issues",
            "research_findings",
            "sections",
            "requirements",
            "documents",
        ):
            admin.table(table).delete().eq("project_id", pid).execute()
        admin.table("projects").delete().eq("id", pid).execute()
    if rows:
        print(f"[ok] removed {len(rows)} previous demo project(s)")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Archimedes demo project")
    parser.add_argument(
        "--live",
        action="store_true",
        help="use real Nebius/Tavily keys instead of fixtures",
    )
    args = parser.parse_args()

    load_env()
    admin = service_client()

    user_id = ensure_demo_user(admin)
    delete_previous_demos(admin, user_id)

    import asyncio

    from app.agent.demo_fixture import DEMO_ORG, DEMO_SOLICITATION
    from app.agent.reporter import SupabaseRunReporter
    from app.agent.runner import run_pipeline
    from app.config import get_settings
    from app.db import create_job, create_project

    project = create_project(
        user_id,
        DEMO_TITLE,
        funder_name="Community Resilience Fund",
    )
    print(f"[ok] created project {project['id']}")

    job = create_job(project["id"], "full_pipeline", "local")
    reporter = SupabaseRunReporter(job_id=job["id"], project_id=project["id"])

    settings = get_settings()
    if not args.live:
        settings = settings.model_copy(update={"mock_llm": True})

    print("→ running the agent pipeline (this takes ~5 s offline, minutes live)…")
    final_state = asyncio.run(
        run_pipeline(
            project["id"],
            job["id"],
            reporter,
            settings,
            solicitation_text=DEMO_SOLICITATION,
            org_text=DEMO_ORG,
            project_title=DEMO_TITLE,
        )
    )

    score = final_state.get("compliance_score")
    sections = [
        s for s in final_state.get("sections", {}).values() if s.get("content_md")
    ]
    findings = final_state.get("findings", [])
    print("")
    print("Demo project ready:")
    print(f"  login      {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print(f"  project    {project['id']} — “{DEMO_TITLE}”")
    print(
        f"  result     {len(sections)} sections · {len(findings)} findings · score {score}/100"
    )
    if not args.live:
        print(
            "  mode       offline fixtures (MOCK_LLM=true); use --live for a real run"
        )
    print("")
    print("Start the stack and sign in:  make api  +  make web")


if __name__ == "__main__":
    main()
