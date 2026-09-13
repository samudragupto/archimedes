"""Unit tests for the ModelRouter routing table, tier params, cost model,
telemetry emission, and retry policy."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest

from app.config import Settings
from app.models.schemas import LLMTier
from app.services.nebius_client import TASK_ROUTES, ModelRouter


def make_router(client=None, emitter=None, **settings_kwargs) -> ModelRouter:
    defaults = dict(mock_llm=False, nebius_api_key="test-key")
    return ModelRouter(
        settings=Settings(**{**defaults, **settings_kwargs}), client=client, emitter=emitter
    )


def fake_response(content="hello", tokens_in=100, tokens_out=20, model="test/nemotron-nano"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=tokens_in, completion_tokens=tokens_out),
        model=model,
    )


class StubClient:
    """Records create() kwargs and replays scripted outcomes (value or exception)."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


# ---------------------------------------------------------------------------
# Routing table
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "task_type,expected_tier",
    [
        ("extraction", LLMTier.nano),
        ("classification", LLMTier.nano),
        ("formatting", LLMTier.nano),
        ("chat", LLMTier.nano),
        ("planning", LLMTier.super),
        ("audit", LLMTier.super),
        ("critique", LLMTier.super),
        ("drafting", LLMTier.ultra),
        ("revision", LLMTier.ultra),
        ("executive_summary", LLMTier.ultra),
    ],
)
def test_route_table(task_type, expected_tier):
    router = make_router()
    tier, model = router.route(task_type)
    assert tier is expected_tier
    assert model == router.settings.model_id_for_tier(tier.value)


def test_route_covers_all_documented_tasks():
    assert set(TASK_ROUTES) == {
        "extraction",
        "classification",
        "formatting",
        "chat",
        "planning",
        "audit",
        "critique",
        "drafting",
        "revision",
        "executive_summary",
    }


def test_unknown_task_type_raises():
    with pytest.raises(ValueError, match="unknown task_type"):
        make_router().route("vibes")


def test_models_come_from_env():
    settings = Settings(
        mock_llm=False,
        nebius_api_key="k",
        nemotron_nano_model="custom/nano-x",
        nemotron_super_model="custom/super-y",
        nemotron_ultra_model="custom/ultra-z",
    )
    router = ModelRouter(settings=settings)
    assert router.route("chat")[1] == "custom/nano-x"
    assert router.route("audit")[1] == "custom/super-y"
    assert router.route("drafting")[1] == "custom/ultra-z"


# ---------------------------------------------------------------------------
# Tier params + cost model
# ---------------------------------------------------------------------------
def test_nano_is_deterministic_temperature_zero():
    temp, cap = ModelRouter.params_for(LLMTier.nano)
    assert temp == 0.0
    assert cap == 4096


def test_ultra_params_match_spec():
    temp, cap = ModelRouter.params_for(LLMTier.ultra)
    assert temp == 0.4
    assert cap == 4096


def test_params_overrides_clamp_to_tier_cap():
    temp, cap = ModelRouter.params_for(LLMTier.nano, max_tokens=999_999, temperature=0.7)
    assert cap == 4096  # never exceed the tier ceiling
    assert temp == 0.7  # explicit override honored


def test_estimated_cost_tiers_are_monotonic():
    cheap = [ModelRouter.estimate_cost(t, 10_000, 5_000) for t in LLMTier]
    assert cheap[0] < cheap[1] < cheap[2]  # nano < super < ultra


# ---------------------------------------------------------------------------
# Completion (live path with injected stub client)
# ---------------------------------------------------------------------------
async def test_complete_routes_and_meters():
    stub = StubClient([fake_response()])
    emitted: list = []

    async def emitter(result):
        emitted.append(result)

    router = make_router(client=stub, emitter=emitter)
    result = await router.complete(
        "classification", [{"role": "user", "content": "classify this"}], json_mode=True
    )

    assert result.tier is LLMTier.nano
    assert result.model == "test/nemotron-nano"
    assert result.content == "hello"
    assert result.tokens_in == 100 and result.tokens_out == 20
    assert result.attempts == 1 and result.mocked is False
    assert result.estimated_cost_usd > 0

    # the stub saw the routed model + json_object response format + temp 0
    call = stub.calls[0]
    assert call["model"] == "test/nemotron-nano"
    assert call["temperature"] == 0.0
    assert call["response_format"] == {"type": "json_object"}

    assert len(emitted) == 1 and emitted[0].task_type == "classification"


async def test_ultra_drafting_call_uses_warm_temperature():
    stub = StubClient(
        [fake_response(model="test/nemotron-ultra", tokens_in=1_000, tokens_out=2_000)]
    )
    router = make_router(client=stub)
    result = await router.complete("drafting", [{"role": "user", "content": "write"}])

    assert stub.calls[0]["model"] == "test/nemotron-ultra"
    assert stub.calls[0]["temperature"] == 0.4
    assert result.tier is LLMTier.ultra


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------
def _rate_limit() -> Exception:
    req = httpx.Request("POST", "https://api.studio.nebius.com/v1/chat/completions")
    return openai.RateLimitError(
        "rate limited", response=httpx.Response(429, request=req), body=None
    )


def _bad_request() -> Exception:
    req = httpx.Request("POST", "https://api.studio.nebius.com/v1/chat/completions")
    return openai.APIStatusError("bad key", response=httpx.Response(401, request=req), body=None)


async def test_retries_on_429_then_succeeds():
    stub = StubClient([_rate_limit(), _rate_limit(), fake_response(content="third try")])
    router = make_router(
        client=stub,
        llm_retry_wait_min_seconds=0.01,
        llm_retry_wait_max_seconds=0.02,
    )
    result = await router.complete("chat", [{"role": "user", "content": "hi"}])
    assert result.content == "third try"
    assert result.attempts == 3  # two 429s, then success
    assert len(stub.calls) == 3


async def test_no_retry_on_4xx():
    stub = StubClient([_bad_request()])
    router = make_router(
        client=stub,
        llm_retry_wait_min_seconds=0.01,
        llm_retry_wait_max_seconds=0.02,
    )
    with pytest.raises(openai.APIStatusError):
        await router.complete("chat", [{"role": "user", "content": "hi"}])
    assert len(stub.calls) == 1  # fail fast — no retry on config errors


# ---------------------------------------------------------------------------
# Mock mode (MOCK_LLM=true)
# ---------------------------------------------------------------------------
async def test_mock_mode_is_deterministic_and_offline():
    settings = Settings(mock_llm=True)
    router = ModelRouter(settings=settings)
    a = await router.complete(
        "extraction", [{"role": "user", "content": "solicitation text"}], json_mode=True
    )
    b = await router.complete(
        "extraction", [{"role": "user", "content": "solicitation text"}], json_mode=True
    )
    assert a.content == b.content
    assert a.mocked and b.mocked
    assert a.tokens_in > 0 and a.tokens_out > 0
    assert a.estimated_cost_usd == 0.0  # mock runs cost nothing
    # the JSON fixture actually parses through the tolerant path
    from app.services.nebius_client import parse_llm_json

    assert parse_llm_json(a.content)["task"] == "extraction"


async def test_mock_mode_uses_fixture_registry():
    from app.services.nebius_client import MOCK_FIXTURES

    MOCK_FIXTURES["unit_test_fixture"] = lambda messages: '{"from": "registry"}'
    try:
        router = ModelRouter(settings=Settings(mock_llm=True))
        result = await router.complete(
            "extraction",
            [{"role": "user", "content": "x"}],
            json_mode=True,
            fixture_key="unit_test_fixture",
        )
        assert result.content == '{"from": "registry"}'
    finally:
        MOCK_FIXTURES.pop("unit_test_fixture", None)


async def test_missing_api_key_fails_fast_when_not_mocked():
    router = make_router(mock_llm=False, nebius_api_key="")
    with pytest.raises(RuntimeError, match="NEBIUS_API_KEY"):
        await router.complete("chat", [{"role": "user", "content": "hi"}])
