"""
Module: protocols_ai
Layer: common
Purpose: Protocol interfaces the AI layer and its callers depend on. Defined in common/
    so the engine and ai layers share a stable contract without cross-importing (DEC-018).
    Includes AILayerProtocol, GraphReaderProtocol, RulePackLoaderProtocol, LLMClientProtocol.
Dependencies: typing, models_ai, models_entity
Used by: engine (AILayerProtocol), ai.service (GraphReaderProtocol, RulePackLoaderProtocol,
    LLMClientProtocol), ai.adapter, engine.attribution_stub, tests
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .models_ai import (
    FlowAttribution,
    FlowClassification,
    FlowContext,
    RuleRetrievalResult,
)
from .models_entity import FlowNature, JurisdictionCode

if TYPE_CHECKING:
    from tributary.ai.models import AILayerOutput, RuleSummary, TransactionContext


class GraphReaderProtocol(Protocol):
    """Narrow read interface the AI service uses to fetch transaction context."""

    def get_transaction_context(self, transaction_id: str) -> TransactionContext:
        """Fetch transaction text and graph facts WITHOUT amounts."""
        ...


class RulePackLoaderProtocol(Protocol):
    """Narrow rule-loader interface the AI service uses to fetch rule summaries."""

    def get_rule_summaries(self, jurisdictions: list[str]) -> list[RuleSummary]:
        """Fetch rule summaries for prompt injection (id, summary, as_of_date, source_citation)."""
        ...


class LLMClientProtocol(Protocol):
    """Interface any LLM client must satisfy to be injected into AILayerService."""

    def generate(self, prompt: str, max_tokens: int = 800) -> AILayerOutput:
        """Generate structured AI output from a prompt string."""
        ...


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
