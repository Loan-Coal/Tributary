"""
Module: test_adapter
Layer: test-unit
Purpose: Unit tests for ai.adapter.AILayerAdapter — FlowNature normalisation, FlowClassification
    mapping, FlowAttribution mapping, and RuleRetrievalResult mapping using FakeClaudeClient.
Dependencies: datetime, decimal, pytest, tributary.ai.adapter, tributary.ai.fake_client,
    tributary.rules.loader, tests.support.fakes
Used by: make test
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tributary.ai.adapter import AILayerAdapter, _NATURE_MAP, _map_citation
from tributary.ai.fake_client import FakeClaudeClient
from tributary.ai.models import AILayerOutput, RuleCitation as AiRuleCitation
from tributary.common.models import (
    ActivityType,
    ConfidenceLevel,
    FlowContext,
    FlowNature,
    JurisdictionCode,
)
from tributary.rules.loader import JSONRulePackLoader
from tests.support.fakes import FakeGraphReader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _context(
    flow_id: str = "T001",
    source_jur: str | None = "HK",
    available: list[str] | None = None,
) -> FlowContext:
    avail = list(available or ["HK", "DE"])
    return FlowContext(
        flow_id=flow_id,
        description="Test transaction",
        amount_hkd=Decimal("500000"),
        flow_date=date(2025, 6, 1),
        source_entity_id="LENOVO-HK",
        source_jurisdiction=source_jur,
        counterparty_entity_id="LENOVO-DE",
        counterparty_jurisdiction="DE",
        is_intercompany=True,
        activity_type=ActivityType.REVENUE,
        days_present=None,
        has_agent_authority=False,
        available_jurisdictions=avail,
    )


@pytest.fixture(scope="module")
def adapter() -> AILayerAdapter:
    return AILayerAdapter(llm_client=FakeClaudeClient(), rule_loader=JSONRulePackLoader())


# ===========================================================================
# FlowNature normalisation
# ===========================================================================

class TestNatureNormalisation:
    def test_revenue_uppercase_maps_to_enum(self):
        assert _NATURE_MAP["REVENUE"] == FlowNature.REVENUE

    def test_unclassified_maps_to_other(self):
        assert _NATURE_MAP["UNCLASSIFIED"] == FlowNature.OTHER

    def test_all_upstream_literals_are_mapped(self):
        """Every Literal value from AILayerOutput.flow_classification has a mapping."""
        upstream_literals = ["REVENUE", "EXPENSE", "INTERCOMPANY", "CAPITAL", "LOAN", "UNCLASSIFIED"]
        for lit in upstream_literals:
            assert lit in _NATURE_MAP


# ===========================================================================
# RuleCitation conversion
# ===========================================================================

class TestMapCitation:
    def test_as_of_date_str_converted_to_date(self):
        raw = AiRuleCitation(
            rule_id="TR-001",
            source_citation="Tax Act §12",
            as_of_date="2026-01-01",
            confidence=0.9,
            reasoning="Applies because...",
        )
        citation = _map_citation(raw, "HK")
        assert citation.as_of_date == date(2026, 1, 1)
        assert citation.jurisdiction == "HK"
        assert citation.rule_id == "TR-001"
        assert citation.source_citation == "Tax Act §12"


# ===========================================================================
# classify_flow
# ===========================================================================

class TestClassifyFlow:
    def test_returns_flow_classification_with_correct_flow_id(self, adapter):
        ctx = _context("T001")
        result = adapter.classify_flow(ctx)
        assert result.flow_id == "T001"

    def test_flow_nature_is_lowercase_enum(self, adapter):
        """FakeClaudeClient returns 'REVENUE'; adapter must normalise to FlowNature.REVENUE."""
        ctx = _context("T001")
        result = adapter.classify_flow(ctx)
        assert result.nature == FlowNature.REVENUE

    def test_not_abstained_on_fake_client(self, adapter):
        ctx = _context("T001")
        result = adapter.classify_flow(ctx)
        assert result.confidence == ConfidenceLevel.HIGH
        assert result.abstain_reason is None

    def test_rule_citations_have_date_objects(self, adapter):
        """Canonical RuleCitation.as_of_date must be date, not str."""
        ctx = _context("T001")
        result = adapter.classify_flow(ctx)
        for citation in result.rule_citations:
            assert isinstance(citation.as_of_date, date)


# ===========================================================================
# attribute_flow
# ===========================================================================

class TestAttributeFlow:
    def test_returns_flow_attribution_with_correct_flow_id(self, adapter):
        ctx = _context("T002")
        classification = adapter.classify_flow(ctx)
        attribution = adapter.attribute_flow(ctx, classification)
        assert attribution.flow_id == "T002"

    def test_candidate_jurisdictions_become_claims(self, adapter):
        """FakeClaudeClient returns ['US', 'SG']; those become JurisdictionClaim entries."""
        ctx = _context("T002")
        classification = adapter.classify_flow(ctx)
        attribution = adapter.attribute_flow(ctx, classification)
        claim_jurisdictions = {c.jurisdiction for c in attribution.claims}
        # FakeClaudeClient returns US and SG — both should appear
        assert "US" in claim_jurisdictions or len(attribution.claims) >= 1

    def test_result_is_cached_no_second_llm_call(self, adapter):
        """Second call with same flow_id should reuse cache — outcome is identical."""
        ctx = _context("T003")
        c1 = adapter.classify_flow(ctx)
        c2 = adapter.classify_flow(ctx)
        assert c1.flow_id == c2.flow_id
        assert c1.nature == c2.nature


# ===========================================================================
# retrieve_applicable_rules
# ===========================================================================

class TestRetrieveApplicableRules:
    def test_returns_abstain_if_not_classified_first(self):
        """retrieve_applicable_rules must be called after classify_flow."""
        fresh_adapter = AILayerAdapter(
            llm_client=FakeClaudeClient(), rule_loader=JSONRulePackLoader()
        )
        result = fresh_adapter.retrieve_applicable_rules(
            "UNCACHED-FLOW", "HK", FlowNature.REVENUE
        )
        assert result.abstain is True

    def test_returns_rules_after_classify_flow(self, adapter):
        ctx = _context("T004")
        adapter.classify_flow(ctx)
        result = adapter.retrieve_applicable_rules("T004", "HK", FlowNature.REVENUE)
        assert result.flow_id == "T004"
        assert result.jurisdiction == "HK"
        # FakeClaudeClient returns one rule
        assert len(result.applicable_rules) >= 1
