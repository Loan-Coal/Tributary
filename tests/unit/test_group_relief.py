"""
Module: test_group_relief
Layer: engine
Purpose: Unit tests for the scan_group_relief function (Wave 6b group-relief scanner).
    Verifies opportunity emission, absence when no rule exists, and the golden-scenario
    regression guard (HK/DE/FR → zero opportunities).
Dependencies: pytest, decimal, datetime, pathlib, unittest.mock, tributary.engine.group_relief,
    tributary.engine.aggregator, tributary.rules, tributary.common
Used by: pytest test suite
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tributary.common.models import FiscalPeriod, JurisdictionCode
from tributary.common.models_engine import GroupReliefMechanism
from tributary.common.models_entity import EntityRecord
from tributary.engine.aggregator import EntityBase
from tributary.engine.group_relief import scan_group_relief
from tributary.rules.loader import JSONRulePackLoader
from tributary.rules.models import Rule, RuleCategory, RuleParameters, RuleType

def _period(jurisdiction: JurisdictionCode = "HK") -> FiscalPeriod:
    return FiscalPeriod(
        jurisdiction=jurisdiction,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

RULES_DIR = Path(__file__).resolve().parents[2] / "data" / "rules"


def _make_base(
    entity_id: str,
    jurisdiction: JurisdictionCode,
    net_income_hkd: Decimal,
) -> EntityBase:
    return EntityBase(
        entity_id=entity_id,
        jurisdiction=jurisdiction,
        period=_period(jurisdiction),
        third_party_income_hkd=max(net_income_hkd, Decimal("0")),
        ic_income_taxable_hkd=Decimal("0"),
        deductible_expense_hkd=Decimal("0"),
        interest_expense_hkd=Decimal("0"),
        net_income_hkd=net_income_hkd,
        income_flow_ids=[],
        expense_flow_ids=[],
        outbound_payments=[],
    )


def _make_entity(entity_id: str, jurisdiction: JurisdictionCode) -> EntityRecord:
    from tributary.common.models_entity import EntityType
    return EntityRecord(
        entity_id=entity_id,
        name=entity_id,
        entity_type=EntityType.SUBSIDIARY,
        resident_jurisdiction=jurisdiction,
        incorporation_jurisdiction=jurisdiction,
        is_group_member=True,
    )


def _make_group_relief_rule(jurisdiction: JurisdictionCode) -> Rule:
    return Rule(
        id="group_relief",
        jurisdiction=jurisdiction,
        type=RuleType.OBLIGATION_TRIGGER,
        category=RuleCategory.GROUP_RELIEF,
        parameters=RuleParameters(relief_mechanism="group_relief"),
        as_of_date=date(2025, 1, 1),
        source_citation="Test statute §1",
    )


class TestScanGroupRelief:
    """Tests for the scan_group_relief scanner."""

    def test_opportunity_emitted_when_rule_exists(self) -> None:
        """Income entity A + loss entity B with a GROUP_RELIEF rule → one opportunity."""
        income = _make_base("A", "GB", Decimal("1000000"))
        loss = _make_base("B", "GB", Decimal("-400000"))
        bases = {"A": income, "B": loss}
        entities = [_make_entity("A", "GB"), _make_entity("B", "GB")]

        loader = MagicMock()
        loader.get_rules.return_value = [_make_group_relief_rule("GB")]

        opportunities = scan_group_relief(bases, entities, loader)

        assert len(opportunities) == 1
        opp = opportunities[0]
        assert opp.income_entity_id == "A"
        assert opp.loss_entity_id == "B"
        assert opp.available_income_hkd == Decimal("1000000")
        assert opp.unused_loss_hkd == Decimal("400000")
        assert opp.relief_mechanism == GroupReliefMechanism.GROUP_RELIEF
        assert opp.applicable_rule_id == "group_relief"
        assert opp.needs_review is True

    def test_no_opportunity_when_no_rule(self) -> None:
        """Income entity A + loss entity B but no GROUP_RELIEF rule → empty list."""
        income = _make_base("A", "SG", Decimal("500000"))
        loss = _make_base("B", "HK", Decimal("-200000"))
        bases = {"A": income, "B": loss}
        entities = [_make_entity("A", "SG"), _make_entity("B", "HK")]

        loader = MagicMock()
        loader.get_rules.return_value = []

        opportunities = scan_group_relief(bases, entities, loader)

        assert opportunities == []

    def test_both_positive_no_opportunity(self) -> None:
        """Two profitable entities → no opportunity (no loss entity)."""
        a = _make_base("A", "HK", Decimal("800000"))
        b = _make_base("B", "HK", Decimal("200000"))
        bases = {"A": a, "B": b}
        entities = [_make_entity("A", "HK"), _make_entity("B", "HK")]

        loader = MagicMock()
        loader.get_rules.return_value = [_make_group_relief_rule("HK")]

        opportunities = scan_group_relief(bases, entities, loader)

        assert opportunities == []

    def test_both_loss_no_opportunity(self) -> None:
        """Two loss entities → no opportunity (no income entity)."""
        a = _make_base("A", "HK", Decimal("-100000"))
        b = _make_base("B", "DE", Decimal("-50000"))
        bases = {"A": a, "B": b}
        entities = [_make_entity("A", "HK"), _make_entity("B", "DE")]

        loader = MagicMock()
        loader.get_rules.return_value = [_make_group_relief_rule("HK")]

        opportunities = scan_group_relief(bases, entities, loader)

        assert opportunities == []

    def test_golden_scenario_produces_zero_opportunities(self) -> None:
        """Regression guard: HK/DE/FR have no bilateral GROUP_RELIEF rules → zero opportunities."""
        loader = JSONRulePackLoader(RULES_DIR)
        entities = [
            _make_entity("MERID-HK", "HK"),
            _make_entity("MERID-DE", "DE"),
            _make_entity("MERID-FR", "FR"),
        ]
        bases = {
            "MERID-HK": _make_base("MERID-HK", "HK", Decimal("2700000")),
            "MERID-DE": _make_base("MERID-DE", "DE", Decimal("300000")),
            "MERID-FR": _make_base("MERID-FR", "FR", Decimal("-150000")),
        }

        opportunities = scan_group_relief(bases, entities, loader)

        assert opportunities == [], (
            f"Golden scenario should produce 0 group-relief opportunities; got {len(opportunities)}"
        )
