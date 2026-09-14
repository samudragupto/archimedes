"""Integration test: the FULL LangGraph pipeline with MOCK_LLM=true and the
in-memory reporter — the same path `worker/main.py --demo` runs.

Asserts the product contract end to end: requirements extracted and deduped,
research planned and executed, outline coverage guaranteed, all sections
drafted with citations, audit scored with the spec formula, the revise loop
running exactly to the round budget, and the finalized document assembled with
a reference list drawn only from stored findings.
"""

from __future__ import annotations

import re

import pytest

from app.agent.demo_fixture import DEMO_ORG, DEMO_PROJECT_TITLE, DEMO_SOLICITATION
from app.agent.reporter import MemoryRunReporter
from app.agent.runner import run_pipeline
from app.config import Settings


@pytest.fixture
async def run_result():
    settings = Settings(mock_llm=True)
    reporter = MemoryRunReporter(echo=False)
    final = await run_pipeline(
        project_id="test-project",
        job_id="test-job",
        reporter=reporter,
        settings=settings,
        solicitation_text=DEMO_SOLICITATION,
        org_text=DEMO_ORG,
        project_title=DEMO_PROJECT_TITLE,
    )
    return final, reporter


async def test_full_pipeline_produces_complete_proposal(run_result):
    final, _ = run_result

    # requirements: extracted, deduped, all categories present
    reqs = final["requirements"]
    assert len(reqs) >= 10
    categories = {r["category"] for r in reqs}
    assert {"deadline", "budget", "eligibility", "section", "format"} <= categories
    keys = [r["key"] for r in reqs]
    assert len(keys) == len(set(k.lower() for k in keys))  # deduped

    # research: plan executed, findings stored in citation order
    assert len(final["research_plan"]) >= 3
    assert len(final["findings"]) >= 3
    assert all(f["url"].startswith("https://mock.tavily.local/") for f in final["findings"])

    # outline: all six mandatory sections covered, in order
    titles = [item["title"] for item in final["outline"]]
    assert titles == [
        "Project Summary",
        "Statement of Need",
        "Project Design and Methodology",
        "Evaluation Plan",
        "Budget and Budget Justification",
        "Organizational Capacity",
    ]

    # draft: every section has content and provenance. Status may be "done" or
    # "needs_revision" — the mock audit's issues persist, so the FINAL audit
    # legitimately re-flags the revised section for human attention.
    assert len(final["sections"]) == 6
    for section in final["sections"].values():
        assert section["status"] in ("done", "needs_revision")
        assert section["content_md"].strip()
        assert section["model_used"]  # provenance recorded
    need = final["sections"]["Statement of Need"]["content_md"]
    assert re.search(r"\[\d\]", need)  # inline citations present


async def test_audit_scores_and_revision_loop_behave_per_spec(run_result):
    final, reporter = run_result

    # fixture audit: 1 major + 2 minors → 100 − 10 − 6 = 84
    assert len(final["compliance_issues"]) == 3
    assert final["compliance_score"] == 84

    # the revise loop ran to the round budget (issues persist in mock mode)
    assert final["revision_round"] == 2

    # issues were persisted with foreign keys resolved (section + requirement)
    persisted = reporter.issues
    assert persisted and all(i.project_id == "test-project" for i in persisted)
    assert any(i.section_id for i in persisted)
    assert any(i.requirement_id for i in persisted)


async def test_job_events_form_a_complete_trace(run_result):
    final, reporter = run_result

    steps_seen = {e["step"] for e in reporter.events}
    assert {
        "extract_requirements",
        "plan_research",
        "run_research",
        "outline",
        "draft_sections",
        "compliance_audit",
        "revise",
        "finalize",
    } <= steps_seen

    # every model event carries full metering (the Model Router panel data)
    model_events = [e for e in reporter.events if e["level"] == "model"]
    assert len(model_events) >= 15  # 14 chunk/section calls + audits + revise + finalize
    for e in model_events:
        assert e["model_used"] and e["tokens_in"] > 0 and e["tokens_out"] > 0
        assert e["latency_ms"] >= 0

    # tier routing visible in the trace
    models = {e["model_used"] for e in model_events}
    assert any("nano" in m for m in models)
    assert any("super" in m for m in models)
    assert any("ultra" in m for m in models)

    # progress monotonic, ends at 100
    assert reporter.progress == 100
    assert reporter.project_status == "complete"
    assert reporter.final_status == "succeeded"


async def test_finalize_output_assembles_exportable_document(run_result):
    final, reporter = run_result

    md = final["final_markdown"]
    assert md.startswith("# ")
    assert "## Abstract" in md and len(final["abstract"].split()) > 80
    assert "## Table of Contents" in md
    assert "## References" in md
    # references come ONLY from stored findings (citation integrity)
    ref_urls = set(re.findall(r"^\[\d\] .+ — (https://\S+)", md, flags=re.MULTILINE))
    assert ref_urls == {f["url"] for f in final["findings"]}

    # sections were persisted through the reporter as they were drafted
    assert len(reporter.sections) == 6
    assert [reporter.sections[i].title for i in sorted(reporter.sections)] == [
        item["title"] for item in final["outline"]
    ]

    # project updates include the finalize metadata
    updates = reporter.project_updates[-1]
    assert updates["title"] == final["title"]
    assert updates["abstract"] == final["abstract"]
