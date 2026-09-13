"""Central configuration for the Archimedes API and worker.

One pydantic-settings object reads every variable in ``.env.example``. The API
and the worker are separate processes but MUST share these values (same
Nemotron models, same Supabase project) so that a job launched by the API
behaves identically when executed by the worker — whether that worker is a
Nebius Serverless Job container or a local subprocess.

Every field maps 1:1 to an environment variable (case-insensitive), so
``nebius_api_key`` reads ``NEBIUS_API_KEY``.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- NVIDIA Nemotron on Nebius Token Factory (ALL LLM inference) ---------
    nebius_api_key: str = ""
    nebius_base_url: str = "https://api.studio.nebius.com/v1/"
    # Model IDs are env-configured so they can be swapped to newer Token
    # Factory catalog entries without touching code. Defaults match the
    # current Nemotron open-source releases; confirm in the console catalog.
    nemotron_nano_model: str = "nvidia/Llama-3_1-Nemotron-Nano-8B-v1"
    nemotron_super_model: str = "nvidia/Llama-3_3-Nemotron-Super-49B-v1"
    nemotron_ultra_model: str = "nvidia/Llama-3_1-Nemotron-Ultra-253B-v1"

    # --- Tavily (live web research) ------------------------------------------
    tavily_api_key: str = ""

    # --- Supabase (Postgres + Storage + Realtime) ----------------------------
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""  # server-side only; bypasses RLS

    # --- worker runtime --------------------------------------------------------
    # true  → API spawns worker/main.py as a local subprocess per job
    # false → dedicated worker (compose / Nebius Serverless) polls & claims jobs
    local_worker_mode: bool = True
    nebius_serverless_enabled: bool = False
    nebius_serverless_job_image: str = ""
    nebius_project_id: str = ""

    # --- offline / test mode ---------------------------------------------------
    # Deterministic fixtures instead of live model + research calls. One switch
    # covers both LLM and Tavily so `make test` needs zero credits.
    mock_llm: bool = False

    # --- internal knobs (not in .env.example; overridable for tests) ----------
    llm_timeout_seconds: float = 120.0
    llm_retry_attempts: int = 4
    llm_retry_wait_min_seconds: float = 1.5
    llm_retry_wait_max_seconds: float = 30.0
    chunk_target_tokens: int = 6000  # solicitation chunk size (~24k chars)
    chunk_overlap_tokens: int = 200  # overlap so rules at boundaries survive
    tavily_timeout_seconds: float = 30.0

    @property
    def has_nebius_key(self) -> bool:
        return bool(self.nebius_api_key.strip())

    @property
    def has_tavily_key(self) -> bool:
        return bool(self.tavily_api_key.strip())

    def model_id_for_tier(self, tier: str) -> str:
        """Model id for a routing tier ('nano' | 'super' | 'ultra')."""
        return {
            "nano": self.nemotron_nano_model,
            "super": self.nemotron_super_model,
            "ultra": self.nemotron_ultra_model,
        }[tier]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor for long-lived processes (API, worker)."""
    return Settings()
