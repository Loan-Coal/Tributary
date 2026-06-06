"""
Module: errors
Layer: common
Purpose: Custom exception hierarchy for all Tributary domain errors.
Dependencies: none
Used by: all layers
"""
from __future__ import annotations


class TributaryError(Exception):
    """Base exception for all Tributary domain errors."""


# ---------------------------------------------------------------------------
# Graph layer errors
# ---------------------------------------------------------------------------


class GraphError(TributaryError):
    """Base for graph layer errors."""


class EntityNotFoundError(GraphError):
    """Raised when get_entity() finds no record for the requested entity_id."""


class CounterpartyNotFoundError(GraphError):
    """Raised when get_counterparty() finds no record for the requested counterparty_id."""


class GraphWriteError(GraphError):
    """Raised on Neo4j write failure (constraint violation, connectivity, etc.)."""


# ---------------------------------------------------------------------------
# AI layer errors
# ---------------------------------------------------------------------------


class AILayerError(TributaryError):
    """Base for AI layer errors."""


class AIModelCallError(AILayerError):
    """Raised when the Claude API call fails (network, auth, rate limit, etc.)."""


class AIValidationError(AILayerError):
    """Raised when AI output fails Pydantic validation against expected schema."""


class AIContractViolationError(AILayerError):
    """Raised when AI output violates a contract constraint (e.g. emits a figure, DEC-002)."""


# ---------------------------------------------------------------------------
# Engine and rule-pack errors
# ---------------------------------------------------------------------------


class EngineError(TributaryError):
    """Base for deterministic engine errors."""


class RulePackError(TributaryError):
    """Raised on rule pack loading or validation error (missing fields, bad JSON, etc.)."""


# ---------------------------------------------------------------------------
# Ingestion errors
# ---------------------------------------------------------------------------


class IngestionError(TributaryError):
    """Raised on data ingestion or normalization error (malformed source, FX failure, etc.)."""
