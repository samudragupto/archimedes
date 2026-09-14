"""Deterministic MOCK_LLM fixtures for the bundled demo project (CRPG-2026 /
Riverbend). Registered into nebius_client.MOCK_FIXTURES at import time.

WHY fixtures instead of a fake model: `MOCK_LLM=true` must produce a *realistic
end-to-end product* — extraction, research plan, outline, six drafted sections,
a plausible audit, revisions and a final abstract — with zero credits and zero
network. Demo citations point at mock.tavily.local hosts so they can never be
mistaken for live research.

These fixtures are input-independent (the demo inputs are bundled too); that is
the documented trade-off for full determinism.
"""

from __future__ import annotations

import re

from ..services.nebius_client import MOCK_FIXTURES

SOLICITATION_NAME = "CRPG-2026 (mock NSF-style Community Resilience Planning Grants)"

_REQUIREMENTS = """{
  "requirements": [
    {"category": "deadline", "key": "Proposal deadline", "value": "2026-11-15 17:00 ET", "is_mandatory": true, "source_excerpt": "Proposals are due November 15, 2026, 5:00 PM ET.", "confidence": 0.99},
    {"category": "budget", "key": "Maximum total award", "value": "$250,000 in total costs for a project period of up to 24 months", "is_mandatory": true, "source_excerpt": "Up to $250,000 in total costs per award for a project period of up to 24 months.", "confidence": 0.97},
    {"category": "budget", "key": "Cost sharing", "value": "Not required", "is_mandatory": false, "source_excerpt": "Cost sharing is not required.", "confidence": 0.9},
    {"category": "eligibility", "key": "Eligible applicants", "value": "501(c)(3) non-profits, accredited institutions of higher education, state/local/tribal governments", "is_mandatory": true, "source_excerpt": "U.S. 501(c)(3) non-profit organizations, accredited institutions of higher education, and state, local, or tribal government entities may apply.", "confidence": 0.95},
    {"category": "section", "key": "Project Summary", "value": "max 1 page", "is_mandatory": true, "source_excerpt": "(a) Project Summary — max 1 page", "confidence": 0.96},
    {"category": "section", "key": "Statement of Need", "value": "max 3 pages; must include cited demographic and hazard data", "is_mandatory": true, "source_excerpt": "(b) Statement of Need — max 3 pages; must include cited demographic and hazard data", "confidence": 0.96},
    {"category": "section", "key": "Project Design and Methodology", "value": "max 6 pages", "is_mandatory": true, "source_excerpt": "(c) Project Design and Methodology — max 6 pages", "confidence": 0.95},
    {"category": "section", "key": "Evaluation Plan", "value": "max 2 pages; must define measurable outcomes", "is_mandatory": true, "source_excerpt": "(d) Evaluation Plan — max 2 pages; must define measurable outcomes", "confidence": 0.95},
    {"category": "section", "key": "Budget and Budget Justification", "value": "max 2 pages", "is_mandatory": true, "source_excerpt": "(e) Budget and Budget Justification — max 2 pages", "confidence": 0.94},
    {"category": "section", "key": "Organizational Capacity", "value": "max 2 pages", "is_mandatory": true, "source_excerpt": "(f) Organizational Capacity — max 2 pages", "confidence": 0.94},
    {"category": "format", "key": "Formatting rules", "value": "11-point font or larger, single-spaced, 1-inch margins, PDF upload", "is_mandatory": true, "source_excerpt": "11-point font or larger, single-spaced, 1-inch margins, PDF upload.", "confidence": 0.98},
    {"category": "format", "key": "Narrative page limit", "value": "16 pages across sections (a)-(f)", "is_mandatory": true, "source_excerpt": "Total narrative limit: 16 pages across sections (a)-(f).", "confidence": 0.93},
    {"category": "evaluation", "key": "Review criteria", "value": "Intellectual Merit 30%, Community Impact 30%, Feasibility and Capacity 25%, Budget Adequacy 15%", "is_mandatory": true, "source_excerpt": "Intellectual Merit (30%), Community Impact (30%), Feasibility and Capacity (25%), Budget Adequacy (15%).", "confidence": 0.94},
    {"category": "other", "key": "Reporting", "value": "quarterly progress reports and a final outcomes report within 90 days", "is_mandatory": true, "source_excerpt": "Grantees submit quarterly progress reports and a final outcomes report within 90 days of the project period end date.", "confidence": 0.92}
  ]
}"""

_QUERIES = """{
  "queries": [
    {"query": "FEMA National Risk Index Black Hawk County Iowa riverine flood risk rating", "rationale": "Statement of Need must cite hazard data; the NRI percentile is the canonical federal figure.", "target_section": "Statement of Need"},
    {"query": "community-operated flood sensor networks warning lead time improvement study", "rationale": "Evidence that the proposed methodology (dense volunteer gauges) measurably extends warning lead time.", "target_section": "Project Design and Methodology"},
    {"query": "Cedar Falls 2024 flood after action report water rescues east side neighborhoods", "rationale": "Localizes the need: documents the warning gap the project closes with the county's own data.", "target_section": "Statement of Need"}
  ]
}"""

_OUTLINE = """{
  "sections": [
    {"title": "Project Summary", "target_words": 480, "requirement_keys": ["Project Summary"]},
    {"title": "Statement of Need", "target_words": 1450, "requirement_keys": ["Statement of Need", "Review criteria"]},
    {"title": "Project Design and Methodology", "target_words": 1500, "requirement_keys": ["Project Design and Methodology"]},
    {"title": "Evaluation Plan", "target_words": 950, "requirement_keys": ["Evaluation Plan"]},
    {"title": "Budget and Budget Justification", "target_words": 900, "requirement_keys": ["Budget and Budget Justification", "Maximum total award"]},
    {"title": "Organizational Capacity", "target_words": 600, "requirement_keys": ["Organizational Capacity"]}
  ]
}"""

_DRAFTS: dict[str, str] = {
    "Project Summary": (
        "## Project Summary\n\nRiverbend Community Health Collective will deploy a low-cost, "
        "community-operated flood sensor network across four underserved neighborhoods in Cedar "
        "Falls, Iowa, converting real-time water-level data into plain-language alerts and "
        "resident-led response drills. The 24-month project pursues three objectives: (1) install "
        "and maintain 40 open-hardware sensors at flood-prone stormwater outfalls; (2) train 60 "
        'resident "flood wardens" to interpret data and run block-level response protocols; and '
        "(3) co-produce with county emergency management a data-driven evacuation playbook for the "
        "Route 955 corridor.\n\nThe project directly answers CRPG-2026's goal of community-led "
        "resilience: sensors are assembled and calibrated by local high-school robotics teams, "
        "alerts are broadcast in English, Spanish, and Bosnian, and all data publishes to an open "
        "dashboard. By month 24 we expect median neighborhood flood-alert lead time to rise from "
        "38 to at least 90 minutes, measured against National Weather Service gauge records."
    ),
    "Statement of Need": (
        "## Statement of Need\n\nCedar Falls sits at the confluence of the Cedar River and Dry Run "
        "Creek, and the neighborhoods east of Main Street flood, on average, once every three "
        "years. FEMA's National Risk Index rates Black Hawk County's riverine-flood risk in the "
        "92nd percentile nationally [1], yet county alerting depends on a single upstream gauge, "
        "giving low-lying blocks as little as 38 minutes of warning during flash events [3].\n\n"
        "The burden is not evenly shared. Census tract 153.02, where 61% of residents are renters "
        "and 34% lack a vehicle, recorded 14 of the county's 21 water-rescue calls in the 2024 "
        "flood season [3]. Renters are systematically excluded from property-level mitigation "
        "incentives.\n\nCommunity-operated sensing closes this gap: volunteer gauge networks have "
        "been shown to extend actionable lead time by 45-90 minutes — enough to move people, "
        "medications, and documents [2]. Riverbend's trusted-neighbor messenger model, proven "
        "during the 2024 response, is the delivery mechanism those extra minutes require."
    ),
    "Project Design and Methodology": (
        "## Project Design and Methodology\n\n**Phase 1 (months 1-6) — Build.** Resident advisory "
        "board selects 40 sensor sites from county stormwater models; high-school robotics teams "
        "assemble open-hardware gauges (±2 cm accuracy) and install them with city public-works "
        "support. All readings stream to an open MQTT broker and public dashboard [2].\n\n"
        "**Phase 2 (months 4-14) — Train.** Sixty residents complete a 6-hour flood-warden "
        "curriculum (data literacy, door-to-door warning, shelter logistics) in English, Spanish, "
        "and Bosnian. Each block team runs two timed drills against live high-water events.\n\n"
        "**Phase 3 (months 10-24) — Institutionalize.** Riverbend and county emergency management "
        "co-author a data-driven evacuation playbook for the Route 955 corridor, exercising it in "
        "a full-scale tabletop with schools, the food bank, and the transit authority. Quarterly "
        "community data reviews keep the network resident-governed."
    ),
    "Evaluation Plan": (
        "## Evaluation Plan\n\nThe evaluation tracks three measurable outcomes against pre-registered "
        "baselines, analyzed by our University of Northern Iowa evaluation partner.\n\n**Outcome 1 — "
        "Warning lead time.** Median neighborhood alert lead time rises from the 38-minute baseline "
        "(NWS gauge records, 2024 season) to ≥90 minutes by month 24. Source: sensor network logs "
        "cross-checked against National Weather Service gauge records.\n\n**Outcome 2 — Resident "
        "readiness.** ≥60 trained flood wardens; ≥70% of surveyed households in target blocks can "
        "state their block's alert protocol at months 12 and 24 (door-to-door survey, n≈400).\n\n"
        "**Outcome 3 — Institutional adoption.** County emergency management incorporates sensor "
        "data into its alerting workflow, evidenced by a signed memorandum and use in two activated "
        "events. Data are reviewed quarterly by the community advisory board; the design uses a "
        "stepped-wedge rollout across the four neighborhoods so later cohorts serve as comparison."
    ),
    "Budget and Budget Justification": (
        "## Budget and Budget Justification\n\nTotal request: $247,400 over 24 months, within the "
        "$250,000 ceiling.\n\n**Personnel ($118,000).** Programs Director (0.5 FTE) and Community "
        "Outreach Coordinator (1.0 FTE) manage build, training, and county coordination.\n\n"
        "**Sensor hardware ($46,800).** 40 open-hardware gauges (~$700 assembled), enclosures, "
        "spares, and telemetry — procured through the high-school robotics partnership.\n\n"
        "**Training and community operations ($38,600).** Curriculum delivery in three languages, "
        "drill logistics, resident stipends, and interpretation.\n\n**Evaluation ($22,000).** UNI "
        "partner time for the stepped-wedge analysis and survey administration.\n\n**Indirect "
        "costs ($22,000).** The 10% de minimis indirect rate applied to modified total direct "
        "costs, keeping total costs under the $250,000 ceiling.\n\nAll lines exclude cost sharing, "
        "which CRPG-2026 does not require."
    ),
    "Organizational Capacity": (
        "## Organizational Capacity\n\nRiverbend Community Health Collective is a 501(c)(3) "
        "non-profit (est. 2016) with 6 FTE staff and 40 trained resident volunteers, operating "
        "with an annual budget of $780,000. It has managed two competitive awards on time and on "
        "budget: the Iowa Watershed Approach community grant (2022-2024, $180,000) and a "
        "Wellmark Foundation healthy-communities grant (2021, $45,000).\n\nDuring the 2024 flood "
        "season Riverbend coordinated door-to-door warnings for 1,900 households in partnership "
        "with county emergency management — the exact operating model this project formalizes. "
        "The project team pairs Dr. Maya Ellison (Executive Director, 15 years in community "
        "health), T. Okafor (Programs Director), and Prof. L. Whitfield (University of Northern "
        "Iowa, evaluation lead), with fiscal controls administered under Riverbend's board-approved "
        "financial policies."
    ),
}

_AUDIT = """{
  "issues": [
    {"severity": "major", "section_title": "Budget and Budget Justification", "requirement_key": "Maximum total award", "description": "The budget justification does not state which indirect-cost rate is applied; reviewers cannot verify total costs stay under the $250,000 ceiling.", "suggested_fix": "Add a line item stating the 10% de minimis indirect rate applied to modified total direct costs, with the resulting dollar amount."},
    {"severity": "minor", "section_title": "Statement of Need", "requirement_key": "Statement of Need", "description": "The tract-level statistics paragraph runs long for the 3-page limit once citations render; it would read better as an appendix table.", "suggested_fix": "Tighten the Statement of Need to ≤ 750 words and move the tract statistics block to Appendices as a table."},
    {"severity": "minor", "section_title": "Project Summary", "requirement_key": "Review criteria", "description": "The summary does not explicitly answer the Community Impact criterion (30% of the score) with a measurable figure.", "suggested_fix": "Add one sentence quantifying protected households (e.g. '1,900 households in four neighborhoods gain ≥90 minutes of actionable warning')."}
  ]
}"""

_FINALIZE = """{
  "title": "Community Flood-Sensor Network and Resident Response Program for Cedar Falls, Iowa",
  "abstract": "East Cedar Falls floods roughly every three years, yet residents receive as little as 38 minutes of warning because county alerting relies on a single upstream gauge — and 2024 flood-season data show the burden concentrates in renter-majority tracts that property-level mitigation programs miss. Riverbend Community Health Collective, a 501(c)(3) with a proven resident-messenger model, will deploy 40 community-operated flood sensors, train 60 resident flood wardens, and co-author a data-driven evacuation playbook with county emergency management over 24 months. Using a stepped-wedge design analyzed by a university evaluation partner, the project targets a rise in median warning lead time from 38 to at least 90 minutes, verified against National Weather Service records, and county adoption of sensor feeds in official alerting — a replicable model for resident-owned resilience."
}"""


def _revise_fixture(section_title: str):
    """Revision fixture: deterministic 'apply the fixes' behavior.

    For the Budget section the fixture returns the corrected draft (indirect
    costs stated). For any other title it returns the same section's draft
    content with the fixes echoed as a closing line — clearly deterministic,
    visibly a revision.
    """
    fixed = _DRAFTS.get(section_title, "")

    def _fn(messages):
        if section_title == "Budget and Budget Justification":
            return fixed  # the corrected version above already states the rate
        m = re.search(
            r"CURRENT SECTION MARKDOWN:\n(.*?)\n\nCOMPLIANCE FIXES", str(messages), re.DOTALL
        )
        current = m.group(1).strip() if m else ""
        return (
            current
            + "\n\n**Revision note (applied fixes).** Reviewer-flagged compliance items in this "
            "section have been addressed: the flagged language was tightened and any missing "
            "element required by the solicitation is now stated explicitly."
        )

    return _fn


def register() -> None:
    """Idempotently register all demo fixtures into the ModelRouter."""
    MOCK_FIXTURES["extract_requirements"] = lambda messages: _REQUIREMENTS
    MOCK_FIXTURES["plan_research"] = lambda messages: _QUERIES
    MOCK_FIXTURES["outline"] = lambda messages: _OUTLINE
    MOCK_FIXTURES["compliance_audit"] = lambda messages: _AUDIT
    MOCK_FIXTURES["finalize"] = lambda messages: _FINALIZE
    for title, content in _DRAFTS.items():
        MOCK_FIXTURES[f"draft:{title}"] = (lambda c: lambda messages: c)(content)
    for title in _DRAFTS:
        MOCK_FIXTURES[f"revise:{title}"] = _revise_fixture(title)


register()
