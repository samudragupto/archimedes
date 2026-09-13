"""Tavily Search API — the live-research tool behind the run_research node.

Two entry points share one normalization layer:
  * ``search()``      — async httpx call to https://api.tavily.com/search
                        (used by the agent pipeline; concurrency-limited by
                        the caller with asyncio.Semaphore)
  * ``search_sync()`` — wraps the official tavily-python SDK (used by the
                        project chat agent, which runs in a thread pool)

Contract that keeps citations honest: findings are stored ONLY from results
Tavily actually returned (title + url + snippet + score) — the drafting node
may cite ``[n]`` exclusively against these, never from model memory.
"""

from __future__ import annotations

import httpx

from ..config import Settings, get_settings
from ..models.schemas import ResearchFinding, TavilySearchResult

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# Guarded import: the sync SDK is optional at runtime (async path uses httpx),
# but it is part of the declared stack and exercised by the chat tool.
try:  # pragma: no cover - trivial import guard
    from tavily import TavilyClient
except ImportError:  # pragma: no cover
    TavilyClient = None  # type: ignore[assignment]


class TavilyError(RuntimeError):
    """Raised for missing keys, HTTP failures, or unusable responses."""


def _normalize_results(query: str, results: list[dict]) -> list[ResearchFinding]:
    """Map Tavily's raw result dicts to ResearchFinding rows.

    - dedupes by URL (Tavily sometimes returns the same page for overlapping
      queries; first/highest-scored occurrence wins)
    - clamps relevance to [0, 1] (scores occasionally exceed 1)
    - drops entries without a usable title+url — a citation with no target is
      worse than no citation
    """
    seen: set[str] = set()
    findings: list[ResearchFinding] = []
    for r in results or []:
        url = str(r.get("url") or "").strip()
        title = str(r.get("title") or "").strip()
        if not url or not title or url in seen:
            continue
        seen.add(url)
        snippet = str(r.get("content") or "").strip() or None
        if snippet and len(snippet) > 1200:
            snippet = snippet[:1197] + "…"
        score = float(r.get("score") or 0.0)
        findings.append(
            ResearchFinding(
                query=query,
                title=title,
                url=url,
                snippet=snippet,
                relevance=min(1.0, max(0.0, score)),
            )
        )
    return findings


class TavilyService:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client

    # -- async pipeline path -------------------------------------------------
    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = "advanced",
        include_answer: bool = True,
    ) -> TavilySearchResult:
        if self.settings.mock_llm:
            return self._mock_search(query, max_results)
        if not self.settings.has_tavily_key:
            raise TavilyError(
                "TAVILY_API_KEY is not set. Add it to .env (or set MOCK_LLM=true "
                "to run on deterministic fixtures)."
            )

        payload = {
            "api_key": self.settings.tavily_api_key,
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": include_answer,
        }
        client = self._http()
        try:
            resp = await client.post(TAVILY_SEARCH_URL, json=payload)
        except httpx.HTTPError as e:
            raise TavilyError(f"Tavily request failed: {e}") from e
        if resp.status_code >= 400:
            raise TavilyError(
                f"Tavily search failed (HTTP {resp.status_code}) for query: {query!r}"
            )

        data = resp.json()
        return TavilySearchResult(
            query=query,
            answer=str(data.get("answer") or ""),
            findings=_normalize_results(query, data.get("results") or []),
        )

    # -- sync SDK path (chat tool) --------------------------------------------
    def search_sync(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = "advanced",
        include_answer: bool = True,
    ) -> TavilySearchResult:
        if TavilyClient is None:
            raise TavilyError("tavily-python is not installed")
        if self.settings.mock_llm:
            return self._mock_search(query, max_results)
        if not self.settings.has_tavily_key:
            raise TavilyError("TAVILY_API_KEY is not set")
        client = TavilyClient(api_key=self.settings.tavily_api_key)
        data = client.search(
            query=query,
            search_depth=search_depth,  # type: ignore[arg-type]
            max_results=max_results,
            include_answer=include_answer,
        )
        return TavilySearchResult(
            query=query,
            answer=str(data.get("answer") or ""),
            findings=_normalize_results(query, data.get("results") or []),
        )

    # -- internals ---------------------------------------------------------------
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.settings.tavily_timeout_seconds,
                headers={"User-Agent": "Archimedes/0.2 (grant-writing agent)"},
            )
        return self._client

    @staticmethod
    def _mock_search(query: str, max_results: int) -> TavilySearchResult:
        """Deterministic fixture results under a clearly-fake host
        (mock.tavily.local) so mock-mode citations can never be mistaken for
        real, fetched sources."""
        pool = [
            (
                "Community flood-sensing networks: a review of volunteer-operated gauges",
                "https://mock.tavily.local/flood-sensing-review",
                "Peer-reviewed review of volunteer-operated gauge networks, sensor costs, and observed warning lead-time improvements in flash-flood-prone watersheds.",
                0.91,
            ),
            (
                "National risk index methodology for riverine flooding",
                "https://mock.tavily.local/nri-methodology",
                "How county-level riverine flood risk percentiles and annualized loss estimates are computed from exposure, sensitivity, and resilience factors.",
                0.84,
            ),
            (
                "Hazard mitigation planning: roles for community-based organizations",
                "https://mock.tavily.local/mitigation-guidance",
                "State and county mitigation planning requirements and the documented role of community-based organizations in outreach and warning dissemination.",
                0.77,
            ),
        ]
        findings = [
            ResearchFinding(query=query, title=t, url=u, snippet=s, relevance=score)
            for t, u, s, score in pool[: max(1, min(max_results, len(pool)))]
        ]
        return TavilySearchResult(
            query=query,
            answer=f"MOCK_LLM fixture: synthesized answer for “{query}”.",
            findings=findings,
        )
