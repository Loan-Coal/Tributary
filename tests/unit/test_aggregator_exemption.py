"""
Module: test_aggregator_exemption
Layer: test-unit
Purpose: Unit tests for aggregator.exemption_for() — participation and income exemptions.
Dependencies: decimal, pytest, tributary.engine.aggregator, tributary.rules.loader
Used by: make test, make test-engine
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from tributary.common.models import ActivityType, JurisdictionCode
from tributary.engine.aggregator import exemption_for
from tributary.rules.loader import JSONRulePackLoader


@pytest.fixture(scope="module")
def loader() -> JSONRulePackLoader:
    return JSONRulePackLoader()


class TestExemptionFor:
    def test_de_participation_exemption_on_dividend(self, loader: JSONRulePackLoader):
        """DE §8b KStG: 95% of received dividends exempt from CIT base."""
        fraction, rule = exemption_for(loader, "DE", ActivityType.DIVIDEND)
        assert fraction == Decimal("0.95")
        assert rule is not None
        assert rule.jurisdiction == "DE"

    def test_hk_income_exemption_on_dividend(self, loader: JSONRulePackLoader):
        """HK: territorial — inbound dividends fully exempt (100%)."""
        fraction, rule = exemption_for(loader, "HK", ActivityType.DIVIDEND)
        assert fraction == Decimal("1.0")
        assert rule is not None

    def test_no_exemption_for_revenue_activity(self, loader: JSONRulePackLoader):
        """Regular revenue activity has no exemption rule — fraction is zero."""
        fraction, rule = exemption_for(loader, "DE", ActivityType.REVENUE)
        assert fraction == Decimal("0")
        assert rule is None

    def test_no_exemption_for_jurisdiction_without_rule(self, loader: JSONRulePackLoader):
        """FR does not have a participation exemption in the demo pack — returns zero."""
        fraction, rule = exemption_for(loader, "FR", ActivityType.DIVIDEND)
        # FR dividend received from within the group: no exemption rule in demo pack
        assert fraction == Decimal("0")
        assert rule is None

    def test_returns_zero_for_unknown_activity(self, loader: JSONRulePackLoader):
        """Activity with no matching rule returns (0, None) without raising."""
        fraction, rule = exemption_for(loader, "HK", ActivityType.MANAGEMENT_FEE)
        assert fraction == Decimal("0")
        assert rule is None
