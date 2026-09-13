"""Unit tests for requirement dedupe (overlapping extraction chunks produce
near-duplicate rules; the merged checklist must be clean and stable)."""

from __future__ import annotations

from app.models.schemas import Requirement, RequirementCategory, dedupe_requirements


def req(
    key: str,
    value: str,
    *,
    category: RequirementCategory = RequirementCategory.section,
    confidence: float = 0.8,
    excerpt: str | None = None,
    mandatory: bool = True,
) -> Requirement:
    return Requirement(
        key=key,
        value=value,
        category=category,
        confidence=confidence,
        source_excerpt=excerpt,
        is_mandatory=mandatory,
    )


def test_empty_input():
    assert dedupe_requirements([]) == []


def test_exact_duplicates_merge():
    out = dedupe_requirements([req("Page limit", "16 pages"), req("Page limit", "16 pages")])
    assert len(out) == 1
    assert out[0].value == "16 pages"


def test_containment_values_merge():
    out = dedupe_requirements(
        [
            req("Narrative limit", "16 pages"),
            req("Narrative limit", "16 pages across sections (a)-(f)"),
        ]
    )
    assert len(out) == 1
    # the higher-information (longer) value is not chosen arbitrarily: the
    # winner is the higher-confidence row — set equal confidence here, so the
    # first occurrence wins.
    assert out[0].value == "16 pages"


def test_higher_confidence_duplicate_wins():
    out = dedupe_requirements(
        [
            req("Deadline", "November 15, 2026", confidence=0.7),
            req("Deadline", "November 15, 2026", confidence=0.99),
        ]
    )
    assert len(out) == 1
    assert out[0].confidence == 0.99


def test_source_excerpt_is_preserved_from_first_seen():
    out = dedupe_requirements(
        [
            req("Deadline", "Nov 15 2026", excerpt="Proposals are due November 15, 2026."),
            req("Deadline", "Nov 15 2026", excerpt="Late proposals will not be reviewed."),
        ]
    )
    assert out[0].source_excerpt == "Proposals are due November 15, 2026."


def test_normalization_merges_case_and_punctuation_variants():
    out = dedupe_requirements([req("Page Limit:", "16 pages"), req("page limit", "16 PAGES")])
    assert len(out) == 1


def test_different_categories_do_not_merge():
    out = dedupe_requirements(
        [
            req("Limit", "16 pages", category=RequirementCategory.format),
            req("Limit", "16 pages", category=RequirementCategory.budget),
        ]
    )
    assert len(out) == 2


def test_different_values_same_key_do_not_merge():
    out = dedupe_requirements(
        [req("Font size", "11-point minimum"), req("Font size", "12-point preferred")]
    )
    assert len(out) == 2


def test_first_seen_order_is_preserved():
    out = dedupe_requirements(
        [
            req("Deadline", "Nov 15", category=RequirementCategory.deadline),
            req("Award", "$250,000", category=RequirementCategory.budget),
            req("PAGE LIMIT", "16 pages"),
            req("Page limit", "16 pages"),
        ]
    )
    assert [r.key for r in out] == ["Deadline", "Award", "PAGE LIMIT"]


def test_short_values_require_exact_match():
    # '1 page' vs '2 pages' must never containment-merge just because one is
    # short — the ≥6-char guard applies to the *contained* string only, and
    # neither contains the other here anyway.
    out = dedupe_requirements([req("Summary", "1 page"), req("Summary", "2 pages")])
    assert len(out) == 2


def test_overlapping_chunks_scenario_end_to_end():
    """The realistic case: chunk 1 and chunk 2 both see the same rules with
    slightly different extraction wording."""
    chunk1 = [
        req(
            "Proposal deadline",
            "November 15, 2026 5:00 PM ET",
            category=RequirementCategory.deadline,
            confidence=0.98,
            excerpt="Proposals are due November 15, 2026, 5:00 PM ET.",
        ),
        req(
            "Required sections",
            "six sections with page limits",
            category=RequirementCategory.section,
            confidence=0.9,
        ),
    ]
    chunk2 = [
        req(
            "proposal deadline",
            "November 15, 2026",
            category=RequirementCategory.deadline,
            confidence=0.95,
        ),
        req(
            "Required Sections",
            "six sections",
            category=RequirementCategory.section,
            confidence=0.85,
        ),
        req(
            "Formatting",
            "11-point font, single-spaced",
            category=RequirementCategory.format,
            confidence=0.97,
        ),
    ]
    out = dedupe_requirements(chunk1 + chunk2)
    assert len(out) == 3
    assert out[0].confidence == 0.98  # best-confidence duplicate kept
    assert out[0].source_excerpt.startswith("Proposals are due")
