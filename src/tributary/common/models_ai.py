"""
Module: models_ai
Layer: common
Purpose: AI protocol input/output data models — flow context, classification, attribution,
    and rule retrieval. These models contain NO amount fields (DEC-002).
Dependencies: pydantic, decimal, datetime, models_entity, models_engine
Used by: models (re-export), ai, brief
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from .models_engine import RuleCitation
from .models_entity import (
    ActivityType,
    ConfidenceLevel,
    FlowNature,
    JurisdictionCode,
)


class FlowContext(BaseModel):
    """Input context passed to the AI layer for classification and attribution.

    Note:
        ``amount_hkd`` is included here as read-only context that the AI uses
        to understand flow materiality. The AI must never re-emit this figure.
    """

    flow_id: str
    description: str
    amount_hkd: Decimal
    flow_date: date
    source_entity_id: str
    source_jurisdiction: JurisdictionCode | None
    counterparty_entity_id: str | None
    counterparty_jurisdiction: JurisdictionCode | None
    is_intercompany: bool
    activity_type: ActivityType | None
    days_present: int | None
    has_agent_authority: bool
    available_jurisdictions: list[JurisdictionCode]


class FlowClassification(BaseModel):
    """AI output: semantic nature of a flow and associated confidence.

    Note:
        This model intentionally contains no amount or rate fields (DEC-002).
        All numeric outputs belong to EngineRunResult.
    """

    flow_id: str
    nature: FlowNature
    confidence: ConfidenceLevel
    rule_citations: list[RuleCitation]
    abstain_reason: str | None


class JurisdictionClaim(BaseModel):
    """A single jurisdiction's claim to tax a flow, with confidence and optional citation.

    Note:
        rationale_citation is Optional. When the AI abstains or cannot supply a real rule
        reference, citation is None and needs_human_review is set on the parent FlowAttribution
        (DEC-022). A None citation must never be silently promoted to a fabricated placeholder.
    """

    jurisdiction: JurisdictionCode
    confidence: ConfidenceLevel
    claim_basis: str
    rationale_citation: RuleCitation | None = None


class FlowAttribution(BaseModel):
    """AI output: jurisdiction attribution for a flow.

    Note:
        Contains no numeric amounts (DEC-002). Primary jurisdiction may be None
        when the AI abstains.
    """

    flow_id: str
    primary_jurisdiction: JurisdictionCode | None
    claims: list[JurisdictionClaim]
    abstain: bool
    abstain_reason: str | None


class ApplicableRule(BaseModel):
    """A rule identified as applicable to a flow during retrieval."""

    rule_id: str
    jurisdiction: JurisdictionCode
    rule_type: str
    as_of_date: date
    source_citation: str
    relevance_note: str | None


class RuleRetrievalResult(BaseModel):
    """AI output: set of applicable rules retrieved for a flow and jurisdiction."""

    flow_id: str
    jurisdiction: JurisdictionCode
    applicable_rules: list[ApplicableRule]
    abstain: bool
    abstain_reason: str | None
