"""
Module: flow_context
Layer: engine
Purpose: Build FlowContext objects from graph transactions and run them through the injected
    AI layer (classification + attribution) to derive per-jurisdiction review flags. The AI
    produces no figures (DEC-002); it only influences needs_review.
Dependencies: tributary.common
Used by: engine.runner
"""
from __future__ import annotations

from pydantic import BaseModel

from tributary.common.errors import EntityNotFoundError, GraphError
from tributary.common.models import (
    AILayerProtocol,
    ConfidenceLevel,
    FlowAttribution,
    FlowClassification,
    FlowContext,
    GraphReader,
    JurisdictionCode,
    TransactionRecord,
)


class FlowJudgement(BaseModel):
    """The AI's classification + attribution for one flow (no figures)."""

    classification: FlowClassification
    attribution: FlowAttribution


def build_flow_context(
    reader: GraphReader,
    txn: TransactionRecord,
    available_jurisdictions: list[JurisdictionCode],
) -> FlowContext:
    """Construct the FlowContext the AI layer needs for one transaction."""
    source_jurisdiction: JurisdictionCode | None = None
    try:
        source_jurisdiction = reader.get_entity(txn.source_entity_id).resident_jurisdiction
    except (EntityNotFoundError, GraphError):
        source_jurisdiction = None
    return FlowContext(
        flow_id=txn.transaction_id,
        description=txn.description,
        amount_hkd=txn.amount_hkd,
        flow_date=txn.transaction_date,
        source_entity_id=txn.source_entity_id,
        source_jurisdiction=source_jurisdiction,
        counterparty_entity_id=txn.counterparty_entity_id,
        counterparty_jurisdiction=txn.counterparty_jurisdiction,
        is_intercompany=txn.is_intercompany,
        activity_type=txn.activity_type,
        days_present=txn.days_present,
        has_agent_authority=txn.has_agent_authority,
        available_jurisdictions=available_jurisdictions,
    )


def judge_flows(
    ai: AILayerProtocol,
    reader: GraphReader,
    transactions: list[TransactionRecord],
    available_jurisdictions: list[JurisdictionCode],
) -> dict[str, FlowJudgement]:
    """Classify + attribute each non-presence flow via the AI layer.

    Args:
        ai: The injected AI layer.
        reader: Graph reader (for FlowContext construction).
        transactions: Transactions to judge (presence markers are skipped).
        available_jurisdictions: Jurisdictions with loaded rule packs.
    Returns:
        Map of flow_id → FlowJudgement.
    """
    judgements: dict[str, FlowJudgement] = {}
    for txn in transactions:
        if txn.days_present is not None:
            continue
        context = build_flow_context(reader, txn, available_jurisdictions)
        classification = ai.classify_flow(context)
        attribution = ai.attribute_flow(context, classification)
        judgements[txn.transaction_id] = FlowJudgement(
            classification=classification, attribution=attribution
        )
    return judgements


def jurisdiction_needs_review(
    judgements: dict[str, FlowJudgement],
    flow_ids: list[str],
    jurisdiction: JurisdictionCode,
) -> bool:
    """Return True if any of the given flows is low-confidence for this jurisdiction.

    Args:
        judgements: AI judgements keyed by flow id.
        flow_ids: The flows contributing to a jurisdiction's obligation.
        jurisdiction: The taxing jurisdiction to check claims for.
    Returns:
        True if a contributing classification is LOW, or an attribution claim for this
        jurisdiction is LOW.
    """
    for flow_id in flow_ids:
        judgement = judgements.get(flow_id)
        if judgement is None:
            continue
        if judgement.classification.confidence is ConfidenceLevel.LOW:
            return True
        for claim in judgement.attribution.claims:
            if claim.jurisdiction == jurisdiction and claim.confidence is ConfidenceLevel.LOW:
                return True
    return False
