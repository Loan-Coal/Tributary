"""
Module: protocols_ai
Layer: common
Purpose: The AILayerProtocol the engine depends on for flow classification, jurisdiction
    attribution, and rule retrieval. Defined in common/ because the engine may not import
    ai/ and the ai layer may not import engine/ — common is the only shared layer (DEC-018).
    Re-exported by ai/protocol.py as the published surface for the AI colleague.
Dependencies: typing, models_ai, models_entity
Used by: engine (depends on protocol), ai (implements it), engine.attribution_stub, tests
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models_ai import (
    FlowAttribution,
    FlowClassification,
    FlowContext,
    RuleRetrievalResult,
)
from .models_entity import FlowNature, JurisdictionCode


@runtime_checkable
class AILayerProtocol(Protocol):
    """Contract the AI layer must implement.

    The engine depends only on this protocol, never on concrete AI classes. Both the
    Phase-3/4 attribution stub and the real Claude adapter implement it. No method may
    emit a figure (DEC-002).
    """

    def classify_flow(self, context: FlowContext) -> FlowClassification:
        """Classify the nature of a transaction flow.

        Args:
            context: All graph + transaction data for one flow.
        Returns:
            Classification with nature, confidence, and rule citations.
        Raises:
            AILayerError: If the underlying model call fails (not for abstention).
        """
        ...

    def attribute_flow(
        self,
        context: FlowContext,
        classification: FlowClassification,
    ) -> FlowAttribution:
        """Attribute the jurisdiction(s) that may tax this flow.

        Args:
            context: The same FlowContext passed to classify_flow().
            classification: Output from classify_flow() for this flow.
        Returns:
            Attribution with one or more jurisdiction claims.
        Raises:
            AILayerError: On model call failure.
        """
        ...

    def retrieve_applicable_rules(
        self,
        flow_id: str,
        jurisdiction: JurisdictionCode,
        nature: FlowNature,
    ) -> RuleRetrievalResult:
        """Retrieve rule IDs the AI believes apply to this flow in this jurisdiction.

        Args:
            flow_id: The transaction ID.
            jurisdiction: The attributed jurisdiction.
            nature: The classified flow nature.
        Returns:
            Applicable rule citations for cross-check against the rule pack.
        Raises:
            AILayerError: On model call failure.
        """
        ...
