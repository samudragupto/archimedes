"""LangGraph definition — the ONLY place pipeline routing exists.

    START
      └─> extract_requirements (NANO)
            └─> plan_research (SUPER)
                  └─> run_research (TAVILY)
                        └─> outline (SUPER)
                              └─> draft_sections (ULTRA)
                                    └─> compliance_audit (SUPER)
                                          ├─ blockers/majors AND rounds < 2 ─> revise (ULTRA) ─> compliance_audit
                                          └─ otherwise ─> finalize (NANO) ─> END

Why a graph (and not a loop): the routing decision lives in ONE pure function
(``route_after_audit``), the state is typed, and every transition is visible in
this file — auditors and judges can verify the control flow without reading
node bodies. LangGraph also gives us resume/inspection points for free if we
later add checkpointing.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import (
    compliance_audit,
    draft_sections,
    extract_requirements,
    finalize,
    outline,
    plan_research,
    revise,
    run_research,
)
from .state import ProposalState, needs_revision

MAX_REVISION_ROUNDS = 2


def route_after_audit(state: ProposalState) -> str:
    """The conditional edge: keep revising while blocking issues remain AND we
    haven't exhausted the round budget. WHY a cap: each round costs Ultra tokens
    on every affected section — 2 rounds catches fixable drafts without ever
    rabbit-holing on an unsalvageable application (that's a human conversation,
    not an API call)."""
    if needs_revision(state.get("compliance_issues", [])) and (
        state.get("revision_round", 0) < MAX_REVISION_ROUNDS
    ):
        return "revise"
    return "finalize"


def build_graph():
    """Compile the proposal pipeline. Nodes are pure; routing lives here."""
    graph = StateGraph(ProposalState)
    graph.add_node("extract_requirements", extract_requirements)
    graph.add_node("plan_research", plan_research)
    graph.add_node("run_research", run_research)
    graph.add_node("outline", outline)
    graph.add_node("draft_sections", draft_sections)
    graph.add_node("compliance_audit", compliance_audit)
    graph.add_node("revise", revise)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "extract_requirements")
    graph.add_edge("extract_requirements", "plan_research")
    graph.add_edge("plan_research", "run_research")
    graph.add_edge("run_research", "outline")
    graph.add_edge("outline", "draft_sections")
    graph.add_edge("draft_sections", "compliance_audit")
    graph.add_conditional_edges(
        "compliance_audit",
        route_after_audit,
        {"revise": "revise", "finalize": "finalize"},
    )
    graph.add_edge("revise", "compliance_audit")  # re-audit after every round
    graph.add_edge("finalize", END)
    return graph.compile()
