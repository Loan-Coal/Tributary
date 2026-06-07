"""
Module: settings
Layer: config
Purpose: Load environment configuration for Tributary.
Dependencies: python-dotenv, os
Used by: all layers that need config values
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

from tributary.common.errors import ConfigurationError

load_dotenv()

NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
# No hardcoded default — requires explicit env var or .env file.
NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
LLM_BACKEND: str = os.getenv("TRIBUTARY_LLM", "claude")
QWEN_MODEL: str = os.getenv("TRIBUTARY_QWEN_MODEL", "Qwen/Qwen3-30B-A3B-Instruct-2507")
OLLAMA_MODEL: str = os.getenv("TRIBUTARY_OLLAMA_MODEL", "qwen3:8b")
OLLAMA_BASE_URL: str = os.getenv("TRIBUTARY_OLLAMA_URL", "http://localhost:11434")
DATA_DIR: str = os.getenv("DATA_DIR", "data")
AI_ENABLED: bool = os.getenv("TRIBUTARY_AI_ENABLED", "").lower() in ("1", "true", "yes")
AI_CACHE_ONLY: bool = os.getenv("TRIBUTARY_AI_CACHE_ONLY", "").lower() in ("1", "true", "yes")
FX_LIVE: bool = os.getenv("TRIBUTARY_FX_LIVE", "").lower() in ("1", "true", "yes")
FX_CACHE_MINUTES: int = int(os.getenv("TRIBUTARY_FX_CACHE_MINUTES", "60"))


def validate() -> None:
    """Raise ConfigurationError if any required variable is absent.

    ANTHROPIC_API_KEY is only required when TRIBUTARY_LLM=claude (the default).
    Set TRIBUTARY_LLM=qwen to use a local Qwen model instead.

    Raises:
        ConfigurationError: If a required variable is missing.
    """
    required: dict[str, str] = {
        "NEO4J_URI": NEO4J_URI,
        "NEO4J_USER": NEO4J_USER,
        "NEO4J_PASSWORD": NEO4J_PASSWORD,
    }
    if LLM_BACKEND.lower() == "claude" and not AI_CACHE_ONLY:
        required["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
    missing = [name for name, val in required.items() if not val]
    if missing:
        raise ConfigurationError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Set them in your environment or a .env file."
        )
