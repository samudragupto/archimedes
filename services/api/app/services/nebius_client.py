"""Nebius Token Factory client + ModelRouter.

HARD CONSTRAINT: every LLM call in Archimedes goes through the Nebius Token
Factory (OpenAI-compatible API at NEBIUS_BASE_URL) using **NVIDIA open-source
Nemotron models only**. The ``openai`` SDK is used purely as a compatible
client — no OpenAI/Anthropic/Google models exist anywhere in this codebase.

ModelRouter (the class judges should read first)
------------------------------------------------
``route(task_type)`` maps a task to the cheapest Nemotron tier that can do it:

    NANO  extraction · classification · formatting · chat
          → fast & cheap, temperature 0 — deterministic JSON work
    SUPER planning   · audit   · critique
          → mid tier — structured judgment over the whole draft
    ULTRA drafting   · revision · executive_summary
          → the 253B heavy model — long-form persuasive writing

WHY routing matters: a full pipeline run makes 15–30 model calls; drafting is
<30% of the calls but >85% of the tokens. Sending extraction/audit work to
Nano/Super cuts run cost by roughly an order of magnitude versus running
everything on Ultra — the difference between "costs a few cents per grant" and
"a few dollars". Every call returns an LLMCallResult with tokens/latency/
estimated cost, logged as a job_event so the UI can prove the routing.

MOCK_LLM=true swaps in deterministic fixtures (see ``_mock_content``) so tests
and offline demos run with zero credits and zero network.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from ..config import Settings, get_settings
from ..models.schemas import LLMCallResult, LLMTier, estimate_tokens

# ---------------------------------------------------------------------------
# Task → tier routing table
# ---------------------------------------------------------------------------
TASK_ROUTES: dict[str, LLMTier] = {
    # NANO — fast/cheap, deterministic (temp 0): small in/out, structured output
    "extraction": LLMTier.nano,
    "classification": LLMTier.nano,
    "formatting": LLMTier.nano,
    "chat": LLMTier.nano,
    # SUPER — structured judgment over medium context
    "planning": LLMTier.super,
    "audit": LLMTier.super,
    "critique": LLMTier.super,
    # ULTRA — long-form generation, deep reasoning
    "drafting": LLMTier.ultra,
    "revision": LLMTier.ultra,
    "executive_summary": LLMTier.ultra,
}

# Approximate Token Factory list prices (USD per 1M tokens, input, output) —
# used ONLY for the in-app cost panel; confirm current pricing in the Nebius
# console. Order-of-magnitude correctness is what proves the routing value.
COST_PER_1M_TOKENS: dict[LLMTier, tuple[float, float]] = {
    LLMTier.nano: (0.05, 0.15),
    LLMTier.super: (0.15, 0.45),
    LLMTier.ultra: (0.60, 1.80),
}

# Per-tier sampling params (spec: NANO temp 0 · ULTRA temp 0.4 · max 4096).
# SUPER gets a light 0.2: judgment tasks benefit from a little variety, but
# audit scores must stay stable across reruns.
TIER_DEFAULTS: dict[LLMTier, tuple[float, int]] = {
    LLMTier.nano: (0.0, 4096),
    LLMTier.super: (0.2, 4096),
    LLMTier.ultra: (0.4, 4096),
}

# Optional fixture registry: Phase 3 agent nodes register deterministic
# responses under fixture keys so MOCK_LLM runs produce a realistic full
# proposal. Populated in app/agent/fixtures.py.
MOCK_FIXTURES: dict[str, Callable[[list[dict[str, str]]], str]] = {}

MetricsEmitter = Callable[[LLMCallResult], Awaitable[None]]


# ---------------------------------------------------------------------------
# Robust JSON handling (Nemotron models occasionally wrap/annotate JSON)
# ---------------------------------------------------------------------------
class JSONRepairError(ValueError):
    """Raised when a model's content cannot be repaired into parseable JSON."""


def strip_think(text: str) -> str:
    """Remove Nemotron reasoning blocks.

    WHY: Nemotron Ultra/Super emit ``<think>…</think>`` reasoning before the
    final answer. The think block itself contains braces that would wreck JSON
    extraction, so it is stripped first — everything after the LAST closing
    tag is the answer.
    """
    if "</think>" in text:
        text = text.split("</think>")[-1]
    return text.replace("<think>", "").strip()


def extract_json_block(text: str) -> str | None:
    """Return the first balanced ``{…}``/``[…]`` substring, or None.

    A small state machine (not regex) because it must ignore braces inside
    JSON strings and honor escape sequences — e.g. the model writing
    'Here is the JSON: {"a": "{brace}"} — good luck' still extracts cleanly.
    """
    start = -1
    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            if depth > 0:
                in_str = True
            continue  # quote in prose, before the JSON starts
        if ch in "{[":
            if depth == 0:
                start = i
            depth += 1
        elif ch in "}]":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


_SMART_QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'"})


def _escape_control_chars_in_strings(s: str) -> str:
    """Escape literal newlines/tabs that models sometimes emit *inside* JSON
    strings (invalid JSON, but obvious intent)."""
    out: list[str] = []
    in_str = False
    esc = False
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            elif ch == "\n":
                out.append("\\n")
                continue
            elif ch == "\r":
                out.append("\\r")
                continue
            elif ch == "\t":
                out.append("\\t")
                continue
        elif ch == '"':
            in_str = True
        out.append(ch)
    return "".join(out)


_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def repair_json(raw: str) -> str:
    """Best-effort repair of LLM JSON, tried in escalating order:

      1. code-fence extraction (```json … ```)
      2. balanced-block extraction (prose around the JSON)
      3. trailing-comma removal        — '{"a":1,}' is illegal but common
      4. smart-quote normalization     — curly quotes used as JSON delimiters
      5. escaping raw control chars inside strings
      6. single→double quotes (last resort; note in docstring: content
         containing apostrophes may be mangled, so it is tried last)

    Returns a string that ``json.loads`` accepts; raises JSONRepairError otherwise.
    """
    s = strip_think(raw or "")
    if not s.strip():
        raise JSONRepairError("cannot parse JSON from empty content")

    candidates: list[str] = []
    for fence in re.findall(r"```(?:json)?\s*(.*?)```", s, flags=re.DOTALL):
        candidates.append(fence.strip())
    block = extract_json_block(s)
    if block:
        candidates.append(block)
    candidates.append(s.strip())

    last_err: Exception | None = None
    for cand in candidates:
        # Cumulative escalation: each variant applies every fix so far, so a
        # response with trailing commas AND single quotes is fixed in one walk.
        v = cand
        variants = [v]
        v = _TRAILING_COMMA_RE.sub(r"\1", v)  # 1. trailing commas
        variants.append(v)
        v = v.translate(_SMART_QUOTES)  # 2. smart quotes as delimiters
        variants.append(v)
        v = _escape_control_chars_in_strings(v)  # 3. raw control chars in strings
        variants.append(v)
        v = v.replace("'", '"')  # 4. single quotes (last resort: may mangle
        variants.append(v)  #    content containing apostrophes)
        for variant in variants:
            try:
                json.loads(variant)
                return variant
            except json.JSONDecodeError as e:  # keep trying
                last_err = e
    raise JSONRepairError(f"cannot repair JSON: {last_err}")


def parse_llm_json(content: str) -> Any:
    """Parse a model response into Python data, tolerating think-blocks,
    fences and prose wrappers. Raises JSONRepairError (a ValueError)."""
    s = strip_think(content or "")
    if not s.strip():
        raise JSONRepairError("cannot parse JSON from empty content")
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return json.loads(repair_json(s))


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------
def _is_retryable(exc: BaseException) -> bool:
    """Retry ONLY transient failures: 429 rate limits, 5xx, timeouts/connection
    errors. A 400 (bad request) or 401 (bad key) must fail fast — retrying
    hides real config bugs from the developer."""
    if isinstance(
        exc, RateLimitError | APITimeoutError | APIConnectionError | httpx.TimeoutException
    ):
        return True
    return isinstance(exc, APIStatusError) and getattr(exc, "status_code", 0) >= 500


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------
class ModelRouter:
    """Routes tasks to Nemotron tiers, calls Nebius Token Factory, and emits
    per-call telemetry (tokens, latency, estimated cost) to an optional async
    emitter — the worker wires this to job_events so the UI can render the
    Model Router panel live."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: Any | None = None,
        emitter: MetricsEmitter | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._injected_client = client
        self._emitter = emitter

    # -- routing ------------------------------------------------------------
    def route(self, task_type: str) -> tuple[LLMTier, str]:
        """Map a task type to (tier, model id). Model ids come from env so
        newer Token Factory catalog entries are a .env change, not a code change."""
        try:
            tier = TASK_ROUTES[task_type]
        except KeyError:
            raise ValueError(
                f"unknown task_type {task_type!r}; expected one of {sorted(TASK_ROUTES)}"
            ) from None
        return tier, self.settings.model_id_for_tier(tier.value)

    @staticmethod
    def params_for(
        tier: LLMTier, max_tokens: int | None = None, temperature: float | None = None
    ) -> tuple[float, int]:
        """(temperature, max_tokens) for a tier — ULTRA caps at 4096 tokens,
        NANO runs at temperature 0 for deterministic extraction."""
        temp, cap = TIER_DEFAULTS[tier]
        return (temp if temperature is None else temperature), (
            cap if max_tokens is None else min(max_tokens, cap)
        )

    @staticmethod
    def estimate_cost(tier: LLMTier, tokens_in: int, tokens_out: int) -> float:
        pin, pout = COST_PER_1M_TOKENS[tier]
        return (tokens_in / 1_000_000) * pin + (tokens_out / 1_000_000) * pout

    # -- completion ----------------------------------------------------------
    async def complete(
        self,
        task_type: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        max_tokens: int | None = None,
        temperature: float | None = None,
        fixture_key: str | None = None,
    ) -> LLMCallResult:
        """One routed, retried, metered completion.

        ``json_mode`` requests response_format={"type":"json_object"}; content
        should then be parsed with parse_llm_json() (never bare json.loads —
        models still occasionally wrap JSON in prose or think-blocks).
        ``fixture_key`` selects a deterministic MOCK_FIXTURES entry in mock mode.
        """
        tier, model = self.route(task_type)
        temp, cap = self.params_for(tier, max_tokens=max_tokens, temperature=temperature)

        # ---- offline path: deterministic fixtures, zero network ------------
        if self.settings.mock_llm:
            t0 = time.perf_counter()
            content = self._mock_content(task_type, messages, json_mode, fixture_key)
            result = LLMCallResult(
                task_type=task_type,
                tier=tier,
                model=model,
                content=content,
                tokens_in=estimate_tokens(" ".join(str(m.get("content", "")) for m in messages)),
                tokens_out=estimate_tokens(content),
                latency_ms=max(1, int((time.perf_counter() - t0) * 1000)),
                estimated_cost_usd=0.0,
                finish_reason="stop",
                attempts=1,
                mocked=True,
            )
            await self._emit(result)
            return result

        # ---- live path: Nebius Token Factory --------------------------------
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": cap,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        t0 = time.perf_counter()
        retryer = AsyncRetrying(
            stop=stop_after_attempt(self.settings.llm_retry_attempts),
            wait=wait_exponential(
                multiplier=self.settings.llm_retry_wait_min_seconds,
                min=self.settings.llm_retry_wait_min_seconds,
                max=self.settings.llm_retry_wait_max_seconds,
            ),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )
        response: Any = await retryer(self._call_once, body)
        attempts = int(retryer.statistics.get("attempt_number", 1))

        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
        result = LLMCallResult(
            task_type=task_type,
            tier=tier,
            model=getattr(response, "model", model) or model,
            content=choice.message.content or "",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=max(1, int((time.perf_counter() - t0) * 1000)),
            estimated_cost_usd=round(self.estimate_cost(tier, tokens_in, tokens_out), 6),
            finish_reason=getattr(choice, "finish_reason", None),
            attempts=attempts,
            mocked=False,
        )
        await self._emit(result)
        return result

    async def _call_once(self, body: dict[str, Any]) -> Any:
        client = self._client()
        # max_retries=0 on the SDK: tenacity above owns retry policy so attempts
        # are counted and logged exactly once per job_event.
        return await client.chat.completions.create(**body)

    def _client(self) -> Any:
        if self._injected_client is not None:
            return self._injected_client
        if not self.settings.has_nebius_key:
            raise RuntimeError(
                "NEBIUS_API_KEY is not set. Add it to .env (or set MOCK_LLM=true "
                "to run the whole pipeline on deterministic fixtures)."
            )
        return AsyncOpenAI(
            api_key=self.settings.nebius_api_key,
            base_url=self.settings.nebius_base_url,
            timeout=self.settings.llm_timeout_seconds,
            max_retries=0,
        )

    async def _emit(self, result: LLMCallResult) -> None:
        if self._emitter is None:
            return
        try:
            await self._emitter(result)
        except Exception:  # noqa: BLE001 — telemetry must never kill a job
            pass

    # -- mock mode -------------------------------------------------------------
    def _mock_content(
        self,
        task_type: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        fixture_key: str | None,
    ) -> str:
        if fixture_key and fixture_key in MOCK_FIXTURES:
            return MOCK_FIXTURES[fixture_key](messages)
        if json_mode:
            # Shape-true generic fixture; agent fixtures (Phase 3) override it
            # per node with realistic content for the demo project.
            return json.dumps(
                {
                    "mock": True,
                    "task": task_type,
                    "requirements": [
                        {
                            "category": "deadline",
                            "key": "Mock deadline",
                            "value": "2026-12-01",
                            "is_mandatory": True,
                            "source_excerpt": "MOCK_LLM fixture — proposals are due December 1, 2026.",
                            "confidence": 0.9,
                        }
                    ],
                },
                indent=2,
            )
        last_user = next(
            (str(m.get("content", "")) for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        return f"[MOCK_LLM:{task_type}] {last_user[:180]}"
