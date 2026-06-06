"""
Module: models
Layer: common
Purpose: Canonical Pydantic v2 data models shared across all Tributary layers.
    This module re-exports all models from the three sub-modules to provide a
    single import surface. Split across files to respect the 300-line limit
    (see DECISIONS.md DEC-011).
Dependencies: models_entity, models_engine, models_ai
Used by: graph, engine, ai, brief, ingestion, api — all layers
"""
from __future__ import annotations

# AI protocol input/output models (DEC-010)
from .models_ai import (
    ApplicableRule,
    FlowAttribution,
    FlowClassification,
    FlowContext,
    JurisdictionClaim,
    RuleRetrievalResult,
)

# Engine output models
from .models_engine import (
    ComputationStep,
    ConflictFlag,
    ConflictType,
    DeadlineResult,
    EngineRunResult,
    GroupReliefMechanism,
    GroupReliefOpportunity,
    LossCarryforwardRecord,
    ObligationResult,
    ReliefMechanism,
    RuleCitation,
    ThresholdResult,
)

# Entity, structure, period, and enum models
from .models_entity import (
    AccountRecord,
    ActivityType,
    ConfidenceLevel,
    CounterpartyRecord,
    EntityRecord,
    EntityType,
    FiscalCalendar,
    FiscalPeriod,
    FlowNature,
    JurisdictionCode,
    ObligationType,
    OwnershipRecord,
    PresenceActivity,
    PresenceRecord,
    PriorPeriodLoss,
    TransactionRecord,
)
from .protocols_ai import AILayerProtocol

# Boundary protocols (DEC-018) — defined in common so engine can depend on them
from .protocols_graph import GraphReader, GraphWriter

__all__ = [
    # Enums
    "ConfidenceLevel",
    "FlowNature",
    "ActivityType",
    "PresenceActivity",
    "ObligationType",
    "EntityType",
    "ConflictType",
    "ReliefMechanism",
    "GroupReliefMechanism",
    # Entity / structure
    "JurisdictionCode",
    "EntityRecord",
    "OwnershipRecord",
    "AccountRecord",
    "TransactionRecord",
    "PresenceRecord",
    "PriorPeriodLoss",
    "CounterpartyRecord",
    # Period
    "FiscalPeriod",
    "FiscalCalendar",
    # Shared citation
    "RuleCitation",
    # Engine outputs
    "ComputationStep",
    "ObligationResult",
    "ThresholdResult",
    "DeadlineResult",
    "LossCarryforwardRecord",
    "ConflictFlag",
    "GroupReliefOpportunity",
    "EngineRunResult",
    # Boundary protocols
    "GraphReader",
    "GraphWriter",
    "AILayerProtocol",
    # AI protocol models
    "FlowContext",
    "FlowClassification",
    "JurisdictionClaim",
    "FlowAttribution",
    "ApplicableRule",
    "RuleRetrievalResult",
]
