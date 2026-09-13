"""Unit tests for the Tavily service: result normalization, dedupe, mock mode,
the live-shape HTTP path (via httpx MockTransport), and the sync SDK path."""

from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.services import tavily_service as ts_module
from app.services.tavily_service import TavilyError, TavilyService, _normalize_results


# ---------------------------------------------------------------------------
# _normalize_results — the contract that keeps citations honest
# ---------------------------------------------------------------------------
def test_normalize_maps_fields():
    findings = _normalize_results(
        "q",
        [{"title": "A", "url": "https://a.example/1", "content": "snippet", "score": 0.93}],
    )
    assert findings[0].title == "A"
    assert findings[0].url == "https://a.example/1"
    assert findings[0].snippet == "snippet"
    assert findings[0].relevance == 0.93
    assert findings[0].query == "q"


def test_normalize_dedupes_by_url_keeping_first():
    findings = _normalize_results(
        "q",
        [
            {"title": "first", "url": "https://x.example/dup", "content": "one", "score": 0.9},
            {"title": "second", "url": "https://x.example/dup", "content": "two", "score": 0.8},
        ],
    )
    assert len(findings) == 1 and findings[0].title == "first"


def test_normalize_clamps_score_above_one():
    findings = _normalize_results("q", [{"title": "A", "url": "https://a/1", "score": 1.4}])
    assert findings[0].relevance == 1.0


def test_normalize_drops_entries_without_title_or_url():
    findings = _normalize_results(
        "q",
        [
            {"title": "", "url": "https://a/1", "score": 0.5},
            {"title": "B", "url": "", "score": 0.5},
            {"title": "C", "url": "https://c/3", "score": 0.5},
        ],
    )
    assert [f.title for f in findings] == ["C"]


def test_normalize_truncates_long_snippets():
    findings = _normalize_results(
        "q", [{"title": "A", "url": "https://a/1", "content": "x" * 5000, "score": 0.5}]
    )
    assert len(findings[0].snippet) <= 1200  # 1197 chars + ellipsis


# ---------------------------------------------------------------------------
# Mock mode — deterministic, zero network, unmistakably fake URLs
# ---------------------------------------------------------------------------
async def test_mock_search_is_deterministic_and_clearly_fake():
    service = TavilyService(settings=Settings(mock_llm=True))
    a = await service.search("flood sensor networks")
    b = await service.search("flood sensor networks")
    assert a == b
    assert len(a.findings) == 3
    assert all(f.url.startswith("https://mock.tavily.local/") for f in a.findings)
    assert "flood sensor networks" in a.answer
    assert (
        0.0 <= min(f.relevance for f in a.findings) <= max(f.relevance for f in a.findings) <= 1.0
    )


async def test_mock_search_respects_max_results():
    service = TavilyService(settings=Settings(mock_llm=True))
    assert len((await service.search("q", max_results=1)).findings) == 1


# ---------------------------------------------------------------------------
# Live HTTP path against a realistic Tavily payload (MockTransport)
# ---------------------------------------------------------------------------
TAVILY_PAYLOAD = {
    "answer": "Community sensing improves lead time.",
    "results": [
        {"title": "A", "url": "https://a.example/1", "content": "content a", "score": 1.4},
        {"title": "A again", "url": "https://a.example/1", "content": "dup", "score": 0.5},
        {"title": "B", "url": "https://b.example/2", "content": "content b", "score": 0.32},
    ],
}


async def test_search_posts_expected_payload_and_parses_response():
    seen: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["payload"] = request.read()
        return httpx.Response(200, json=TAVILY_PAYLOAD)

    service = TavilyService(
        settings=Settings(mock_llm=False, tavily_api_key="tv-key"),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    result = await service.search("community flood sensors", max_results=5)

    assert seen["url"] == "https://api.tavily.com/search"
    body = json.loads(seen["payload"])
    assert body["api_key"] == "tv-key"
    assert body["query"] == "community flood sensors"
    assert body["search_depth"] == "advanced"  # spec: advanced depth for the pipeline
    assert body["max_results"] == 5
    assert body["include_answer"] is True

    assert result.answer == "Community sensing improves lead time."
    assert len(result.findings) == 2  # duplicate URL dropped
    assert result.findings[0].relevance == 1.0  # clamped
    assert result.findings[1].relevance == pytest.approx(0.32)


async def test_search_http_500_raises_tavily_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    service = TavilyService(
        settings=Settings(mock_llm=False, tavily_api_key="tv-key"),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(TavilyError, match="HTTP 500"):
        await service.search("anything")


async def test_search_without_key_and_not_mocked_raises():
    service = TavilyService(settings=Settings(mock_llm=False, tavily_api_key=""))
    with pytest.raises(TavilyError, match="TAVILY_API_KEY"):
        await service.search("anything")


# ---------------------------------------------------------------------------
# Sync SDK path (official tavily-python client, used by the chat tool)
# ---------------------------------------------------------------------------
def test_search_sync_uses_official_sdk(monkeypatch):
    created: dict = {}

    class FakeTavilyClient:
        def __init__(self, api_key: str):
            created["api_key"] = api_key

        def search(self, **kwargs):
            created["kwargs"] = kwargs
            return {
                "query": kwargs["query"],
                "answer": "sync answer",
                "results": [
                    {"title": "S", "url": "https://s.example/1", "content": "c", "score": 0.5}
                ],
            }

    monkeypatch.setattr(ts_module, "TavilyClient", FakeTavilyClient)
    service = TavilyService(settings=Settings(mock_llm=False, tavily_api_key="tv-key"))
    result = service.search_sync("sync query", max_results=3)

    assert created["api_key"] == "tv-key"
    assert created["kwargs"]["query"] == "sync query"
    assert created["kwargs"]["max_results"] == 3
    assert result.answer == "sync answer"
    assert len(result.findings) == 1 and result.findings[0].title == "S"
