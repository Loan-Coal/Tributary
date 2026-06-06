"""
Module: protocol
Layer: ai
Purpose: Published interface surface for the AI layer implementor. Re-exports the
    AILayerProtocol and its input/output models so the AI colleague has a single import
    point (`from tributary.ai.protocol import AILayerProtocol, FlowContext, ...`).
    The protocol itself is defined in common/ (DEC-018) so the engine can depend on it
    without importing ai/.
Dependencies: tributary.common
Used by: ai layer implementations (classifier, attributor, retriever, mock_adapter)
"""
from __future__ import annotations

from tributary.common.models_ai import (
    ApplicableRule,
    FlowAttribution,
    FlowClassification,
    FlowContext,
    JurisdictionClaim,
    RuleRetrievalResult,
)
from tributary.common.models_engine import RuleCitation
from tributary.common.models_entity import (
    ActivityType,
    ConfidenceLevel,
    FlowNature,
    JurisdictionCode,
)
from tributary.common.protocols_ai import AILayerProtocol

__all__ = [
    "AILayerProtocol",
    "FlowContext",
    "FlowClassification",
    "FlowAttribution",
    "JurisdictionClaim",
    "ApplicableRule",
    "RuleRetrievalResult",
    "RuleCitation",
    "ActivityType",
    "ConfidenceLevel",
    "FlowNature",
    "JurisdictionCode",
]
