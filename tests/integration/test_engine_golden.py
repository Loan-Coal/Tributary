"""
Module: test_engine_golden
Layer: test-integration
Purpose: End-to-end golden-scenario engine integration test. Runs the full deterministic engine
    against the golden fixtures (FakeGraphReader + AttributionStub + JSONRulePackLoader) and
    asserts that every obligation, WHT, threshold, and conflict value matches EXPECTED.md §7.
    If any value here diverges from the hand-computed ground truth the engine has a bug.
Dependencies: decimal, pytest, tests.support.fakes, tributary.engine, tributary.rules
Used by: make test-engine, make test
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from tests.support.fakes import CollectingGraphWriter, FakeGraphReader
from tributary.common.models import (
    ConflictFlag,
    ConflictType,
    EngineRunResult,
    ObligationType,
    ReliefMechanism,
)
from tributary.engine.attribution_stub import AttributionStub
from tributary.engine.runner import EngineRunner
from tributary.rules.loader import JSONRulePackLoader

_REFERENCE_YEAR = 2025


@pytest.fixture(scope="module")
def engine_results() -> list[EngineRunResult]:
    """Run the full golden-scenario engine once for all assertions in this module."""
    reader = FakeGraphReader()
    writer = CollectingGraphWriter()
    ai = AttributionStub()
    loader = JSONRulePackLoader()
    runner = EngineRunner(reader, writer, ai, loader, _REFERENCE_YEAR)
    return runner.run()


@pytest.fixture(scope="module")
def by_entity(engine_results: list[EngineRunResult]) -> dict[str, EngineRunResult]:
    """Index results by entity_id."""
    return {r.entity_id: r for r in engine_results}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _obligation(result: EngineRunResult, ob_type: ObligationType) -> list:
    return [o for o in result.obligations if o.obligation_type == ob_type]


def _wht_for_flow(result: EngineRunResult, flow_id: str):
    matches = [
        o for o in result.obligations
        if o.obligation_type == ObligationType.WHT and flow_id in o.source_flow_ids
    ]
    assert len(matches) == 1, f"Expected one WHT for {flow_id}, got {len(matches)}"
    return matches[0]


# ---------------------------------------------------------------------------
# MERID-HK — Profits Tax: HKD 445,500  (EXPECTED.md §3)
# ---------------------------------------------------------------------------

class TestMeridHK:
    def test_cit_amount(self, by_entity):
        hk = by_entity["MERID-HK"]
        cits = _obligation(hk, ObligationType.CIT)
        assert len(cits) == 1
        assert cits[0].net_amount_hkd == Decimal("445500")

    def test_cit_base(self, by_entity):
        hk = by_entity["MERID-HK"]
        cit = _obligation(hk, ObligationType.CIT)[0]
        # T001 royalty (2,400,000) + T007 management fee (300,000) = 2,700,000
        assert cit.taxable_base_hkd == Decimal("2700000")

    def test_cit_rate(self, by_entity):
        hk = by_entity["MERID-HK"]
        cit = _obligation(hk, ObligationType.CIT)[0]
        assert cit.rate == Decimal("0.165")

    def test_no_trade_tax(self, by_entity):
        hk = by_entity["MERID-HK"]
        assert _obligation(hk, ObligationType.TRADE_TAX) == []

    def test_no_wht(self, by_entity):
        hk = by_entity["MERID-HK"]
        assert _obligation(hk, ObligationType.WHT) == []

    def test_filing_deadline(self, by_entity):
        from datetime import date
        hk = by_entity["MERID-HK"]
        cit_deadlines = [d for d in hk.deadlines if d.obligation_type == ObligationType.CIT]
        assert len(cit_deadlines) == 1
        # HK profits tax return: 30 April 2026
        assert cit_deadlines[0].filing_deadline == date(2026, 4, 30)

    def test_needs_review_flagged(self, by_entity):
        """T001 royalty sourcing is LOW confidence — CIT obligation should be needs_review."""
        hk = by_entity["MERID-HK"]
        cit = _obligation(hk, ObligationType.CIT)[0]
        assert cit.needs_review is True


# ---------------------------------------------------------------------------
# MERID-DE — CIT, Trade Tax, WHT  (EXPECTED.md §4)
# ---------------------------------------------------------------------------

class TestMeridDE:
    def test_cit_amount(self, by_entity):
        de = by_entity["MERID-DE"]
        cits = _obligation(de, ObligationType.CIT)
        assert len(cits) == 1
        assert cits[0].net_amount_hkd == Decimal("47673")

    def test_cit_base(self, by_entity):
        de = by_entity["MERID-DE"]
        cit = _obligation(de, ObligationType.CIT)[0]
        # Post-PE, post-loss: 2,925,000 - 1,023,750 - 1,600,000 = 301,250
        assert cit.taxable_base_hkd == Decimal("301250")

    def test_cit_effective_rate(self, by_entity):
        de = by_entity["MERID-DE"]
        cit = _obligation(de, ObligationType.CIT)[0]
        # 15% × (1 + 5.5%) = 15.825%
        assert cit.rate == Decimal("0.15") * (Decimal("1") + Decimal("0.055"))

    def test_trade_tax_amount(self, by_entity):
        de = by_entity["MERID-DE"]
        tts = _obligation(de, ObligationType.TRADE_TAX)
        assert len(tts) == 1
        assert tts[0].net_amount_hkd == Decimal("42175")

    def test_trade_tax_base(self, by_entity):
        de = by_entity["MERID-DE"]
        tt = _obligation(de, ObligationType.TRADE_TAX)[0]
        assert tt.taxable_base_hkd == Decimal("301250")

    def test_loss_fully_consumed(self, by_entity):
        de = by_entity["MERID-DE"]
        # Full 1,600,000 prior loss consumed; none remaining
        for record in de.loss_carryforward_applied:
            assert record.remaining_loss_hkd == Decimal("0")
        total_used = sum(r.used_this_period_hkd for r in de.loss_carryforward_applied)
        assert total_used == Decimal("1600000")

    def test_wht_t005_dividend(self, by_entity):
        """T005 dividend to MERID-HK: 5% treaty rate → HKD 75,000."""
        de = by_entity["MERID-DE"]
        wht = _wht_for_flow(de, "T005")
        assert wht.net_amount_hkd == Decimal("75000")
        assert wht.rate == Decimal("0.05")
        assert wht.gross_amount_hkd == Decimal("375000")  # domestic 25%
        assert wht.treaty_citation is not None

    def test_wht_t006_interest(self, by_entity):
        """T006 interest to MERID-HK: 0% DTA rate → HKD 0."""
        de = by_entity["MERID-DE"]
        wht = _wht_for_flow(de, "T006")
        assert wht.net_amount_hkd == Decimal("0")
        assert wht.rate == Decimal("0")
        assert wht.gross_amount_hkd == Decimal("80000")  # domestic 25%
        assert wht.treaty_citation is not None

    def test_zinsschranke_not_breached(self, by_entity):
        """Interest barrier check: 320,000 < 973,500 cap → not breached."""
        de = by_entity["MERID-DE"]
        zins = [t for t in de.threshold_checks if t.threshold_name == "zinsschranke_interest_barrier"]
        assert len(zins) == 1
        assert zins[0].breached is False
        assert zins[0].actual_value_hkd == Decimal("320000")

    def test_pe_threshold_breached(self, by_entity):
        """PE days threshold: 185 > 183 → breached."""
        de = by_entity["MERID-DE"]
        pe = [t for t in de.threshold_checks if t.threshold_name == "service_pe_days"]
        assert len(pe) == 1
        assert pe[0].breached is True
        assert pe[0].actual_value_hkd == Decimal("185")

    def test_filing_deadline(self, by_entity):
        from datetime import date
        de = by_entity["MERID-DE"]
        cit_dl = [d for d in de.deadlines if d.obligation_type == ObligationType.CIT]
        assert len(cit_dl) == 1
        assert cit_dl[0].filing_deadline == date(2026, 7, 31)

    def test_pe_conflict_on_de(self, by_entity):
        """PE conflict flag is attached to MERID-DE (the residence entity)."""
        de = by_entity["MERID-DE"]
        assert len(de.conflicts) >= 1


# ---------------------------------------------------------------------------
# MERID-FR — CIT, VAT, WHT  (EXPECTED.md §5)
# ---------------------------------------------------------------------------

class TestMeridFR:
    def test_cit_amount(self, by_entity):
        fr = by_entity["MERID-FR"]
        cits = _obligation(fr, ObligationType.CIT)
        assert len(cits) == 1
        assert cits[0].net_amount_hkd == Decimal("1030938")

    def test_cit_base(self, by_entity):
        fr = by_entity["MERID-FR"]
        cit = _obligation(fr, ObligationType.CIT)[0]
        # 2,800,000 + 600,000 + 1,023,750 (PE) - 300,000 (mgmt fee) = 4,123,750
        assert cit.taxable_base_hkd == Decimal("4123750")

    def test_vat_obligation_triggered(self, by_entity):
        """FR revenue (EUR 329,412) > threshold (EUR 85,800) → VAT breached."""
        fr = by_entity["MERID-FR"]
        vat = [t for t in fr.threshold_checks if t.threshold_name == "vat_registration"]
        assert len(vat) == 1
        assert vat[0].breached is True

    def test_wht_t007_management_fee(self, by_entity):
        """T007 management fee to MERID-HK: 12.8% → HKD 38,400."""
        fr = by_entity["MERID-FR"]
        wht = _wht_for_flow(fr, "T007")
        assert wht.net_amount_hkd == Decimal("38400")
        assert wht.rate == Decimal("0.128")

    def test_wht_t004_dividend_zero(self, by_entity):
        """T004 dividend to MERID-DE: 0% EU PSD → HKD 0."""
        fr = by_entity["MERID-FR"]
        wht = _wht_for_flow(fr, "T004")
        assert wht.net_amount_hkd == Decimal("0")
        assert wht.treaty_citation is not None

    def test_no_trade_tax(self, by_entity):
        fr = by_entity["MERID-FR"]
        assert _obligation(fr, ObligationType.TRADE_TAX) == []

    def test_filing_deadline(self, by_entity):
        from datetime import date
        fr = by_entity["MERID-FR"]
        cit_dl = [d for d in fr.deadlines if d.obligation_type == ObligationType.CIT]
        assert len(cit_dl) == 1
        assert cit_dl[0].filing_deadline == date(2026, 5, 31)


# ---------------------------------------------------------------------------
# PE Triangle Conflict  (EXPECTED.md §6)
# ---------------------------------------------------------------------------

class TestPeTriangleConflict:

    @pytest.fixture(scope="class")
    def conflict(self, by_entity) -> ConflictFlag:
        de = by_entity["MERID-DE"]
        assert len(de.conflicts) == 1
        return de.conflicts[0]

    def test_conflict_id(self, conflict):
        assert conflict.conflict_id == "PE-TRIANGLE-2025"

    def test_attributed_base(self, conflict):
        assert conflict.attributed_base_hkd == Decimal("1023750")

    def test_pe_tax_in_france(self, conflict):
        # 1,023,750 × 25% = 255,937.50 → rounded 255,938
        assert conflict.pe_tax_hkd == Decimal("255938")

    def test_residence_tax_before_relief(self, conflict):
        # 1,023,750 × 15.825% = 162,008.xx → rounded 162,008
        assert conflict.residence_tax_before_relief_hkd == Decimal("162008")

    def test_exemption_mechanism(self, conflict):
        assert conflict.relief_mechanism == ReliefMechanism.EXEMPTION

    def test_relieved_amount(self, conflict):
        """Under exemption the relieved amount equals the residence-state tax."""
        assert conflict.relieved_amount_hkd == Decimal("162008")

    def test_no_residual_double_tax(self, conflict):
        assert conflict.residual_double_tax_hkd == Decimal("0")

    def test_treaty_rule(self, conflict):
        assert conflict.treaty_rule_id == "DEFR-DTA-ELIMINATION"

    def test_jurisdictions(self, conflict):
        assert set(conflict.jurisdictions) == {"DE", "FR"}

    def test_trigger_flow_id(self, conflict):
        assert "PRES-DE-FR-2025" in conflict.trigger_flow_ids

    def test_credit_note_present(self, conflict):
        assert conflict.credit_method_note is not None
        assert "162008" in conflict.credit_method_note


# ---------------------------------------------------------------------------
# Writer persistence assertions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# WHT Exposure Regression Guard  (W6.4 regression + W6.7 cross-check)
# ---------------------------------------------------------------------------

class TestWhtExposureRegressionGuard:
    def test_no_wht_over_withheld_flags_golden(self, engine_results):
        """Golden scenario: all WHT is treaty-compliant — zero over-withheld flags."""
        for result in engine_results:
            over_withheld = [
                c for c in result.conflicts
                if c.conflict_type == ConflictType.WHT_OVER_WITHHELD
            ]
            assert over_withheld == [], (
                f"Unexpected WHT_OVER_WITHHELD flag on {result.entity_id}: {over_withheld}"
            )

    def test_conflict_count_de(self, by_entity):
        """MERID-DE has exactly one conflict: the PE Triangle — no WHT exposure."""
        de = by_entity["MERID-DE"]
        assert len(de.conflicts) == 1
        assert de.conflicts[0].conflict_type == ConflictType.SERVICE_PE_DOUBLE_TAX

    def test_no_conflicts_hk_or_fr(self, by_entity):
        """MERID-HK and MERID-FR have no conflict flags in the golden scenario."""
        assert by_entity["MERID-HK"].conflicts == []
        assert by_entity["MERID-FR"].conflicts == []


class TestWriterPersistence:
    @pytest.fixture(scope="class")
    def writer(self, engine_results) -> CollectingGraphWriter:
        """Re-run to get the collecting writer (engine_results already ran; reuse)."""
        # engine_results fixture already populated a writer; we can't access it directly
        # so we run a lightweight second pass for writer verification.
        reader = FakeGraphReader()
        w = CollectingGraphWriter()
        runner = EngineRunner(reader, w, AttributionStub(), JSONRulePackLoader(), _REFERENCE_YEAR)
        runner.run()
        return w

    def test_obligations_written(self, writer):
        assert len(writer.obligations) > 0

    def test_loss_updates_written(self, writer):
        # MERID-DE has one loss record consumed
        de_updates = [u for u in writer.loss_updates if u[0] == "MERID-DE"]
        assert len(de_updates) >= 1

    def test_summaries_written(self, writer):
        assert len(writer.summaries) == 3  # HK, DE, FR
