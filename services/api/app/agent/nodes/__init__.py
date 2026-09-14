"""The 8 pipeline nodes, in execution order. Each is a pure function
(state) → partial-state; all side effects go through state["ctx"].reporter."""

from .compliance_audit import compliance_audit
from .draft_sections import draft_sections
from .extract_requirements import extract_requirements
from .finalize import finalize
from .outline import outline
from .plan_research import plan_research
from .revise import revise
from .run_research import run_research

__all__ = [
    "extract_requirements",
    "plan_research",
    "run_research",
    "outline",
    "draft_sections",
    "compliance_audit",
    "revise",
    "finalize",
]
