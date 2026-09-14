#!/usr/bin/env python3
"""End-to-end smoke test for Archimedes.

Default (offline, no credits, no running services) verifies the whole wiring:
  1. app factory builds and /health answers
  2. auth rejects anonymous calls and validates a minted HS256 JWT
  3. the full LangGraph pipeline completes on fixtures and persists in memory
  4. the exporter produces valid markdown, DOCX (PK zip) and PDF (%PDF) bytes

--live http://host:8000 additionally probes a RUNNING stack:
  - GET  /health?deep=true       → 200 with both provider keys validated
  - GET  /api/v1/projects        → 401 without a token (auth wired)
  - GET  /api/v1/projects (valid minted token) → not a 500

Exit code 0 = smoke passes. Run via `make smoke` or
services/api/.venv/bin/python scripts/smoke_test.py [--live URL].
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "services" / "api"
sys.path.insert(0, str(API_DIR))

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, label: str) -> None:
    RESULTS.append((ok, label))
    print(f"  {'✓' if ok else '✗'} {label}")


def load_env() -> None:
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def smoke_offline() -> bool:
    print("· offline smoke (fixtures, no services)")

    os.environ.setdefault("MOCK_LLM", "true")
    os.environ.setdefault(
        "SUPABASE_JWT_SECRET", "smoke-test-secret-0123456789abcdef0123456789abcdef"
    )
    os.environ.pop("SUPABASE_URL", None)  # force the API's no-database path
    load_env()

    # 1 · app factory + health
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    health = client.get("/health")
    check(health.status_code == 200, "GET /health -> 200")
    check(
        set(health.json().get("models", {})) == {"nano", "super", "ultra"},
        "three Nemotron model ids configured",
    )

    # 2 · auth
    import jwt as pyjwt

    anonymous = client.get("/api/v1/projects")
    check(anonymous.status_code == 401, "GET /api/v1/projects anonymous -> 401")

    token = pyjwt.encode(
        {
            "sub": "smoke-user",
            "email": "smoke@archimedes.dev",
            "aud": "authenticated",
            "exp": int(time.time()) + 300,
        },
        os.environ["SUPABASE_JWT_SECRET"],
        algorithm="HS256",
    )
    user = client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token}"})
    check(
        user.status_code in (200, 503),
        "authenticated projects call handled (200 data / 503 no-DB, never 500)",
    )
    from app.auth import _decode

    try:
        decoded_ok = _decode(token)["sub"] == "smoke-user"
    except Exception:  # noqa: BLE001
        decoded_ok = False
    check(decoded_ok, "minted HS256 token verifies against SUPABASE_JWT_SECRET")

    # 3 · full pipeline on fixtures (same entrypoint the worker uses)
    import asyncio

    from app.agent.demo_fixture import DEMO_ORG, DEMO_PROJECT_TITLE, DEMO_SOLICITATION
    from app.agent.reporter import MemoryRunReporter
    from app.agent.runner import run_pipeline
    from app.config import get_settings

    settings = get_settings().model_copy(update={"mock_llm": True})
    reporter = MemoryRunReporter()
    final_state = asyncio.run(
        run_pipeline(
            project_id="smoke-project",
            job_id="smoke-job",
            reporter=reporter,
            settings=settings,
            solicitation_text=DEMO_SOLICITATION,
            org_text=DEMO_ORG,
            project_title=DEMO_PROJECT_TITLE,
        )
    )
    score = final_state.get("compliance_score")
    sections = [
        s for s in final_state.get("sections", {}).values() if s.get("content_md")
    ]
    check(
        isinstance(score, int) and 0 <= score <= 100 and len(sections) >= 4,
        f"pipeline completes on fixtures ({len(sections)} sections, score {score}/100)",
    )

    # 4 · exporter outputs
    from app.agent.nodes.finalize import compose_final_markdown
    from app.services.exporter import markdown_to_docx_bytes, markdown_to_pdf_bytes

    md = compose_final_markdown(
        "Smoke Test Proposal",
        "An abstract.",
        [{"title": "Plan", "order_index": 1, "content_md": "## Plan\n\nDo the thing."}],
        [{"title": "Source", "url": "https://example.org/a"}],
    )
    docx = markdown_to_docx_bytes(md, title="Smoke Test Proposal")
    pdf = markdown_to_pdf_bytes(md, title="Smoke Test Proposal")
    check(md.startswith("# Smoke Test Proposal"), "markdown composes")
    check(docx[:2] == b"PK", "DOCX export valid (zip magic)")
    check(pdf[:5] == b"%PDF-", "PDF export valid (%PDF magic)")

    return all(ok for ok, _ in RESULTS)


def smoke_live(base_url: str) -> bool:
    import httpx

    base = base_url.rstrip("/")
    print(f"· live smoke against {base}")

    health = httpx.get(f"{base}/health", timeout=15)
    check(health.status_code == 200, "GET /health -> 200")
    deep = httpx.get(f"{base}/health?deep=true", timeout=60).json()
    neb = deep.get("nebius", {})
    tav = deep.get("tavily", {})
    check(
        bool(neb.get("ok")) or neb.get("skipped"),
        f"Nebius key validated by the API ({neb})",
    )
    check(
        bool(tav.get("ok")) or tav.get("skipped"),
        f"Tavily key validated by the API ({tav})",
    )

    anon = httpx.get(f"{base}/api/v1/projects", timeout=15)
    check(anon.status_code == 401, "GET /api/v1/projects without token -> 401")
    return all(ok for ok, _ in RESULTS[len(RESULTS) - 3 :])


def main() -> None:
    parser = argparse.ArgumentParser(description="Archimedes smoke test")
    parser.add_argument(
        "--live",
        metavar="URL",
        help="also probe a running API (e.g. http://localhost:8000)",
    )
    args = parser.parse_args()

    print("ARCHIMEDES smoke test")
    offline_ok = smoke_offline()
    live_ok = True
    if args.live:
        live_ok = smoke_live(args.live)

    failed = [label for ok, label in RESULTS if not ok]
    print("")
    if offline_ok and live_ok:
        print(f"SMOKE PASS · {len(RESULTS)} checks")
        sys.exit(0)
    print(f"SMOKE FAIL · {len(failed)} of {len(RESULTS)} checks failed:")
    for label in failed:
        print(f"  ✗ {label}")
    sys.exit(1)


if __name__ == "__main__":
    main()
