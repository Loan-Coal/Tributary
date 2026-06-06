"""
Module: test_engine_units
Layer: test-unit
Purpose: Unit tests for individual deterministic engine sub-modules: money helpers, loss ledger,
    CIT engine, trade-tax engine, WHT engine, thresholds, deadlines, PE detection, and conflict.
    Each test exercises one sub-engine in isolation using minimal in-memory fixtures.
    No I/O, no Neo4j, no AI calls.
Dependencies: datetime, decimal, pytest, tributary.engine.*, tributary.common
Used by: make test, make test-engine
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tributary.common.models import (
    ActivityType,
    ConflictType,
    FiscalPeriod,
    JurisdictionCode,
    ObligationType,
    PriorPeriodLoss,
    ReliefMechanism,
)
from tributary.engine.money import effective_rate, round_hkd


# ===========================================================================
# money.py
# ===========================================================================

class TestRoundHkd:
    def test_exact_integer(self):
        assert round_hkd(Decimal("1000")) == Decimal("1000")

    def test_rounds_half_up(self):
        assert round_hkd(Decimal("100.5")) == Decimal("101")

    def test_rounds_down_below_half(self):
        assert round_hkd(Decimal("100.499")) == Decimal("100")

    def test_large_amount(self):
        # 1,023,750 × 0.25 = 255,937.50 → 255,938
        assert round_hkd(Decimal("1023750") * Decimal("0.25")) == Decimal("255938")

    def test_cit_effective_rate_result(self):
        # 1,023,750 × 15.825% = 162,008.4375 → 162,008
        rate = effective_rate(Decimal("0.15"), Decimal("0.055"))
        assert round_hkd(Decimal("1023750") * rate) == Decimal("162008")


class TestEffectiveRate:
    def test_no_surcharge(self):
        assert effective_rate(Decimal("0.165"), None) == Decimal("0.165")

    def test_with_surcharge(self):
        # 15% × 1.055 = 0.15825
        result = effective_rate(Decimal("0.15"), Decimal("0.055"))
        assert result == Decimal("0.15825")

    def test_zero_rate(self):
        assert effective_rate(Decimal("0"), Decimal("0.055")) == Decimal("0")


# ===========================================================================
# loss_ledger.py
# ===========================================================================

from tributary.engine.loss_ledger import LossOffsetResult, apply_loss_offset


def _loss(entity: str, jur: str, amount: Decimal, start=date(2024, 1, 1), end=date(2024, 12, 31)) -> PriorPeriodLoss:
    return PriorPeriodLoss(
        loss_id=f"{entity}-{jur}-{start}",
        entity_id=entity,
        jurisdiction=jur,
        loss_period_start=start,
        loss_period_end=end,
        original_loss_hkd=amount,
        remaining_loss_hkd=amount,
        created_at=date(2025, 1, 1),
    )


class TestLossLedgerNoRule:
    def test_unlimited_offset(self):
        loss = _loss("E1", "HK", Decimal("500000"))
        result = apply_loss_offset(Decimal("700000"), [loss], None, "HK")
        assert result.post_loss_base_hkd == Decimal("200000")
        assert result.total_offset_hkd == Decimal("500000")
        assert result.limitation_applied is False

    def test_full_offset_when_loss_gt_base(self):
        loss = _loss("E1", "HK", Decimal("1000000"))
        result = apply_loss_offset(Decimal("400000"), [loss], None, "HK")
        assert result.post_loss_base_hkd == Decimal("0")
        assert result.total_offset_hkd == Decimal("400000")

    def test_no_loss_zero_offset(self):
        result = apply_loss_offset(Decimal("900000"), [], None, "HK")
        assert result.post_loss_base_hkd == Decimal("900000")
        assert result.total_offset_hkd == Decimal("0")


class TestLossLedgerMindestbesteuerung:
    """German §10d: full offset ≤ de_minimis; 60% cap above."""

    @pytest.fixture
    def de_rule(self):
        from tributary.rules.loader import JSONRulePackLoader
        from tributary.rules.models import RuleCategory
        loader = JSONRulePackLoader()
        rules = loader.get_rules("DE", RuleCategory.LOSS_RELIEF)
        assert rules, "DE loss-relief rule not found in pack"
        return rules[0]

    def test_below_threshold_no_cap(self, de_rule):
        """Base < 8,500,000 de-minimis → full offset allowed."""
        loss = _loss("E1", "DE", Decimal("1600000"))
        result = apply_loss_offset(Decimal("1901250"), [loss], de_rule, "DE")
        assert result.post_loss_base_hkd == Decimal("301250")
        assert result.total_offset_hkd == Decimal("1600000")
        assert result.limitation_applied is False

    def test_above_threshold_60_cap(self, de_rule):
        """Base > 8,500,000 → only 60% of excess above de-minimis can be offset."""
        # Base: 10,000,000; de_minimis: 8,500,000; excess: 1,500,000; cap: 8,500,000 + 0.6×1,500,000 = 9,400,000
        loss = _loss("E1", "DE", Decimal("10000000"))
        result = apply_loss_offset(Decimal("10000000"), [loss], de_rule, "DE")
        assert result.limitation_applied is True
        assert result.post_loss_base_hkd == Decimal("600000")  # 10M - 9.4M

    def test_partial_remaining_loss(self, de_rule):
        """If available loss < allowable, only the available loss is consumed."""
        loss = _loss("E1", "DE", Decimal("300000"))
        result = apply_loss_offset(Decimal("500000"), [loss], de_rule, "DE")
        assert result.total_offset_hkd == Decimal("300000")
        assert result.post_loss_base_hkd == Decimal("200000")
        assert result.records[0].remaining_loss_hkd == Decimal("0")


# ===========================================================================
# thresholds.py
# ===========================================================================

from tributary.engine.aggregator import EntityBase
from tributary.engine.thresholds import pe_days_check, vat_threshold_check, zinsschranke_check


def _base(
    entity_id="E1",
    jur="DE",
    third_party=Decimal("0"),
    ic_taxable=Decimal("0"),
    deductible=Decimal("0"),
    interest=Decimal("0"),
) -> EntityBase:
    net = third_party + ic_taxable - deductible
    return EntityBase(
        entity_id=entity_id,
        jurisdiction=jur,
        period=FiscalPeriod(
            jurisdiction=jur,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        ),
        third_party_income_hkd=third_party,
        ic_income_taxable_hkd=ic_taxable,
        deductible_expense_hkd=deductible,
        interest_expense_hkd=interest,
        net_income_hkd=net,
        income_flow_ids=[],
        expense_flow_ids=[],
        outbound_payments=[],
    )


class TestZinsschranke:
    @pytest.fixture
    def barrier_rule(self):
        from tributary.rules.loader import JSONRulePackLoader
        from tributary.rules.models import RuleCategory
        rules = JSONRulePackLoader().get_rules("DE", RuleCategory.INTEREST_BARRIER)
        return rules[0]

    def test_not_breached_golden(self, barrier_rule):
        """DE golden scenario: 320,000 interest < 973,500 cap → not breached."""
        base = _base(
            jur="DE",
            third_party=Decimal("6200000"),
            ic_taxable=Decimal("45000"),
            deductible=Decimal("3320000"),  # 3,000,000 royalties + 320,000 interest
            interest=Decimal("320000"),
        )
        result = zinsschranke_check(base, barrier_rule)
        assert result.breached is False
        assert result.actual_value_hkd == Decimal("320000")

    def test_breached(self, barrier_rule):
        """Interest > 30% EBITDA → breached."""
        base = _base(
            jur="DE",
            third_party=Decimal("1000000"),
            ic_taxable=Decimal("0"),
            deductible=Decimal("400000"),
            interest=Decimal("400000"),
        )
        # EBITDA proxy = 1,000,000 - 0 (non-interest deductible = 0) = 1,000,000; cap = 300,000
        result = zinsschranke_check(base, barrier_rule)
        assert result.breached is True

    def test_loss_making_no_interest_not_breached(self, barrier_rule):
        """W6c.3 regression (ISSUE-012): loss-making entity with zero interest must not be flagged.

        Before the EBITDA clamp, negative EBITDA yielded a negative cap, causing
        `0 > negative_cap` to evaluate True — a false-positive Zinsschranke flag.
        """
        base = _base(
            jur="DE",
            third_party=Decimal("200000"),
            ic_taxable=Decimal("0"),
            deductible=Decimal("900000"),  # large losses, but NO interest component
            interest=Decimal("0"),
        )
        # Unclamped EBITDA proxy = 200,000 - 900,000 = -700,000; cap = -210,000
        # Bug: 0 > -210,000 → True (false positive)
        # Fixed: clamp to 0; cap = 0; 0 > 0 → False
        result = zinsschranke_check(base, barrier_rule)
        assert result.breached is False
        assert result.threshold_value_hkd >= Decimal("0")

    def test_loss_making_with_interest_cap_non_negative(self, barrier_rule):
        """W6c.3 regression (ISSUE-012): negative EBITDA must produce a non-negative cap.

        When EBITDA is negative, the 30%-cap must be clamped to 0 — not negative.
        A negative threshold_value_hkd is numerically incoherent.
        """
        base = _base(
            jur="DE",
            third_party=Decimal("500000"),
            ic_taxable=Decimal("0"),
            deductible=Decimal("2000000"),  # includes interest below
            interest=Decimal("300000"),
        )
        # non_interest_deductible = 2,000,000 - 300,000 = 1,700,000
        # EBITDA proxy = 500,000 - 1,700,000 = -1,200,000 (negative)
        # Without clamp: cap = 0.30 × -1,200,000 = -360,000 (wrong)
        # With clamp: cap = 0.30 × 0 = 0 (correct — no interest deductible when EBITDA ≤ 0)
        result = zinsschranke_check(base, barrier_rule)
        assert result.threshold_value_hkd >= Decimal("0")


class TestPeDaysCheck:
    @pytest.fixture
    def pe_rule(self):
        from tributary.rules.loader import JSONRulePackLoader
        from tributary.rules.models import RuleCategory
        rules = JSONRulePackLoader().get_treaty_rules("DE", "FR")
        return next(r for r in rules if r.category.value == "treaty_pe")

    def test_breached_185_days(self, pe_rule):
        result = pe_days_check("MERID-DE", "FR", 185, pe_rule)
        assert result.breached is True
        assert result.actual_value_hkd == Decimal("185")
        assert result.threshold_value_hkd == Decimal("183")

    def test_not_breached_182_days(self, pe_rule):
        result = pe_days_check("MERID-DE", "FR", 182, pe_rule)
        assert result.breached is False

    def test_exactly_threshold_not_breached(self, pe_rule):
        """Exactly 183 days is not strictly greater than — not triggered."""
        result = pe_days_check("MERID-DE", "FR", 183, pe_rule)
        assert result.breached is False


# ===========================================================================
# deadlines.py
# ===========================================================================

from tributary.engine.deadlines import compute_deadline


def _period(jur: str, start: date, end: date) -> FiscalPeriod:
    return FiscalPeriod(jurisdiction=jur, start_date=start, end_date=end)


class TestDeadlines:
    @pytest.fixture
    def hk_deadline_rule(self):
        from tributary.rules.loader import JSONRulePackLoader
        from tributary.rules.models import RuleCategory
        rules = JSONRulePackLoader().get_rules("HK", RuleCategory.CIT_DEADLINE)
        return rules[0]

    @pytest.fixture
    def de_deadline_rule(self):
        from tributary.rules.loader import JSONRulePackLoader
        from tributary.rules.models import RuleCategory
        rules = JSONRulePackLoader().get_rules("DE", RuleCategory.CIT_DEADLINE)
        return rules[0]

    def test_hk_same_year_filing(self, hk_deadline_rule):
        """HK: period ends Mar 31 2026, filing month Apr 30 is after → same year (2026)."""
        period = _period("HK", date(2025, 4, 1), date(2026, 3, 31))
        result = compute_deadline("MERID-HK", ObligationType.CIT, period, hk_deadline_rule)
        assert result.filing_deadline == date(2026, 4, 30)

    def test_de_next_year_filing(self, de_deadline_rule):
        """DE: period ends Dec 31 2025, filing month Jul 31 is before in calendar order → next year (2026)."""
        period = _period("DE", date(2025, 1, 1), date(2025, 12, 31))
        result = compute_deadline("MERID-DE", ObligationType.CIT, period, de_deadline_rule)
        assert result.filing_deadline == date(2026, 7, 31)


# ===========================================================================
# conflict.py
# ===========================================================================

from tributary.engine.conflict import _resolve


class TestConflictResolve:
    def test_exemption_zero_residual(self):
        """Exemption: residence gives up its tax claim; residual = 0."""
        relieved, residual = _resolve(
            ReliefMechanism.EXEMPTION, Decimal("255938"), Decimal("162008")
        )
        assert relieved == Decimal("162008")
        assert residual == Decimal("0")

    def test_credit_capped_at_residence(self):
        """Credit: relief capped at lower of (pe_tax, residence_tax)."""
        relieved, residual = _resolve(
            ReliefMechanism.CREDIT, Decimal("255938"), Decimal("162008")
        )
        assert relieved == Decimal("162008")
        assert residual == Decimal("255938") - Decimal("162008")

    def test_credit_pe_lower_than_residence(self):
        """Credit: when PE tax is lower than residence tax, full PE tax is relieved."""
        relieved, residual = _resolve(
            ReliefMechanism.CREDIT, Decimal("100000"), Decimal("200000")
        )
        assert relieved == Decimal("100000")
        assert residual == Decimal("0")


# ===========================================================================
# conflict + pe integration (no graph layer)
# ===========================================================================

from tributary.engine.conflict import build_pe_conflict
from tributary.engine.pe import PeAttribution
from tributary.common.models import ThresholdResult


class TestBuildPeConflict:
    @pytest.fixture
    def pe_attr(self):
        threshold = ThresholdResult(
            entity_id="MERID-DE",
            jurisdiction="FR",
            rule_id="DEFR-DTA-PE",
            threshold_name="service_pe_days",
            threshold_value_hkd=Decimal("183"),
            actual_value_hkd=Decimal("185"),
            breached=True,
            as_of_date=date(2017, 1, 1),
            source_citation="DE-FR DTA Art.5",
        )
        return PeAttribution(
            entity_id="MERID-DE",
            residence_jurisdiction="DE",
            pe_jurisdiction="FR",
            total_days=185,
            attribution_pct=Decimal("0.35"),
            attributed_income_hkd=Decimal("1023750"),
            threshold=threshold,
            treaty_pe_rule_id="DEFR-DTA-PE",
            trigger_presence_ids=["PRES-DE-FR-2025"],
        )

    @pytest.fixture
    def rules(self):
        from tributary.rules.loader import JSONRulePackLoader
        from tributary.rules.models import RuleCategory
        loader = JSONRulePackLoader()
        de_cit = loader.get_rules("DE", RuleCategory.CIT_RATE)[0]
        fr_cit = loader.get_rules("FR", RuleCategory.CIT_RATE)[0]
        elimination = next(
            r for r in loader.get_treaty_rules("DE", "FR")
            if r.category.value == "treaty_elimination"
        )
        return de_cit, fr_cit, elimination

    def test_conflict_figures_match_expected(self, pe_attr, rules):
        de_cit, fr_cit, elim = rules
        conflict = build_pe_conflict(pe_attr, de_cit, fr_cit, elim, "MERID-FR", 2025)
        assert conflict.conflict_id == "PE-MERID-DE-DE-2025"
        assert conflict.attributed_base_hkd == Decimal("1023750")
        assert conflict.pe_tax_hkd == Decimal("255938")
        assert conflict.residence_tax_before_relief_hkd == Decimal("162008")
        assert conflict.relief_mechanism == ReliefMechanism.EXEMPTION
        assert conflict.residual_double_tax_hkd == Decimal("0")

    def test_conflict_type(self, pe_attr, rules):
        de_cit, fr_cit, elim = rules
        conflict = build_pe_conflict(pe_attr, de_cit, fr_cit, elim, "MERID-FR", 2025)
        assert conflict.conflict_type == ConflictType.SERVICE_PE_DOUBLE_TAX

    def test_two_entities_same_year_produce_distinct_ids(self, rules):
        """Two distinct entities triggering PE in the same year must get different conflict IDs."""
        de_cit, fr_cit, elim = rules

        def _make_pe(entity_id: str, residence: str) -> PeAttribution:
            t = ThresholdResult(
                entity_id=entity_id,
                jurisdiction="FR",
                rule_id="DEFR-DTA-PE",
                threshold_name="service_pe_days",
                threshold_value_hkd=Decimal("183"),
                actual_value_hkd=Decimal("185"),
                breached=True,
                as_of_date=date(2017, 1, 1),
                source_citation="DE-FR DTA Art.5",
            )
            return PeAttribution(
                entity_id=entity_id,
                residence_jurisdiction=residence,
                pe_jurisdiction="FR",
                total_days=185,
                attribution_pct=Decimal("0.35"),
                attributed_income_hkd=Decimal("1023750"),
                threshold=t,
                treaty_pe_rule_id="DEFR-DTA-PE",
                trigger_presence_ids=[f"PRES-{entity_id}-FR-2025"],
            )

        conflict_de = build_pe_conflict(_make_pe("MERID-DE", "DE"), de_cit, fr_cit, elim, "MERID-FR", 2025)
        conflict_hk = build_pe_conflict(_make_pe("MERID-HK", "HK"), de_cit, fr_cit, elim, "MERID-FR", 2025)
        assert conflict_de.conflict_id != conflict_hk.conflict_id


# ===========================================================================
# aggregator edge cases
# ===========================================================================

from tests.support.fakes import FakeGraphReader
from tributary.engine.aggregator import aggregate_entity
from tributary.rules.loader import JSONRulePackLoader
from tributary.engine.periods import compute_period


class TestAggregator:
    @pytest.fixture(scope="class")
    def reader(self):
        return FakeGraphReader()

    @pytest.fixture(scope="class")
    def loader(self):
        return JSONRulePackLoader()

    def test_merid_de_net_income(self, reader, loader):
        """MERID-DE net income before PE/loss should be 2,925,000."""
        period = compute_period(loader.get_fiscal_calendar("DE"), 2025)
        base = aggregate_entity(reader, loader, "MERID-DE", "DE", period)
        assert base.net_income_hkd == Decimal("2925000")

    def test_merid_de_interest_expense(self, reader, loader):
        """T006 interest: 320,000 is tracked as interest_expense for Zinsschranke."""
        period = compute_period(loader.get_fiscal_calendar("DE"), 2025)
        base = aggregate_entity(reader, loader, "MERID-DE", "DE", period)
        assert base.interest_expense_hkd == Decimal("320000")

    def test_merid_de_outbound_payments(self, reader, loader):
        """MERID-DE has outbound WHT-bearing payments: T005 (dividend), T006 (interest)."""
        period = compute_period(loader.get_fiscal_calendar("DE"), 2025)
        base = aggregate_entity(reader, loader, "MERID-DE", "DE", period)
        flow_ids = {p.flow_id for p in base.outbound_payments}
        assert "T005" in flow_ids
        assert "T006" in flow_ids

    def test_merid_hk_taxable_income(self, reader, loader):
        """MERID-HK taxable base: 2,400,000 (royalty) + 300,000 (mgmt fee) = 2,700,000."""
        period = compute_period(loader.get_fiscal_calendar("HK"), 2025)
        base = aggregate_entity(reader, loader, "MERID-HK", "HK", period)
        taxable = base.ic_income_taxable_hkd + base.third_party_income_hkd - base.deductible_expense_hkd
        assert taxable == Decimal("2700000")

    def test_merid_fr_includes_pe_income_via_adjustment(self, reader, loader):
        """MERID-FR's own base before PE attribution should be 3,100,000."""
        period = compute_period(loader.get_fiscal_calendar("FR"), 2025)
        base = aggregate_entity(reader, loader, "MERID-FR", "FR", period)
        # 2,800,000 (T009) + 600,000 (T002) - 300,000 (T007 mgmt fee expense)
        assert base.net_income_hkd == Decimal("3100000")


# ===========================================================================
# periods.py
# ===========================================================================

from tributary.engine.periods import compute_period
from tributary.common.models import FiscalCalendar


class TestPeriods:
    @pytest.fixture
    def hk_calendar(self):
        from tributary.rules.loader import JSONRulePackLoader
        loader = JSONRulePackLoader()
        return loader.get_fiscal_calendar("HK")

    @pytest.fixture
    def de_calendar(self):
        from tributary.rules.loader import JSONRulePackLoader
        loader = JSONRulePackLoader()
        return loader.get_fiscal_calendar("DE")

    def test_hk_period(self, hk_calendar):
        period = compute_period(hk_calendar, 2025)
        assert period.start_date == date(2025, 4, 1)
        assert period.end_date == date(2026, 3, 31)
        assert period.jurisdiction == "HK"

    def test_de_period(self, de_calendar):
        period = compute_period(de_calendar, 2025)
        assert period.start_date == date(2025, 1, 1)
        assert period.end_date == date(2025, 12, 31)
        assert period.jurisdiction == "DE"


# ===========================================================================
# loss_ledger.py — FIFO multi-period allocation
# ===========================================================================

class TestLossLedgerFifoMultiPeriod:
    """Verify FIFO ordering and remaining balance decrements across three loss records."""

    def test_fifo_oldest_consumed_first(self):
        """Three losses: oldest consumed fully before touching newer ones."""
        losses = [
            _loss("E1", "HK", Decimal("500000")),   # oldest
            _loss("E1", "HK", Decimal("700000")),   # middle
            _loss("E1", "HK", Decimal("900000")),   # newest
        ]
        # Base 600,000 — should consume 500K from oldest, 100K from middle
        result = apply_loss_offset(Decimal("600000"), losses, None, "HK")
        assert result.total_offset_hkd == Decimal("600000")
        assert result.post_loss_base_hkd == Decimal("0")
        records = result.records
        assert records[0].remaining_loss_hkd == Decimal("0")      # oldest: fully consumed
        assert records[1].remaining_loss_hkd == Decimal("600000") # middle: 100K used, 600K left
        assert records[2].remaining_loss_hkd == Decimal("900000") # newest: untouched

    def test_fifo_partial_total_offset_across_all_three(self):
        """Offset spanning all three loss records — total must match sum of consumed."""
        losses = [
            _loss("E1", "HK", Decimal("100000")),
            _loss("E1", "HK", Decimal("200000")),
            _loss("E1", "HK", Decimal("300000")),
        ]
        # Base 500,000 — consumes 100K + 200K + 200K of the 300K newest
        result = apply_loss_offset(Decimal("500000"), losses, None, "HK")
        assert result.total_offset_hkd == Decimal("500000")
        assert result.post_loss_base_hkd == Decimal("0")
        assert result.records[0].remaining_loss_hkd == Decimal("0")
        assert result.records[1].remaining_loss_hkd == Decimal("0")
        assert result.records[2].remaining_loss_hkd == Decimal("100000")

    def test_base_exceeds_all_losses_floor_at_zero(self):
        """If total losses are less than base, post_loss_base is base - total_losses."""
        losses = [
            _loss("E1", "HK", Decimal("200000")),
            _loss("E1", "HK", Decimal("300000")),
        ]
        result = apply_loss_offset(Decimal("1000000"), losses, None, "HK")
        assert result.total_offset_hkd == Decimal("500000")
        assert result.post_loss_base_hkd == Decimal("500000")


# ===========================================================================
# wht_engine.py — failure path: missing domestic WHT rule
# ===========================================================================

from tributary.engine.wht_engine import compute_wht
from tributary.engine.aggregator import OutboundPayment
from tributary.common.errors import EngineError
from tests.support.fakes import FakeGraphReader


def _payment(flow_id: str, activity: ActivityType) -> OutboundPayment:
    return OutboundPayment(
        flow_id=flow_id,
        activity=activity,
        gross_hkd=Decimal("500000"),
        payer_entity_id="MERID-HK",
        payee_entity_id="MERID-DE",
        payer_jurisdiction="HK",
        payee_jurisdiction="DE",
    )


class TestWhtMissingDomesticRule:
    @pytest.fixture
    def loader_without_wht(self):
        """Loader that returns HK rules — HK has no WHT on REVENUE activity."""
        from tributary.rules.loader import JSONRulePackLoader
        return JSONRulePackLoader()

    def test_engine_error_on_missing_domestic_wht_rule(self, loader_without_wht):
        """EngineError raised when no domestic WHT rule exists for the activity type."""
        reader = FakeGraphReader()
        period = FiscalPeriod(
            jurisdiction="HK",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
        )
        # REVENUE is not a WHT-bearing activity — no rule in any pack
        payment = _payment("T-WHT-FAIL", ActivityType.REVENUE)
        with pytest.raises(EngineError):
            compute_wht(reader, loader_without_wht, payment, period, needs_review=False)


# ===========================================================================
# wht_engine.py — W6c.1: treaty_rate=None must raise RulePackError, not apply 0%
# ===========================================================================

from tributary.common.errors import RulePackError
from tributary.engine.wht_engine import get_treaty_rate
from tributary.rules.models import Rule, RuleCategory, RuleType, RuleParameters


def _malformed_treaty_rule() -> Rule:
    """A treaty rule with treaty_rate=None (simulates a malformed/incomplete pack)."""
    return Rule(
        id="BAD-TREATY-NO-RATE",
        jurisdiction="DE",
        type=RuleType.TREATY,
        category=RuleCategory.TREATY_DIVIDEND,
        parameters=RuleParameters(treaty_rate=None, min_holding_pct=None, requires_eu=None),
        as_of_date=date(2024, 1, 1),
        source_citation="Malformed treaty pack — for regression test only",
    )


class _StubLoaderWithBadTreaty:
    """Loader that returns a single treaty rule with treaty_rate=None."""

    def get_treaty_rules(self, a: str, b: str) -> list[Rule]:
        return [_malformed_treaty_rule()]

    def get_rules(self, jur: str, cat: RuleCategory) -> list[Rule]:
        return []

    def get_rule(self, jur: str, rule_id: str) -> Rule:
        raise KeyError(rule_id)

    def get_fiscal_calendar(self, jur: str):  # type: ignore[return]
        raise KeyError(jur)


class TestWhtTreatyRateMissing:
    def test_none_treaty_rate_raises_rule_pack_error(self):
        """RulePackError raised when a treaty rule has treaty_rate=None (W6c.1).

        Before the fix, ``treaty_rate or Decimal("0")`` silently applies 0% WHT.
        After the fix, the engine fails fast with a typed error.
        """
        reader = FakeGraphReader()
        payment = OutboundPayment(
            flow_id="T-BAD-TREATY",
            activity=ActivityType.DIVIDEND,
            gross_hkd=Decimal("100000"),
            payer_entity_id="MERID-DE",
            payee_entity_id="MERID-HK",
            payer_jurisdiction="DE",
            payee_jurisdiction="HK",
        )
        with pytest.raises(RulePackError, match="treaty_rate"):
            get_treaty_rate(reader, _StubLoaderWithBadTreaty(), payment, date(2025, 12, 31))


# ===========================================================================
# runner.py — W6c.5: missing CIT rule raises EngineError, not IndexError
# ===========================================================================

from unittest.mock import MagicMock

from tributary.common.errors import EngineError
from tributary.engine.runner import EngineRunner


class _StubLoaderNoCit:
    """Loader that returns an empty list for every get_rules call."""

    def get_rules(self, jur: str, cat: RuleCategory) -> list[Rule]:
        return []

    def get_treaty_rules(self, a: str, b: str) -> list[Rule]:
        return []

    def get_rule(self, jur: str, rule_id: str) -> Rule:
        raise KeyError(rule_id)

    def get_fiscal_calendar(self, jur: str):  # type: ignore[return]
        raise KeyError(jur)


class TestRunnerMissingCitRule:
    @pytest.fixture
    def runner(self):
        return EngineRunner(
            reader=MagicMock(),
            writer=MagicMock(),
            ai=MagicMock(),
            loader=_StubLoaderNoCit(),
            reference_year=2025,
        )

    def test_engine_error_not_index_error_when_cit_rule_absent(self, runner):
        """EngineError (not IndexError) when _cit_rule() finds no CIT rule for a jurisdiction.

        Before the fix, get_rules()[0] raises bare IndexError.
        After the fix, the engine raises typed EngineError with a descriptive message.
        """
        with pytest.raises(EngineError, match="CIT"):
            runner._cit_rule("XX")
