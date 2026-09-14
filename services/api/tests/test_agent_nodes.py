"""Unit tests for the node-level parsing/validation helpers — the guards that
make model output safe to persist."""

from __future__ import annotations

import json

from app.agent.demo_fixture import DEMO_ORG, DEMO_SOLICITATION
from app.agent.fixtures import register
from app.agent.nodes.compliance_audit import parse_issues
from app.agent.nodes.extract_requirements import parse_requirements_json
from app.agent.nodes.finalize import compose_final_markdown
from app.agent.nodes.outline import ensure_coverage, parse_outline
from app.services.nebius_client import MOCK_FIXTURES


# ---------------------------------------------------------------------------
# extract_requirements.parse_requirements_json
# ---------------------------------------------------------------------------
def test_parse_requirements_valid_and_invalid_categories():
    raw = json.dumps(
        {
            "requirements": [
                {"category": "deadline", "key": "Due", "value": "Nov 15", "confidence": 1.2},
                {"category": "nonsense", "key": "Odd", "value": "rule"},
                {"key": "", "value": "dropped — no key"},
                {"key": "Only key"},
            ]
        }
    )
    reqs = parse_requirements_json(raw)
    assert [r.category for r in reqs] == ["deadline", "other"]
    assert reqs[0].confidence == 1.0  # clamped
    assert reqs[1].is_mandatory is True  # default
    assert len(reqs) == 2  # empty-key and value-less items dropped


def test_parse_requirements_garbage_raises():
    import pytest

    from app.services.nebius_client import JSONRepairError

    with pytest.raises(JSONRepairError):
        parse_requirements_json("no json at all")


# ---------------------------------------------------------------------------
# outline.parse_outline + ensure_coverage
# ---------------------------------------------------------------------------
def test_parse_outline_clamps_word_counts():
    content = json.dumps(
        {
            "sections": [
                {"title": "A", "target_words": 10},
                {"title": "B", "target_words": 99999},
                {"title": "", "target_words": 500},
                {"title": "C"},
            ]
        }
    )
    items = parse_outline(content)
    assert [i.title for i in items] == ["A", "B", "C"]
    assert items[0].target_words == 150  # min clamp
    assert items[1].target_words == 3000  # max clamp
    assert [i.order_index for i in items] == [1, 2, 3]


def test_ensure_coverage_appends_missing_mandatory_sections():
    items = parse_outline(
        json.dumps({"sections": [{"title": "Project Summary", "target_words": 480}]})
    )
    requirements = [
        {
            "category": "section",
            "key": "Project Summary",
            "value": "max 1 page",
            "is_mandatory": True,
        },
        {
            "category": "section",
            "key": "Evaluation Plan",
            "value": "max 2 pages",
            "is_mandatory": True,
        },
        {"category": "format", "key": "Font", "value": "11-point", "is_mandatory": True},
    ]
    items, appended = ensure_coverage(items, requirements)
    assert appended == ["Evaluation Plan"]
    assert [i.title for i in items] == ["Project Summary", "Evaluation Plan"]
    assert items[1].target_words == 1000  # derived from "max 2 pages"


def test_ensure_coverage_no_duplicates_when_covered():
    items = parse_outline(
        json.dumps(
            {
                "sections": [
                    {
                        "title": "Statement of Need",
                        "target_words": 1400,
                        "requirement_keys": ["Statement of Need"],
                    }
                ]
            }
        )
    )
    requirements = [
        {
            "category": "section",
            "key": "Statement of Need",
            "value": "max 3 pages",
            "is_mandatory": True,
        }
    ]
    items, appended = ensure_coverage(items, requirements)
    assert appended == []
    assert len(items) == 1


# ---------------------------------------------------------------------------
# compliance_audit.parse_issues
# ---------------------------------------------------------------------------
def test_parse_issues_clamps_severity_and_strips_fields():
    content = json.dumps(
        {
            "issues": [
                {
                    "severity": "CATASTROPHIC",
                    "description": "unknown severity downgraded",
                    "section_title": "  ",
                },
                {
                    "severity": "blocker",
                    "description": "missing section",
                    "section_title": "Evaluation Plan",
                    "requirement_key": "Evaluation Plan",
                    "suggested_fix": "add it",
                },
                {"description": ""},
            ]
        }
    )
    issues = parse_issues(content)
    assert len(issues) == 2  # empty description dropped
    assert issues[0]["severity"] == "minor"
    assert issues[0]["section_title"] is None  # whitespace-only → None
    assert issues[1]["severity"] == "blocker"


# ---------------------------------------------------------------------------
# finalize.compose_final_markdown
# ---------------------------------------------------------------------------
def test_compose_final_markdown_references_come_from_findings_only():
    sections = [
        {"title": "Summary", "order_index": 1, "content_md": "## Summary\n\nText [1]."},
        {"title": "Need", "order_index": 2, "content_md": "## Need\n\nMore [2]."},
    ]
    findings = [
        {"title": "Risk Atlas", "url": "https://mock.tavily.local/atlas"},
        {"title": "Lead-time Study", "url": "https://mock.tavily.local/lead"},
    ]
    md = compose_final_markdown("My Title", "A tight abstract.", sections, findings)
    assert md.startswith("# My Title")
    assert "## Abstract" in md and "A tight abstract." in md
    assert "## Table of Contents" in md and "1. Summary" in md and "2. Need" in md
    assert "[1] Risk Atlas — https://mock.tavily.local/atlas" in md
    assert "[2] Lead-time Study — https://mock.tavily.local/lead" in md
    # no findings → no references heading
    md_no_refs = compose_final_markdown("T", "A", sections, [])
    assert "## References" not in md_no_refs


# ---------------------------------------------------------------------------
# fixtures — registered, parseable, and demo texts are self-consistent
# ---------------------------------------------------------------------------
def test_fixtures_register_and_parse():
    register()
    for key in ("extract_requirements", "plan_research", "outline", "compliance_audit", "finalize"):
        assert key in MOCK_FIXTURES
        data = __import__("json").loads(MOCK_FIXTURES[key]([]))
        assert isinstance(data, dict)
    assert "draft:Project Summary" in MOCK_FIXTURES
    assert "revise:Budget and Budget Justification" in MOCK_FIXTURES
    assert MOCK_FIXTURES["draft:Statement of Need"]([]).startswith("## Statement of Need")


def test_demo_fixture_mentions_deadline_and_budget():
    assert "November 15, 2026" in DEMO_SOLICITATION
    assert "$250,000" in DEMO_SOLICITATION
    assert "501(c)(3)" in DEMO_ORG
