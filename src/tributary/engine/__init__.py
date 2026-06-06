"""
Package: tributary.engine
Layer: engine
Purpose: Deterministic tax engine — triggers, thresholds, aggregation, rates, deadlines, and conflict detection. No AI calls.
Public surface: EngineRunner, AttributionStub, aggregate_entity, compute_period.
"""
from __future__ import annotations

from .attribution_stub import AttributionStub
from .aggregator import aggregate_entity
from .periods import compute_period
from .runner import EngineRunner

__all__ = ["EngineRunner", "AttributionStub", "aggregate_entity", "compute_period"]
