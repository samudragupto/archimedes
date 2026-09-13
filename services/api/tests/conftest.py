"""Test-wide environment. MUST run before any app import so that Settings
(pydantic-settings, env-cached) sees the offline configuration:

  * MOCK_LLM=true    → ModelRouter and TavilyService return deterministic
                       fixtures — zero credits, zero network, zero flake
  * sentinel keys    → prove code paths read the *configured* value
  * test model ids   → routing tests assert against these exact strings
"""

from __future__ import annotations

import os

os.environ.setdefault("MOCK_LLM", "true")
os.environ.setdefault("NEBIUS_API_KEY", "test-nebius-key")
os.environ.setdefault("NEBIUS_BASE_URL", "https://api.studio.nebius.com/v1/")
os.environ.setdefault("NEMOTRON_NANO_MODEL", "test/nemotron-nano")
os.environ.setdefault("NEMOTRON_SUPER_MODEL", "test/nemotron-super")
os.environ.setdefault("NEMOTRON_ULTRA_MODEL", "test/nemotron-ultra")
os.environ.setdefault("TAVILY_API_KEY", "test-tavily-key")
