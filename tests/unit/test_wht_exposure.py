"""
Module: test_wht_exposure
Layer: test-unit
Purpose: Unit tests for engine.wht_exposure — the WHT over-withheld scanner.
    Verifies that ConflictFlag(WHT_OVER_WITHHELD) is emitted when a treaty rate
    was available but the domestic rate was applied, and that no flag fires when
    the treaty was already applied or when no treaty exists.
Dependencies: decimal, datetime, pytest, tributary.common, tributary.engine, tributary.rules
Used by: make test
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tests.support.fakes import CollectingGraphWriter, FakeGraphReader
from tributary.common.models import (
    ActivityType,
    ConflictType,
    EngineRunResult,
    FiscalPeriod,
    JurisdictionCode,
    ObligationResult,
    ObligationType,
    OwnershipRecord,
)
from tributary.engine.aggregator import OutboundPayment
from tributary.engine.attribution_stub import AttributionStub
from tributary.engine.runner import EngineRunner
from tributary.engine.wht_exposure import scan_wht_exposure
from tributary.rules.loader import JSONRulePackLoader

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DE: JurisdictionCode = "DE"
_HK: JurisdictionCode = "HK"
_FR: JurisdictionCode = "FR"

_PERIOD_DE = FiscalPeriod(
    jurisdiction=_DE,
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
)


def _make_obligation(
    flow_id: str,
    payer_jur: JurisdictionCode,
    rate: Decimal,
    gross_hkd: Decimal,
    treaty_citation=None,
) -> ObligationResult:
    """Build a minimal WHT ObligationResult for testing."""
    from tributary.common.models import ComputationStep
    net = gross_hkd * rate
    return ObligationResult(
        obligation_id=f"OBL-{flow_id}",
        entity_id="TEST-ENTITY",
        jurisdiction=payer_jur,
        obligation_type=ObligationType.WHT,
        fiscal_period=_PERIOD_DE,
        taxable_base_hkd=gross_hkd,
        rate=rate,
        gross_amount_hkd=gross_hkd * Decimal("0.25"),
        treaty_relief_hkd=Decimal("0"),
        net_amount_hkd=net,
        rule_id="TEST-RULE",
        as_of_date=date(2025, 1, 1),
        source_citation="Test rule",
        treaty_citation=treaty_citation,
        source_flow_ids=[flow_id],
        computation_trace=[
            ComputationStep(
                step_name="apply_domestic_rate",
                input_value_hkd=gross_hkd,
                rule_id="TEST-RULE",
                rule_as_of_date=date(2025, 1, 1),
                result_value_hkd=gross_hkd * Decimal("0.25"),
                note="Test",
            )
        ],
        needs_review=False,
    )


def _make_payment(
    flow_id: str,
    payer_jur: JurisdictionCode,
    payee_jur: JurisdictionCode,
    activity: ActivityType = ActivityType.DIVIDEND,
    gross_hkd: Decimal = Decimal("1500000"),
) -> OutboundPayment:
    return OutboundPayment(
        flow_id=flow_id,
        activity=activity,
        gross_hkd=gross_hkd,
        payer_entity_id="LENOVO-DE",
        payer_jurisdiction=payer_jur,
        payee_entity_id="LENOVO-HK",
        payee_jurisdiction=payee_jur,
    )


class _OwningFakeReader:
    """Minimal GraphReader stub that satisfies DE→HK ownership checks for WHT treaty."""

    def get_entity_ownership(self, entity_id: str) -> list[OwnershipRecord]:
        """Return a 100% holding from LENOVO-HK in LENOVO-DE, held since 2020."""
        return [
            OwnershipRecord(
                owner_entity_id="LENOVO-HK",
                owned_entity_id="LENOVO-DE",
                ownership_pct=Decimal("100"),
                effective_from=date(2020, 1, 1),
                effective_to=None,
            )
        ]


# ---------------------------------------------------------------------------
# Test: over-withheld flag fires when domestic rate applied despite treaty
# ---------------------------------------------------------------------------

class TestOverWithheldFlag:
    @pytest.fixture(scope="class")
    def loader(self):
        return JSONRulePackLoader()

    @pytest.fixture(scope="class")
    def over_withheld_obligation(self):
        """DE→HK dividend withheld at domestic 25% (no treaty applied)."""
        return _make_obligation(
            flow_id="T-OW",
            payer_jur=_DE,
            rate=Decimal("0.25"),
            gross_hkd=Decimal("1500000"),
            treaty_citation=None,
        )

    @pytest.fixture(scope="class")
    def payment(self):
        return _make_payment("T-OW", _DE, _HK)

    @pytest.fixture(scope="class")
    def flags(self, over_withheld_obligation, payment, loader):
        return scan_wht_exposure(
            wht_obligations=[over_withheld_obligation],
            payments=[payment],
            loader=loader,
            reader=_OwningFakeReader(),
            period=_PERIOD_DE,
        )

    def test_one_flag_emitted(self, flags):
        assert len(flags) == 1

    def test_conflict_type(self, flags):
        assert flags[0].conflict_type == ConflictType.WHT_OVER_WITHHELD

    def test_conflict_id_contains_flow(self, flags):
        assert "T-OW" in flags[0].conflict_id

    def test_jurisdictions(self, flags):
        assert set(flags[0].jurisdictions) == {"DE", "HK"}

    def test_entities(self, flags):
        assert set(flags[0].entities) == {"LENOVO-DE", "LENOVO-HK"}

    def test_pe_tax_is_actual_wht(self, flags):
        """pe_tax_hkd holds the actual amount withheld (25% × 1,500,000 = 375,000)."""
        assert flags[0].pe_tax_hkd == Decimal("375000")

    def test_residence_tax_is_treaty_entitlement(self, flags):
        """residence_tax_before_relief_hkd = treaty rate (5%) × base = 75,000."""
        assert flags[0].residence_tax_before_relief_hkd == Decimal("75000")

    def test_relieved_amount_is_over_withheld(self, flags):
        """relieved_amount = 375,000 - 75,000 = 300,000."""
        assert flags[0].relieved_amount_hkd == Decimal("300000")

    def test_residual_double_tax_is_zero(self, flags):
        assert flags[0].residual_double_tax_hkd == Decimal("0")

    def test_treaty_rule_referenced(self, flags):
        assert flags[0].treaty_rule_id == "DEHK-DTA-DIVIDEND"

    def test_needs_review(self, flags):
        assert flags[0].needs_review is True


# ---------------------------------------------------------------------------
# Test: no flag when treaty citation already present (treaty was applied)
# ---------------------------------------------------------------------------

class TestNoFlagWhenTreatyApplied:
    @pytest.fixture(scope="class")
    def loader(self):
        return JSONRulePackLoader()

    @pytest.fixture(scope="class")
    def treaty_applied_obligation(self, loader):
        """DE→HK dividend with treaty citation already set (treaty was applied)."""
        from tributary.common.models import RuleCitation
        from tributary.rules.models import RuleCategory
        treaty_rules = loader.get_treaty_rules("DE", "HK")
        rule = next(r for r in treaty_rules if r.category == RuleCategory.TREATY_DIVIDEND)
        citation = RuleCitation(
            rule_id=rule.id,
            jurisdiction=_DE,
            as_of_date=rule.as_of_date,
            source_citation=rule.source_citation,
        )
        return _make_obligation(
            flow_id="T-OK",
            payer_jur=_DE,
            rate=Decimal("0.05"),
            gross_hkd=Decimal("1500000"),
            treaty_citation=citation,
        )

    @pytest.fixture(scope="class")
    def payment(self):
        return _make_payment("T-OK", _DE, _HK)

    def test_no_flag_when_treaty_applied(self, treaty_applied_obligation, payment, loader):
        flags = scan_wht_exposure(
            wht_obligations=[treaty_applied_obligation],
            payments=[payment],
            loader=loader,
            reader=_OwningFakeReader(),
            period=_PERIOD_DE,
        )
        assert flags == []


# ---------------------------------------------------------------------------
# Test: no flag when no treaty exists for the jurisdiction pair
# ---------------------------------------------------------------------------

class TestNoFlagWhenNoTreaty:
    @pytest.fixture(scope="class")
    def loader(self):
        return JSONRulePackLoader()

    def test_no_flag_for_pair_without_treaty(self, loader):
        """FR→HK management fee: no FR-HK treaty in pack → no flag."""
        _PERIOD_FR = FiscalPeriod(
            jurisdiction=_FR,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        )
        obligation = _make_obligation(
            flow_id="T-NOTREATY",
            payer_jur=_FR,
            rate=Decimal("0.128"),
            gross_hkd=Decimal("300000"),
            treaty_citation=None,
        )
        payment = OutboundPayment(
            flow_id="T-NOTREATY",
            activity=ActivityType.MANAGEMENT_FEE,
            gross_hkd=Decimal("300000"),
            payer_entity_id="LENOVO-FR",
            payer_jurisdiction=_FR,
            payee_entity_id="LENOVO-HK",
            payee_jurisdiction=_HK,
        )
        flags = scan_wht_exposure(
            wht_obligations=[obligation],
            payments=[payment],
            loader=loader,
            reader=_OwningFakeReader(),
            period=_PERIOD_FR,
        )
        assert flags == []


# ---------------------------------------------------------------------------
# Test: golden scenario produces no WHT_OVER_WITHHELD flags
# ---------------------------------------------------------------------------

class TestGoldenScenarioNoOverWithheld:
    @pytest.fixture(scope="class")
    def engine_results(self) -> list[EngineRunResult]:
        reader = FakeGraphReader()
        writer = CollectingGraphWriter()
        ai = AttributionStub()
        loader = JSONRulePackLoader()
        runner = EngineRunner(reader, writer, ai, loader, 2025)
        return runner.run()

    def test_no_wht_over_withheld_in_golden(self, engine_results):
        """All WHT in golden scenario applies the best available rate — no over-withheld flags."""
        over_withheld = [
            c
            for result in engine_results
            for c in result.conflicts
            if c.conflict_type == ConflictType.WHT_OVER_WITHHELD
        ]
        assert over_withheld == []


# ---------------------------------------------------------------------------
# Branch coverage: _check_obligation early-return paths
# ---------------------------------------------------------------------------


class TestCheckObligationBranches:
    """Direct tests for _check_obligation() branches missed by happy-path tests."""

    @pytest.fixture
    def loader(self):
        return JSONRulePackLoader()

    def _period(self, jur: JurisdictionCode) -> FiscalPeriod:
        return FiscalPeriod(
            jurisdiction=jur,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        )

    def test_non_wht_obligation_returns_no_flag(self, loader):
        """_check_obligation must return None for a CIT obligation (not WHT)."""
        from tributary.common.models import ComputationStep

        cit_obligation = ObligationResult(
            obligation_id="OBL-CIT",
            entity_id="TEST",
            jurisdiction=_DE,
            obligation_type=ObligationType.CIT,
            fiscal_period=self._period(_DE),
            taxable_base_hkd=Decimal("1000000"),
            rate=Decimal("0.15"),
            gross_amount_hkd=Decimal("150000"),
            treaty_relief_hkd=Decimal("0"),
            net_amount_hkd=Decimal("150000"),
            rule_id="TEST",
            as_of_date=date(2025, 1, 1),
            source_citation="Test",
            treaty_citation=None,
            source_flow_ids=["T-CIT"],
            computation_trace=[
                ComputationStep(
                    step_name="apply_rate",
                    input_value_hkd=Decimal("1000000"),
                    rule_id="TEST",
                    rule_as_of_date=date(2025, 1, 1),
                    result_value_hkd=Decimal("150000"),
                    note="CIT",
                )
            ],
            needs_review=False,
        )
        flags = scan_wht_exposure(
            wht_obligations=[cit_obligation],
            payments=[],
            loader=loader,
            reader=_OwningFakeReader(),
            period=self._period(_DE),
        )
        assert flags == []

    def test_no_source_flow_ids_returns_no_flag(self, loader):
        """_check_obligation must return None when source_flow_ids is empty."""
        from tributary.common.models import ComputationStep

        obligation = ObligationResult(
            obligation_id="OBL-EMPTY",
            entity_id="TEST",
            jurisdiction=_DE,
            obligation_type=ObligationType.WHT,
            fiscal_period=self._period(_DE),
            taxable_base_hkd=Decimal("500000"),
            rate=Decimal("0.25"),
            gross_amount_hkd=Decimal("125000"),
            treaty_relief_hkd=Decimal("0"),
            net_amount_hkd=Decimal("125000"),
            rule_id="TEST",
            as_of_date=date(2025, 1, 1),
            source_citation="Test",
            treaty_citation=None,
            source_flow_ids=[],  # empty → early return
            computation_trace=[
                ComputationStep(
                    step_name="apply_rate",
                    input_value_hkd=Decimal("500000"),
                    rule_id="TEST",
                    rule_as_of_date=date(2025, 1, 1),
                    result_value_hkd=Decimal("125000"),
                    note="WHT",
                )
            ],
            needs_review=False,
        )
        flags = scan_wht_exposure(
            wht_obligations=[obligation],
            payments=[],
            loader=loader,
            reader=_OwningFakeReader(),
            period=self._period(_DE),
        )
        assert flags == []

    def test_payment_not_in_map_returns_no_flag(self, loader):
        """_check_obligation must log a warning and return None when flow_id not in payment map."""
        obligation = _make_obligation(
            flow_id="T-MISSING",
            payer_jur=_DE,
            rate=Decimal("0.25"),
            gross_hkd=Decimal("500000"),
        )
        # payments list is empty — flow_id will not be found
        flags = scan_wht_exposure(
            wht_obligations=[obligation],
            payments=[],
            loader=loader,
            reader=_OwningFakeReader(),
            period=self._period(_DE),
        )
        assert flags == []

    def test_rate_at_treaty_entitlement_no_flag(self, loader):
        """No flag when the applied rate is already at or below the treaty rate."""
        # DE-HK treaty dividend rate is 5%; apply exactly 5% → no over-withholding
        obligation = _make_obligation(
            flow_id="T-EXACT",
            payer_jur=_DE,
            rate=Decimal("0.05"),
            gross_hkd=Decimal("1500000"),
            treaty_citation=None,  # no treaty in obligation, but rate is already correct
        )
        payment = _make_payment("T-EXACT", _DE, _HK)
        flags = scan_wht_exposure(
            wht_obligations=[obligation],
            payments=[payment],
            loader=loader,
            reader=_OwningFakeReader(),
            period=self._period(_DE),
        )
        assert flags == []
