"""health router — configuration + optional live key validation.

``GET /health`` always answers fast: which Nemotron models are configured,
which keys are present, worker mode, mock flag. ``GET /health?deep=true``
additionally validates the Nebius and Tavily keys with one cheap live call
each (cached for 60s so dashboards can poll it).
"""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter

from ..config import get_settings

router = APIRouter(tags=["health"])

_VALIDATION_CACHE: dict = {"ts": 0.0, "data": None}
_CACHE_TTL_SECONDS = 60.0


def _validate_keys() -> dict:
    """Live validation, cached — one /models call + one 1-result Tavily search."""
    settings = get_settings()
    if settings.mock_llm:
        return {"skipped": "MOCK_LLM=true — validation would not reflect real key health"}

    nebius: dict
    try:
        resp = httpx.get(
            f"{settings.nebius_base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {settings.nebius_api_key}"},
            timeout=10,
        )
        nebius = (
            {"valid": resp.status_code == 200, "http_status": resp.status_code}
            if settings.has_nebius_key
            else {"valid": False, "reason": "key not configured"}
        )
    except httpx.HTTPError as e:
        nebius = {"valid": False, "reason": f"unreachable: {e}"}

    tavily: dict
    if not settings.has_tavily_key:
        tavily = {"valid": False, "reason": "key not configured"}
    else:
        try:
            resp = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.tavily_api_key,
                    "query": "archimedes health check",
                    "max_results": 1,
                    "search_depth": "basic",
                    "include_answer": False,
                },
                timeout=10,
            )
            tavily = {"valid": resp.status_code == 200, "http_status": resp.status_code}
        except httpx.HTTPError as e:
            tavily = {"valid": False, "reason": f"unreachable: {e}"}

    return {"nebius": nebius, "tavily": tavily}


@router.get("/health")
async def health(deep: bool = False) -> dict:
    settings = get_settings()
    payload = {
        "status": "ok",
        "mock_llm": settings.mock_llm,
        "worker": {
            "local_worker_mode": settings.local_worker_mode,
            "nebius_serverless_enabled": settings.nebius_serverless_enabled,
        },
        "models": {
            "nano": settings.nemotron_nano_model,
            "super": settings.nemotron_super_model,
            "ultra": settings.nemotron_ultra_model,
        },
        "keys": {"nebius": settings.has_nebius_key, "tavily": settings.has_tavily_key},
    }
    if deep:
        now = time.monotonic()
        if _VALIDATION_CACHE["data"] is None or now - _VALIDATION_CACHE["ts"] > _CACHE_TTL_SECONDS:
            _VALIDATION_CACHE["data"] = _validate_keys()
            _VALIDATION_CACHE["ts"] = now
        payload["validation"] = _VALIDATION_CACHE["data"]
    return payload
