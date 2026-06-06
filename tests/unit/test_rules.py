"""
Module: test_rules
Layer: rules
Purpose: Unit + against-real-JSON tests for the rule-pack models and JSON loader. Runs with
    no Neo4j and no network — the real demo packs in data/rules are loaded directly.
Dependencies: pytest, pathlib, decimal, tributary.rules
Used by: pytest test suite
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from tributary.common.errors import RulePackError
from tributary.rules.loader import JSONRulePackLoader
from tributary.rules.models import (
    Rule,
    RuleCategory,
    RuleParameters,
    RuleType,
)

RULES_DIR = Path(__file__).resolve().parents[2] / "data" / "rules"


@pytest.fixture
def loader() -> JSONRulePackLoader:
    """Loader pointed at the real demo rule packs."""
    return JSONRulePackLoader(RULES_DIR)


# ---------------------------------------------------------------------------
# Rule model validation
# ---------------------------------------------------------------------------

class TestRuleModel:
    """Tests for the Rule model and its per-category parameter validator."""

    def test_rate_rule_valid(self) -> None:
        """A rate rule with a rate parameter validates."""
        rule = Rule(
            id="X-CIT",
            jurisdiction="HK",
            type=RuleType.RATE,
            category=RuleCategory.CIT_RATE,
            parameters=RuleParameters(rate=Decimal("0.165")),
            as_of_date=date(2023, 4, 1),
            source_citation="IRO s.14",
        )
        assert rule.parameters.rate == Decimal("0.165")

    def test_rate_rule_missing_required_param(self) -> None:
        """A cit_rate rule without a rate parameter fails fast."""
        with pytest.raises(Exception):
            Rule(
                id="X-CIT",
                jurisdiction="HK",
                type=RuleType.RATE,
                category=RuleCategory.CIT_RATE,
                parameters=RuleParameters(),
                as_of_date=date(2023, 4, 1),
                source_citation="IRO s.14",
            )

    def test_pe_threshold_requires_day_count(self) -> None:
        """A treaty_pe rule without day_count fails fast."""
        with pytest.raises(Exception):
            Rule(
                id="X-PE",
                jurisdiction="DE",
                type=RuleType.TREATY,
                category=RuleCategory.TREATY_PE,
                parameters=RuleParameters(attribution_pct=Decimal("0.35")),
                as_of_date=date(2017, 1, 1),
                source_citation="DTA Art.5",
            )


# ---------------------------------------------------------------------------
# Loader against the real demo packs
# ---------------------------------------------------------------------------

class TestLoaderRealPacks:
    """Tests that load and assert against the actual data/rules JSON files."""

    @pytest.mark.parametrize(
        "jurisdiction,month",
        [("HK", 4), ("DE", 1), ("FR", 1)],
    )
    def test_fiscal_calendars(self, loader: JSONRulePackLoader, jurisdiction: str, month: int) -> None:
        """Each jurisdiction pack exposes the correct fiscal-year start month."""
        calendar = loader.get_fiscal_calendar(jurisdiction)
        assert calendar.period_start_month == month

    def test_de_cit_rate_and_surcharge(self, loader: JSONRulePackLoader) -> None:
        """German CIT rate rule carries base rate and solidarity surcharge."""
        rules = loader.get_rules("DE", RuleCategory.CIT_RATE)
        assert len(rules) == 1
        assert rules[0].parameters.rate == Decimal("0.15")
        assert rules[0].parameters.surcharge_rate == Decimal("0.055")

    def test_hk_has_no_trade_tax(self, loader: JSONRulePackLoader) -> None:
        """HK has no trade-tax rule — the engine must treat absence as 'not applicable'."""
        assert loader.get_rules("HK", RuleCategory.TRADE_TAX_RATE) == []

    def test_de_has_trade_tax(self, loader: JSONRulePackLoader) -> None:
        """DE has a trade-tax rate rule (activates the trade-tax sub-engine, DEC-009)."""
        rules = loader.get_rules("DE", RuleCategory.TRADE_TAX_RATE)
        assert rules and rules[0].parameters.rate == Decimal("0.14")

    def test_treaty_lookup_order_independent(self, loader: JSONRulePackLoader) -> None:
        """get_treaty_rules returns the same pack regardless of argument order."""
        ab = [r.id for r in loader.get_treaty_rules("DE", "FR")]
        ba = [r.id for r in loader.get_treaty_rules("FR", "DE")]
        assert ab == ba and "DEFR-DTA-PE" in ab

    def test_de_fr_pe_attribution_param(self, loader: JSONRulePackLoader) -> None:
        """The DE-FR service-PE rule carries the 183-day count and 35% attribution."""
        pe = [r for r in loader.get_treaty_rules("DE", "FR") if r.category == RuleCategory.TREATY_PE][0]
        assert pe.parameters.day_count == 183
        assert pe.parameters.attribution_pct == Decimal("0.35")

    def test_elimination_mechanism_is_exemption(self, loader: JSONRulePackLoader) -> None:
        """DE-FR Art.23 elimination is modelled as the exemption method (DEC-017)."""
        elim = [
            r for r in loader.get_treaty_rules("DE", "FR")
            if r.category == RuleCategory.TREATY_ELIMINATION
        ][0]
        assert elim.parameters.relief_mechanism == "exemption"

    def test_every_rule_has_as_of_date_and_citation(self, loader: JSONRulePackLoader) -> None:
        """DEC-004: every rule surfaces an as_of_date and a source citation."""
        for jurisdiction in ("HK", "DE", "FR"):
            for category in RuleCategory:
                for rule in loader.get_rules(jurisdiction, category):
                    assert rule.as_of_date is not None
                    assert rule.source_citation.strip()

    def test_missing_pack_raises(self, loader: JSONRulePackLoader) -> None:
        """Requesting an unknown jurisdiction raises RulePackError."""
        with pytest.raises(RulePackError):
            loader.get_fiscal_calendar("ZZ")

    def test_unknown_rule_id_raises(self, loader: JSONRulePackLoader) -> None:
        """Requesting an unknown rule id raises RulePackError."""
        with pytest.raises(RulePackError):
            loader.get_rule("HK", "NOPE")


# ---------------------------------------------------------------------------
# GROUP_RELIEF rule category (Wave 6b — W6b.3)
# ---------------------------------------------------------------------------

class TestGroupReliefCategory:
    """Tests for the GROUP_RELIEF enum member (W6b.3)."""

    def test_group_relief_enum_member_exists(self) -> None:
        """RuleCategory.GROUP_RELIEF exists with the correct string value."""
        assert RuleCategory.GROUP_RELIEF.value == "group_relief"

    def test_group_relief_absent_in_golden_packs(self, loader: JSONRulePackLoader) -> None:
        """Golden packs (HK, DE, FR) correctly return empty list for GROUP_RELIEF.

        HK/DE/FR have no bilateral group relief arrangement — zero opportunities is the
        expected and verifiable result for the Meridian golden scenario.
        """
        for jurisdiction in ("HK", "DE", "FR"):
            rules = loader.get_rules(jurisdiction, RuleCategory.GROUP_RELIEF)
            assert rules == [], (
                f"Expected no GROUP_RELIEF rules for {jurisdiction}; got {rules}"
            )
