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
NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "testpassword")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
DATA_DIR: str = os.getenv("DATA_DIR", "data")
