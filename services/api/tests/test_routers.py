"""API integration tests — real FastAPI app, real auth override, real exporter,
real ModelRouter in MOCK_LLM mode; only the Supabase data layer is faked
(monkeypatched on app.db) so no cloud is touched.

Ownership, payloads, status codes and the SSE stream are all exercised.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db as dbmod
from app.auth import User, get_current_user
from app.main import app

U1, U2 = "user-aaa1", "user-bbb2"
P1, P2 = "proj-own1", "proj-other"
S1 = "sec-budget"
I1, I2 = "issue-sec1", "issue-draft"

REQ = {
    "id": "req-1",
    "project_id": P1,
    "category": "deadline",
    "key": "Proposal deadline",
    "value": "2026-11-15 17:00 ET",
    "is_mandatory": True,
    "source_excerpt": "due Nov 15",
    "confidence": 0.99,
}
FIND = {
    "id": "find-1",
    "project_id": P1,
    "query": "flood risk",
    "title": "Risk Atlas",
    "url": "https://mock.tavily.local/atlas",
    "snippet": "92nd percentile",
    "relevance": 0.9,
    "used_in_sections": ["Statement of Need"],
}


class FakeStore:
    """In-memory stand-in for the Supabase data layer."""

    def __init__(self):
        self.projects = {
            P1: {
                "id": P1,
                "user_id": U1,
                "title": "Flood Net",
                "funder_name": "NRF",
                "status": "draft",
                "compliance_score": None,
                "abstract": None,
            },
            P2: {
                "id": P2,
                "user_id": U2,
                "title": "Other Org",
                "funder_name": None,
                "status": "draft",
                "compliance_score": None,
                "abstract": None,
            },
        }
        self.requirements = [REQ]
        self.sections = [
            {
                "id": S1,
                "project_id": P1,
                "order_index": 1,
                "title": "Budget and Budget Justification",
                "content_md": "## Budget and Budget Justification\n\nOld content.",
                "model_used": None,
                "token_count": 6,
                "status": "done",
            }
        ]
        self.issues = {
            I1: {
                "id": I1,
                "project_id": P1,
                "section_id": S1,
                "requirement_id": None,
                "severity": "major",
                "description": "No indirect-cost rate stated.",
                "suggested_fix": "State the 10% de minimis indirect rate.",
                "resolved": False,
            },
            I2: {
                "id": I2,
                "project_id": P1,
                "section_id": None,
                "requirement_id": None,
                "severity": "minor",
                "description": "Draft-wide nit.",
                "suggested_fix": "Polish it.",
                "resolved": False,
            },
        }
        self.findings = [FIND]
        self.jobs = {}
        self.job_events = {}
        self.documents = {}
        self.launch_calls: list[str] = []
        self.updated_sections: list[dict] = []

    # -- projects -----------------------------------------------------------
    def create_project(self, user_id, title, funder_name=None):
        pid = f"proj-{len(self.projects) + 1:04d}"
        row = {
            "id": pid,
            "user_id": user_id,
            "title": title,
            "funder_name": funder_name,
            "status": "draft",
            "compliance_score": None,
            "abstract": None,
        }
        self.projects[pid] = row
        return row

    def list_projects(self, user_id):
        return [p for p in self.projects.values() if p["user_id"] == user_id]

    def get_project(self, pid):
        return self.projects.get(pid)

    def update_project(self, pid, **fields):
        self.projects[pid].update(fields)
        return self.projects[pid]

    # -- aggregates -----------------------------------------------------------
    def list_requirements(self, pid):
        return [r for r in self.requirements if r["project_id"] == pid]

    def list_sections(self, pid):
        return sorted(
            (s for s in self.sections if s["project_id"] == pid), key=lambda s: s["order_index"]
        )

    def list_issues(self, pid):
        return [i for i in self.issues.values() if i["project_id"] == pid]

    def list_findings(self, pid):
        return [f for f in self.findings if f["project_id"] == pid]

    def list_jobs(self, pid):
        return [j for j in self.jobs.values() if j["project_id"] == pid]

    # -- jobs -----------------------------------------------------------------
    def create_job(self, pid, kind, runtime):
        jid = f"job-{len(self.jobs) + 1:04d}"
        row = {
            "id": jid,
            "project_id": pid,
            "kind": kind,
            "status": "queued",
            "progress": 0,
            "current_step": None,
            "error": None,
            "runtime": runtime,
        }
        self.jobs[jid] = row
        self.job_events[jid] = []
        return row

    def get_job(self, jid):
        return self.jobs.get(jid)

    def update_job(self, jid, **fields):
        self.jobs[jid].update({k: v for k, v in fields.items() if v is not None})
        return self.jobs[jid]

    def list_job_events(self, jid, since=None, limit=500):
        return self.job_events.get(jid, [])

    # -- sections / issues ------------------------------------------------------
    def get_section(self, sid):
        return next((s for s in self.sections if s["id"] == sid), None)

    def update_section(self, sid, **fields):
        section = self.get_section(sid)
        section.update(fields)
        self.updated_sections.append(section)
        return section

    def get_issue(self, iid):
        return self.issues.get(iid)

    def update_issue(self, iid, **fields):
        self.issues[iid].update(fields)
        return self.issues[iid]

    # -- documents ---------------------------------------------------------------
    def upsert_document(self, pid, kind, fields):
        did = f"doc-{len(self.documents) + 1:04d}"
        row = {"id": did, "project_id": pid, "kind": kind, **fields}
        self.documents[(pid, kind)] = row
        self.projects[pid][f"{kind}_doc_id"] = did  # mirror real pointer update
        return row


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    for name in (
        "create_project",
        "list_projects",
        "get_project",
        "update_project",
        "list_requirements",
        "list_sections",
        "list_issues",
        "list_findings",
        "list_jobs",
        "create_job",
        "get_job",
        "update_job",
        "list_job_events",
        "get_section",
        "update_section",
        "get_issue",
        "update_issue",
        "upsert_document",
    ):
        monkeypatch.setattr(dbmod, name, getattr(fake, name))
    app.dependency_overrides[get_current_user] = lambda: User(id=U1, email="u1@example.org")
    yield fake
    app.dependency_overrides.clear()


@pytest.fixture
def client(store):
    return TestClient(app)


# ---------------------------------------------------------------------------
# projects
# ---------------------------------------------------------------------------
def test_create_project_stamps_owner(client, store):
    res = client.post("/api/v1/projects", json={"title": "After-school STEM", "funder_name": "NSF"})
    assert res.status_code == 201
    assert res.json()["user_id"] == U1


def test_list_projects_is_scoped_to_owner(client, store):
    res = client.get("/api/v1/projects")
    assert [p["id"] for p in res.json()] == [P1]


def test_get_project_aggregate(client, store):
    res = client.get(f"/api/v1/projects/{P1}")
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "Flood Net"
    assert body["requirements"][0]["key"] == "Proposal deadline"
    assert body["sections"][0]["title"].startswith("Budget")
    assert body["research_findings"][0]["url"].startswith("https://mock.tavily.local/")
    assert "compliance_issues" in body and "jobs" in body


def test_other_users_project_is_404_not_403(client, store):
    assert client.get(f"/api/v1/projects/{P2}").status_code == 404


def test_anonymous_is_401():
    app.dependency_overrides.clear()
    client = TestClient(app)
    assert client.get("/api/v1/projects").status_code == 401


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------
class StubParser:
    def __init__(self, *a, **k):
        pass

    async def parse_bytes(self, filename, data):
        from app.models.schemas import Chunk, ParsedDocument

        return ParsedDocument(
            text="COMMUNITY RESILIENCE GRANTS — proposals due November 15, 2026.",
            page_count=3,
            chunks=[Chunk(index=0, text="x", token_estimate=1)],
        )


def test_upload_document_parses_and_persists(client, store, monkeypatch):
    monkeypatch.setattr("app.routers.documents.DocumentParser", StubParser)
    monkeypatch.setattr(
        "app.services.storage.upload_document",
        lambda *a, **k: f"{U1}/{P1}/solicitation/abc-rfp.pdf",
    )
    res = client.post(
        f"/api/v1/projects/{P1}/documents",
        data={"kind": "solicitation"},
        files={"file": ("rfp.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert res.status_code == 201
    body = res.json()
    assert "November 15, 2026" in body["preview"]
    assert body["document"]["page_count"] == 3
    doc = body["document"]
    assert doc["storage_path"].startswith(f"{U1}/{P1}/solicitation/")
    assert store.projects[P1]["solicitation_doc_id"] == doc["id"]


def test_upload_requires_file(client, store):
    res = client.post(f"/api/v1/projects/{P1}/documents", data={"kind": "solicitation"})
    assert res.status_code == 400


def test_upload_rejects_supporting_kind(client, store):
    res = client.post(
        f"/api/v1/projects/{P1}/documents",
        data={"kind": "supporting"},
        files={"file": ("x.txt", b"hi", "text/plain")},
    )
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# run + jobs
# ---------------------------------------------------------------------------
def test_run_creates_job_and_launches_worker(client, store, monkeypatch):
    def fake_launch(job_id, settings=None):
        store.launch_calls.append(job_id)
        return {"runtime": "local", "pid": 424242}

    monkeypatch.setattr("app.routers.jobs.launch", fake_launch)
    res = client.post(f"/api/v1/projects/{P1}/run")
    assert res.status_code == 202
    body = res.json()
    assert body["runtime"] == "local"
    assert store.launch_calls == [body["job_id"]]
    assert store.jobs[body["job_id"]]["status"] == "queued"


def test_run_on_other_users_project_404(client, store):
    assert client.post(f"/api/v1/projects/{P2}/run").status_code == 404


def test_job_status_and_events(client, store):
    job = store.create_job(P1, "full_pipeline", "local")
    store.job_events[job["id"]].append(
        {
            "id": "e1",
            "job_id": job["id"],
            "level": "info",
            "step": "outline",
            "message": "Outlined 6 sections",
        }
    )
    status_res = client.get(f"/api/v1/jobs/{job['id']}")
    assert status_res.status_code == 200 and status_res.json()["status"] == "queued"
    events = client.get(f"/api/v1/jobs/{job['id']}/events").json()
    assert events[0]["message"] == "Outlined 6 sections"


def test_job_of_other_project_404(client, store):
    job = store.create_job(P2, "full_pipeline", "local")
    assert client.get(f"/api/v1/jobs/{job['id']}").status_code == 404


# ---------------------------------------------------------------------------
# sections + compliance fix
# ---------------------------------------------------------------------------
def test_patch_section_saves_edits(client, store):
    res = client.patch(
        f"/api/v1/sections/{S1}",
        json={"content_md": "## Budget\n\nEdited by the human author."},
    )
    assert res.status_code == 200
    assert store.sections[0]["content_md"].endswith("human author.")


def test_patch_other_projects_section_404(client, store):
    store.sections[0]["project_id"] = P2
    res = client.patch(f"/api/v1/sections/{S1}", json={"content_md": "hijack"})
    assert res.status_code == 404
    store.sections[0]["project_id"] = P1


def test_fix_applies_suggested_fix_via_ultra(client, store):
    res = client.post(f"/api/v1/compliance-issues/{I1}/fix")
    assert res.status_code == 200
    body = res.json()
    assert body["issue"]["resolved"] is True
    assert body["section"]["model_used"]  # provenance recorded (mock model id)
    assert store.issues[I1]["resolved"] is True
    assert "Old content." not in store.sections[0]["content_md"]  # rewritten


def test_fix_draft_wide_issue_is_400(client, store):
    assert client.post(f"/api/v1/compliance-issues/{I2}/fix").status_code == 400


def test_fix_unknown_issue_404(client, store):
    assert client.post("/api/v1/compliance-issues/nope/fix").status_code == 404


# ---------------------------------------------------------------------------
# chat (SSE)
# ---------------------------------------------------------------------------
def test_chat_streams_sse(client, store):
    res = client.post(f"/api/v1/projects/{P1}/chat", json={"message": "When is the deadline?"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    assert res.text.count("data:") >= 2
    assert '"done": true' in res.text
    assert res.text.endswith("data: [DONE]\n\n")


def test_chat_on_other_project_404(client, store):
    res = client.post(f"/api/v1/projects/{P2}/chat", json={"message": "hi"})
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------
def test_export_markdown(client, store):
    res = client.get(f"/api/v1/projects/{P1}/export?format=md")
    assert res.status_code == 200
    assert res.text.startswith("# Flood Net")
    assert "attachment" in res.headers["content-disposition"]


def test_export_docx_and_pdf(client, store):
    docx_res = client.get(f"/api/v1/projects/{P1}/export?format=docx")
    assert docx_res.status_code == 200
    assert docx_res.content[:2] == b"PK"  # zip container

    pdf_res = client.get(f"/api/v1/projects/{P1}/export?format=pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.content[:5] == b"%PDF-"


def test_export_empty_project_is_409(client, store):
    # P1 has sections; empty the list to prove the guard fires
    sections = list(store.sections)
    store.sections.clear()
    assert client.get(f"/api/v1/projects/{P1}/export?format=md").status_code == 409
    store.sections.extend(sections)


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------
def test_health_reports_configuration():
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert set(body["models"]) == {"nano", "super", "ultra"}
    assert body["mock_llm"] is True  # conftest pins MOCK_LLM=true


# ---------------------------------------------------------------------------
# ops: unconfigured database answers 503, not 500
# ---------------------------------------------------------------------------
def test_missing_supabase_env_is_503(monkeypatch, store, client):
    from app.db import DatabaseNotConfigured

    def boom(*a, **k):
        raise DatabaseNotConfigured("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set.")

    monkeypatch.setattr(dbmod, "list_projects", boom)
    res = client.get("/api/v1/projects")
    assert res.status_code == 503
    assert "SUPABASE_URL" in res.json()["detail"]
