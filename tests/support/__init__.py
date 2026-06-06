"""
Package: tests.support
Layer: test-support (not part of the shipped package)
Purpose: Reusable test doubles that conform to the published boundary protocols, so engine
    tests can mock the graph, ingestion, and AI layers without those layers being built.
Public surface: FakeGraphReader, CollectingGraphWriter, load_golden_models.
"""
from __future__ import annotations

from .fakes import CollectingGraphWriter, FakeGraphReader, load_golden_models

__all__ = ["FakeGraphReader", "CollectingGraphWriter", "load_golden_models"]
