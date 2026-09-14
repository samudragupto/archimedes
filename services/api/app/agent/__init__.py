"""Agent orchestration — a LangGraph state machine that turns a solicitation +
org profile into a compliant, researched, fully-drafted grant proposal.

Module map (read in this order):
    state.py     ProposalState TypedDict + pure scoring helpers
    context.py   PipelineContext (settings, router, tavily, reporter) + prompts
    reporter.py  event/progress sinks: Supabase (production) or in-memory (tests/CLI)
    fixtures.py  deterministic MOCK_LLM fixtures for the demo project
    demo_fixture.py  original CRPG-2026 solicitation + Riverbend org profile
    nodes/       the 8 pure node functions (one per pipeline stage)
    graph.py     the LangGraph wiring (the ONLY place that defines routing)
    runner.py    loads inputs, invokes the graph, marks the job done/failed
"""
