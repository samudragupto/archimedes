"""chat router — streaming SSE Q&A about a project.

Pipeline (all Nano — chat is cheap by design):
  1. a json_mode "classification" call decides whether the question needs web
     data beyond the project context;
  2. if it does, Tavily runs (sync SDK in a thread) and the results join the
     context as numbered sources;
  3. the final answer streams token-by-token as SSE `data:` frames.

Grounding rules live in prompts/chat.md: quote requirement values exactly,
cite only provided findings, never invent numbers.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from .. import db
from ..agent import fixtures  # noqa: F401 — registers MOCK fixtures
from ..agent.context import findings_block, requirements_digest
from ..auth import User, get_current_user
from ..models.schemas import ChatRequest
from ..services.nebius_client import ModelRouter, parse_llm_json
from ..services.tavily_service import TavilyService
from .projects import require_project

router = APIRouter(tags=["chat"])

# Per-source truncation keeps the prompt bounded regardless of draft size.
_SECTION_CHARS = 1400
_MAX_SECTIONS_IN_CONTEXT = 12


def build_project_context(project_id: str) -> str:
    requirements = db.list_requirements(project_id)
    sections = sorted(db.list_sections(project_id), key=lambda s: s.get("order_index", 0))
    findings = db.list_findings(project_id)

    parts = [
        "PROJECT REQUIREMENTS:\n" + requirements_digest(requirements),
        "RESEARCH FINDINGS (numbered for citation):\n" + findings_block(findings),
        "PROPOSAL DRAFT:",
    ]
    for section in sections[:_MAX_SECTIONS_IN_CONTEXT]:
        content = (section.get("content_md") or "(not drafted yet)")[:_SECTION_CHARS]
        parts.append(f"### {section['title']}\n{content}")
    return "\n\n".join(parts)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/projects/{project_id}/chat")
async def chat(
    project_id: str,
    body: ChatRequest,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    require_project(project_id, user)
    context = build_project_context(project_id)
    model_router = ModelRouter()
    tavily = TavilyService()

    async def generate():
        # -- step 1: does this need the web? (Nano, json) -------------------
        decision = await model_router.complete(
            "classification",  # NANO — cheap gate before any web spend
            [
                {
                    "role": "system",
                    "content": (
                        "Decide if answering the user's question about this grant project "
                        "requires LIVE web data (current statistics, regulations, facts not "
                        'in the context). Return JSON: {"needs_web": bool, "search_query": '
                        "str|null}. Return {'needs_web': false} whenever the provided context "
                        "or findings suffice."
                    ),
                },
                {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {body.message}"},
            ],
            json_mode=True,
            fixture_key="chat_decision",
        )
        try:
            plan = parse_llm_json(decision.content)
            needs_web = bool(plan.get("needs_web")) and not decision.mocked
        except Exception:  # noqa: BLE001 — a broken gate must not break chat
            needs_web = False

        # -- step 2 (optional): Tavily as a tool ----------------------------
        web_block = ""
        if needs_web and isinstance(plan, dict) and plan.get("search_query"):
            query = str(plan["search_query"])[:300]
            try:
                result = await asyncio.to_thread(
                    tavily.search_sync, query, max_results=4, search_depth="basic"
                )
                web_block = f"LIVE WEB RESULTS for “{query}” (cite as [W1], [W2] …):\n" + "\n".join(
                    f"[W{i}] {f.title} — {(f.snippet or '')[:300]} ({f.url})"
                    for i, f in enumerate(result.findings, start=1)
                )
            except Exception as e:  # noqa: BLE001 — research failure ≠ chat failure
                web_block = f"(web search failed: {e})"

        # -- step 3: stream the grounded answer ------------------------------
        messages = [
            {"role": "system", "content": await asyncio.to_thread(_load_chat_prompt)},
            {
                "role": "user",
                "content": f"PROJECT CONTEXT:\n{context}"
                + (f"\n\n{web_block}" if web_block else "")
                + f"\n\nQUESTION: {body.message}",
            },
        ]
        async for delta, meta in model_router.stream("chat", messages, fixture_key="chat_answer"):
            if delta:
                yield _sse({"delta": delta})
            if meta:
                yield _sse(
                    {
                        "done": True,
                        "model": meta.model,
                        "tokens_in": meta.tokens_in,
                        "tokens_out": meta.tokens_out,
                        "latency_ms": meta.latency_ms,
                        "needs_web": needs_web,
                    }
                )
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _load_chat_prompt() -> str:
    from ..agent.context import load_prompt

    return load_prompt("chat")
