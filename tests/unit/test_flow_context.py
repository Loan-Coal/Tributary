"""
Module: test_flow_context
Layer: test-unit
Purpose: Unit tests for engine.flow_context — build_flow_context and jurisdiction_needs_review.
Dependencies: datetime, decimal, pytest, tributary.engine.flow_context, tests.support.fakes
Used by: make test, make test-engine
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tributary.common.errors import EntityNotFoundError
from tributary.common.models import (
    ActivityType,
    ConfidenceLevel,
    FlowAttribution,
    FlowClassification,
    FlowContext,
    FlowNature,
    JurisdictionClaim,
    JurisdictionCode,
    RuleCitation,
    TransactionRecord,
)
from tributary.engine.flow_context import FlowJudgement, build_flow_context, jurisdiction_needs_review
from tests.support.fakes import FakeGraphReader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _citation(jur: str = "HK") -> RuleCitation:
    return RuleCitation(
        rule_id="TEST-001",
        jurisdiction=JurisdictionCode(jur),
        as_of_date=date(2025, 1, 1),
        source_citation="Test source",
    )


def _classification(flow_id: str, confidence: ConfidenceLevel) -> FlowClassification:
    return FlowClassification(
        flow_id=flow_id,
        nature=FlowNature.REVENUE,
        confidence=confidence,
        rule_citations=[_citation()],
        abstain_reason=None,
    )


def _attribution(flow_id: str, jur: str, confidence: ConfidenceLevel) -> FlowAttribution:
    claim = JurisdictionClaim(
        jurisdiction=JurisdictionCode(jur),
        confidence=confidence,
        claim_basis="test",
        rationale_citation=_citation(jur),
    )
    return FlowAttribution(
        flow_id=flow_id,
        primary_jurisdiction=JurisdictionCode(jur),
        claims=[claim],
        abstain=False,
        abstain_reason=None,
    )


def _txn(txn_id: str, entity_id: str = "MERID-HK") -> TransactionRecord:
    return TransactionRecord(
        transaction_id=txn_id,
        source_entity_id=entity_id,
        counterparty_entity_id=None,
        counterparty_jurisdiction=None,
        description="Test transaction",
        amount_hkd=Decimal("100000"),
        source_amount=Decimal("100000"),
        fx_rate=Decimal("1"),
        fx_date=date(2025, 6, 1),
        source_currency="HKD",
        transaction_date=date(2025, 6, 1),
        activity_type=ActivityType.REVENUE,
        is_intercompany=False,
        days_present=None,
        has_agent_authority=False,
    )


# ===========================================================================
# build_flow_context
# ===========================================================================

class TestBuildFlowContext:
    def test_happy_path_populates_all_fields(self):
        """FlowContext fields are correctly populated from transaction and entity."""
        reader = FakeGraphReader()
        txn = _txn("T001")
        jurisdictions = ["HK", "DE"]
        ctx = build_flow_context(reader, txn, jurisdictions)

        assert ctx.flow_id == "T001"
        assert ctx.description == txn.description
        assert ctx.amount_hkd == txn.amount_hkd
        assert ctx.flow_date == txn.transaction_date
        assert ctx.source_entity_id == "MERID-HK"
        assert ctx.is_intercompany is False
        assert ctx.available_jurisdictions == jurisdictions

    def test_source_jurisdiction_resolved_from_entity(self):
        """Source jurisdiction is populated from the entity's resident_jurisdiction."""
        reader = FakeGraphReader()
        txn = _txn("T001", entity_id="MERID-HK")
        ctx = build_flow_context(reader, txn, ["HK"])
        assert ctx.source_jurisdiction == "HK"

    def test_source_jurisdiction_none_on_missing_entity(self):
        """When the entity is not in the graph, source_jurisdiction defaults to None."""
        reader = FakeGraphReader()
        txn = _txn("T001", entity_id="UNKNOWN-ENTITY")
        ctx = build_flow_context(reader, txn, ["HK"])
        assert ctx.source_jurisdiction is None

    def test_counterparty_fields_passed_through(self):
        """Counterparty entity and jurisdiction from the transaction are preserved."""
        reader = FakeGraphReader()
        txn = _txn("T001")
        txn = txn.model_copy(update={
            "counterparty_entity_id": "MERID-DE",
            "counterparty_jurisdiction": "DE",
        })
        ctx = build_flow_context(reader, txn, ["HK", "DE"])
        assert ctx.counterparty_entity_id == "MERID-DE"
        assert ctx.counterparty_jurisdiction == "DE"


# ===========================================================================
# jurisdiction_needs_review
# ===========================================================================

class TestJurisdictionNeedsReview:
    def test_returns_false_when_all_high_confidence(self):
        """No review needed when classification and attribution are both HIGH."""
        judgements = {
            "T001": FlowJudgement(
                classification=_classification("T001", ConfidenceLevel.HIGH),
                attribution=_attribution("T001", "HK", ConfidenceLevel.HIGH),
            )
        }
        assert jurisdiction_needs_review(judgements, ["T001"], "HK") is False

    def test_returns_true_on_low_classification_confidence(self):
        """LOW classification confidence triggers review regardless of attribution."""
        judgements = {
            "T001": FlowJudgement(
                classification=_classification("T001", ConfidenceLevel.LOW),
                attribution=_attribution("T001", "HK", ConfidenceLevel.HIGH),
            )
        }
        assert jurisdiction_needs_review(judgements, ["T001"], "HK") is True

    def test_returns_true_on_low_attribution_claim_for_jurisdiction(self):
        """LOW attribution confidence for the specific jurisdiction triggers review."""
        judgements = {
            "T001": FlowJudgement(
                classification=_classification("T001", ConfidenceLevel.HIGH),
                attribution=_attribution("T001", "HK", ConfidenceLevel.LOW),
            )
        }
        assert jurisdiction_needs_review(judgements, ["T001"], "HK") is True

    def test_low_claim_for_other_jurisdiction_does_not_trigger(self):
        """LOW confidence for a different jurisdiction does not trigger review for HK."""
        judgements = {
            "T001": FlowJudgement(
                classification=_classification("T001", ConfidenceLevel.HIGH),
                attribution=_attribution("T001", "DE", ConfidenceLevel.LOW),
            )
        }
        assert jurisdiction_needs_review(judgements, ["T001"], "HK") is False

    def test_returns_false_for_missing_flow_id(self):
        """Missing flow_id in judgements is skipped (presence markers, etc.)."""
        judgements: dict[str, FlowJudgement] = {}
        assert jurisdiction_needs_review(judgements, ["T003"], "DE") is False

    def test_any_flow_low_confidence_triggers_review(self):
        """Review triggered if ANY flow in the list has low confidence."""
        judgements = {
            "T001": FlowJudgement(
                classification=_classification("T001", ConfidenceLevel.HIGH),
                attribution=_attribution("T001", "HK", ConfidenceLevel.HIGH),
            ),
            "T002": FlowJudgement(
                classification=_classification("T002", ConfidenceLevel.LOW),
                attribution=_attribution("T002", "HK", ConfidenceLevel.HIGH),
            ),
        }
        assert jurisdiction_needs_review(judgements, ["T001", "T002"], "HK") is True
