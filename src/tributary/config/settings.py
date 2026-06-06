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

load_dotenv()

NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
# No hardcoded default — requires explicit env var or .env file.
NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
DATA_DIR: str = os.getenv("DATA_DIR", "data")


def validate() -> None:
    """Raise EnvironmentError if any required variable is absent.

    Call this at application startup (not at import time, so tests can run without
    a live Neo4j or Anthropic key).

    Raises:
        EnvironmentError: If a required variable is missing.
    """
    required = {
        "NEO4J_URI": NEO4J_URI,
        "NEO4J_USER": NEO4J_USER,
        "NEO4J_PASSWORD": NEO4J_PASSWORD,
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
    }
    missing = [name for name, val in required.items() if not val]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Set them in your environment or a .env file."
        )
