"""Unit tests for compliance scoring (the spec formula, as a pure function)
and the revision-target selection used by the graph's conditional edge."""

from __future__ import annotations

from app.agent.graph import MAX_REVISION_ROUNDS, route_after_audit
from app.agent.nodes.revise import revision_targets
from app.agent.state import compute_compliance_score, count_by_severity, needs_revision


def issue(severity: str, section: str | None = None) -> dict:
    return {"severity": severity, "section_title": section, "description": "x"}


# ---------------------------------------------------------------------------
# compute_compliance_score — 100 − (blockers·25 + majors·10 + minors·3), 0–100
# ---------------------------------------------------------------------------
def test_clean_draft_scores_100():
    assert compute_compliance_score([]) == 100


def test_weights_match_spec():
    assert compute_compliance_score([issue("blocker")]) == 75
    assert compute_compliance_score([issue("major")]) == 90
    assert compute_compliance_score([issue("minor")]) == 97


def test_audit_scenario_scores_84():
    # 1 major · 2 minors → the exact score of the bundled demo audit
    # (and of the finished demo project in supabase/seed.sql)
    issues = [issue("major"), issue("minor"), issue("minor")]
    assert compute_compliance_score(issues) == 84


def test_score_clamps_at_zero():
    assert compute_compliance_score([issue("blocker")] * 5) == 0


def test_count_by_severity_ignores_unknown_severities():
    counts = count_by_severity([issue("blocker"), issue("catastrophic"), {"severity": None}])
    assert counts == {"blocker": 1, "major": 0, "minor": 0}


# ---------------------------------------------------------------------------
# needs_revision — the audit→revise gate
# ---------------------------------------------------------------------------
def test_needs_revision_true_only_for_blockers_or_majors():
    assert needs_revision([issue("blocker")]) is True
    assert needs_revision([issue("major")]) is True
    assert needs_revision([issue("minor"), issue("minor")]) is False
    assert needs_revision([]) is False


# ---------------------------------------------------------------------------
# revision_targets — only sections referenced by blocker/major issues
# ---------------------------------------------------------------------------
SECTIONS = {
    "A": {"title": "A", "order_index": 1},
    "B": {"title": "B", "order_index": 2},
    "C": {"title": "C", "order_index": 3},
}


def test_revision_targets_only_blocking_sections_in_outline_order():
    issues = [
        issue("minor", "A"),
        issue("major", "C"),
        issue("blocker", "A"),
        issue("minor", "B"),
        issue("major", "Missing Section"),
    ]
    assert revision_targets(issues, SECTIONS) == ["A", "C"]


def test_revision_targets_empty_when_only_minors():
    assert revision_targets([issue("minor", "A")], SECTIONS) == []


# ---------------------------------------------------------------------------
# route_after_audit — the graph's conditional edge
# ---------------------------------------------------------------------------
def make_state(issues: list[dict], rounds: int) -> dict:
    return {"compliance_issues": issues, "revision_round": rounds}


def test_routes_to_revise_when_blocking_and_rounds_remain():
    assert route_after_audit(make_state([issue("major")], 0)) == "revise"
    assert route_after_audit(make_state([issue("blocker")], 1)) == "revise"


def test_routes_to_finalize_when_round_budget_exhausted():
    assert route_after_audit(make_state([issue("major")], MAX_REVISION_ROUNDS)) == "finalize"
    assert route_after_audit(make_state([issue("blocker")], 99)) == "finalize"


def test_routes_to_finalize_when_only_minors():
    assert route_after_audit(make_state([issue("minor")], 0)) == "finalize"


def test_round_budget_is_two():
    assert MAX_REVISION_ROUNDS == 2
