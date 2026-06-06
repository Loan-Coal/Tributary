"""
Module: test_scaffold
Layer: common
Purpose: Smoke tests verifying the package scaffold imports resolve correctly.
Dependencies: tributary (all layer __init__.py files)
Used by: pytest, make test
"""
from __future__ import annotations

import importlib


def test_top_level_package_importable() -> None:
    """tributary root package must be importable."""
    mod = importlib.import_module("tributary")
    assert mod is not None


def test_layer_packages_importable() -> None:
    """All layer __init__.py stubs must be importable without errors."""
    layers = [
        "tributary.api",
        "tributary.ingestion",
        "tributary.graph",
        "tributary.rules",
        "tributary.engine",
        "tributary.ai",
        "tributary.brief",
        "tributary.prompts",
        "tributary.config",
    ]
    for layer in layers:
        mod = importlib.import_module(layer)
        assert mod is not None, f"{layer} failed to import"


def test_config_settings_importable() -> None:
    """config.settings must expose the expected constants."""
    from tributary.config import settings

    assert hasattr(settings, "NEO4J_URI")
    assert hasattr(settings, "NEO4J_USER")
    assert hasattr(settings, "NEO4J_PASSWORD")
    assert hasattr(settings, "ANTHROPIC_API_KEY")
    assert hasattr(settings, "DATA_DIR")
