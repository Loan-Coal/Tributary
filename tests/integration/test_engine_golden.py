"""
Module: test_engine_golden
Layer: test-integration
Purpose: End-to-end Lenovo-scenario engine integration test. Runs the full deterministic
    engine against the CSV-normalised fixtures (FakeGraphReader + AttributionStub +
    JSONRulePackLoader) and asserts structural correctness: obligations are produced,
    PE triggers, WHT is computed, conflicts are raised. Specific amount assertions are
    marked xfail pending recomputation for the Lenovo scenario (see ISSUES.md).
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
    """Run the full Lenovo-scenario engine once for all assertions in this module."""
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
# Structural: all three entities produce results
# ---------------------------------------------------------------------------

class TestEngineRunsCleanly:
    def test_three_entities_processed(self, engine_results):
        entity_ids = {r.entity_id for r in engine_results}
        assert "LENOVO-HK" in entity_ids
        assert "LENOVO-DE" in entity_ids
        assert "LENOVO-US" in entity_ids

    def test_every_entity_has_obligations(self, engine_results):
        for result in engine_results:
            assert len(result.obligations) > 0, f"{result.entity_id} has no obligations"


# ---------------------------------------------------------------------------
# LENOVO-HK — Profits Tax structural checks
# ---------------------------------------------------------------------------

class TestLenovoHK:
    def test_has_cit_obligation(self, by_entity):
        hk = by_entity["LENOVO-HK"]
        cits = _obligation(hk, ObligationType.CIT)
        assert len(cits) == 1

    def test_cit_rate(self, by_entity):
        hk = by_entity["LENOVO-HK"]
        cit = _obligation(hk, ObligationType.CIT)[0]
        assert cit.rate == Decimal("0.165")

    def test_no_trade_tax(self, by_entity):
        hk = by_entity["LENOVO-HK"]
        assert _obligation(hk, ObligationType.TRADE_TAX) == []

    def test_filing_deadline(self, by_entity):
        from datetime import date
        hk = by_entity["LENOVO-HK"]
        cit_deadlines = [d for d in hk.deadlines if d.obligation_type == ObligationType.CIT]
        assert len(cit_deadlines) == 1
        assert cit_deadlines[0].filing_deadline == date(2026, 4, 30)

    @pytest.mark.xfail(reason="Expected CIT amount needs recomputation for Lenovo data (see ISSUES.md)")
    def test_cit_amount(self, by_entity):
        hk = by_entity["LENOVO-HK"]
        cit = _obligation(hk, ObligationType.CIT)[0]
        assert cit.net_amount_hkd == Decimal("445500")

    @pytest.mark.xfail(reason="Expected taxable base needs recomputation for Lenovo data (see ISSUES.md)")
    def test_cit_base(self, by_entity):
        hk = by_entity["LENOVO-HK"]
        cit = _obligation(hk, ObligationType.CIT)[0]
        assert cit.taxable_base_hkd == Decimal("2700000")


# ---------------------------------------------------------------------------
# LENOVO-DE — CIT, Trade Tax, WHT structural checks
# ---------------------------------------------------------------------------

class TestLenovoDE:
    def test_has_cit_obligation(self, by_entity):
        de = by_entity["LENOVO-DE"]
        cits = _obligation(de, ObligationType.CIT)
        assert len(cits) == 1

    def test_cit_effective_rate(self, by_entity):
        de = by_entity["LENOVO-DE"]
        cit = _obligation(de, ObligationType.CIT)[0]
        assert cit.rate == Decimal("0.15") * (Decimal("1") + Decimal("0.055"))

    def test_has_trade_tax(self, by_entity):
        de = by_entity["LENOVO-DE"]
        tts = _obligation(de, ObligationType.TRADE_TAX)
        assert len(tts) == 1

    def test_pe_threshold_breached(self, by_entity):
        """PE days threshold: 185 > 183 → breached."""
        de = by_entity["LENOVO-DE"]
        pe = [t for t in de.threshold_checks if t.threshold_name == "service_pe_days"]
        assert len(pe) == 1
        assert pe[0].breached is True
        assert pe[0].actual_value_hkd == Decimal("185")

    def test_pe_conflict_on_de(self, by_entity):
        """PE conflict flag is attached to LENOVO-DE (the residence entity)."""
        de = by_entity["LENOVO-DE"]
        assert len(de.conflicts) >= 1

    def test_filing_deadline(self, by_entity):
        from datetime import date
        de = by_entity["LENOVO-DE"]
        cit_dl = [d for d in de.deadlines if d.obligation_type == ObligationType.CIT]
        assert len(cit_dl) == 1
        assert cit_dl[0].filing_deadline == date(2026, 7, 31)

    def test_wht_t002_dividend_exists(self, by_entity):
        """T002 dividend LENOVO-DE → LENOVO-HK: WHT obligation is produced."""
        de = by_entity["LENOVO-DE"]
        wht = _wht_for_flow(de, "T002")
        assert wht.rate == Decimal("0.05")

    def test_wht_t003_interest_zero(self, by_entity):
        """T003 interest LENOVO-DE → LENOVO-HK: 0% DTA rate."""
        de = by_entity["LENOVO-DE"]
        wht = _wht_for_flow(de, "T003")
        assert wht.net_amount_hkd == Decimal("0")
        assert wht.rate == Decimal("0")

    @pytest.mark.xfail(reason="Expected CIT amount needs recomputation for Lenovo data (see ISSUES.md)")
    def test_cit_amount(self, by_entity):
        de = by_entity["LENOVO-DE"]
        cit = _obligation(de, ObligationType.CIT)[0]
        assert cit.net_amount_hkd == Decimal("47673")

    @pytest.mark.xfail(reason="Expected loss consumed needs recomputation for Lenovo data (see ISSUES.md)")
    def test_loss_consumed(self, by_entity):
        de = by_entity["LENOVO-DE"]
        total_used = sum(r.used_this_period_hkd for r in de.loss_carryforward_applied)
        assert total_used == Decimal("1600000")


# ---------------------------------------------------------------------------
# LENOVO-US — Federal CIT and WHT structural checks
# ---------------------------------------------------------------------------

class TestLenovoUS:
    def test_has_cit_obligation(self, by_entity):
        us = by_entity["LENOVO-US"]
        cits = _obligation(us, ObligationType.CIT)
        assert len(cits) == 1

    def test_cit_rate(self, by_entity):
        us = by_entity["LENOVO-US"]
        cit = _obligation(us, ObligationType.CIT)[0]
        assert cit.rate == Decimal("0.21")

    def test_no_trade_tax(self, by_entity):
        us = by_entity["LENOVO-US"]
        assert _obligation(us, ObligationType.TRADE_TAX) == []

    def test_wht_t006_dividend_no_treaty(self, by_entity):
        """T006 dividend LENOVO-US → LENOVO-HK: 30% domestic rate, no HK-US DTA."""
        us = by_entity["LENOVO-US"]
        wht = _wht_for_flow(us, "T006")
        assert wht.rate == Decimal("0.30")
        assert wht.treaty_citation is None

    def test_filing_deadline(self, by_entity):
        from datetime import date
        us = by_entity["LENOVO-US"]
        cit_dl = [d for d in us.deadlines if d.obligation_type == ObligationType.CIT]
        assert len(cit_dl) == 1
        assert cit_dl[0].filing_deadline == date(2026, 4, 15)

    @pytest.mark.xfail(reason="Expected CIT amount needs recomputation for Lenovo data (see ISSUES.md)")
    def test_cit_amount(self, by_entity):
        us = by_entity["LENOVO-US"]
        cit = _obligation(us, ObligationType.CIT)[0]
        assert cit.net_amount_hkd == Decimal("816900")


# ---------------------------------------------------------------------------
# PE Conflict structural checks
# ---------------------------------------------------------------------------

class TestPeConflict:
    @pytest.fixture(scope="class")
    def de_conflict(self, by_entity) -> ConflictFlag:
        de = by_entity["LENOVO-DE"]
        pe_conflicts = [c for c in de.conflicts if c.conflict_type == ConflictType.SERVICE_PE_DOUBLE_TAX]
        assert len(pe_conflicts) >= 1
        return pe_conflicts[0]

    def test_conflict_id_format(self, de_conflict):
        assert de_conflict.conflict_id.startswith("PE-LENOVO-DE")

    def test_conflict_type(self, de_conflict):
        assert de_conflict.conflict_type == ConflictType.SERVICE_PE_DOUBLE_TAX

    def test_exemption_mechanism(self, de_conflict):
        assert de_conflict.relief_mechanism == ReliefMechanism.EXEMPTION

    def test_no_residual_double_tax(self, de_conflict):
        assert de_conflict.residual_double_tax_hkd == Decimal("0")

    @pytest.mark.xfail(reason="Expected attributed base needs recomputation for Lenovo data (see ISSUES.md)")
    def test_attributed_base(self, de_conflict):
        assert de_conflict.attributed_base_hkd == Decimal("1023750")


# ---------------------------------------------------------------------------
# WHT Exposure Regression Guard
# ---------------------------------------------------------------------------

class TestWhtExposureRegressionGuard:
    def test_no_wht_over_withheld_flags(self, engine_results):
        """All WHT is treaty-compliant — zero over-withheld flags."""
        for result in engine_results:
            over_withheld = [
                c for c in result.conflicts
                if c.conflict_type == ConflictType.WHT_OVER_WITHHELD
            ]
            assert over_withheld == [], (
                f"Unexpected WHT_OVER_WITHHELD flag on {result.entity_id}: {over_withheld}"
            )

    def test_conflict_count_de(self, by_entity):
        """LENOVO-DE has exactly one conflict: the PE — no WHT exposure."""
        de = by_entity["LENOVO-DE"]
        assert len(de.conflicts) == 1
        assert de.conflicts[0].conflict_type == ConflictType.SERVICE_PE_DOUBLE_TAX

    def test_no_conflicts_hk_or_us(self, by_entity):
        """LENOVO-HK and LENOVO-US have no conflict flags."""
        assert by_entity["LENOVO-HK"].conflicts == []
        assert by_entity["LENOVO-US"].conflicts == []


# ---------------------------------------------------------------------------
# Writer persistence
# ---------------------------------------------------------------------------

class TestWriterPersistence:
    @pytest.fixture(scope="class")
    def writer(self, engine_results) -> CollectingGraphWriter:
        reader = FakeGraphReader()
        w = CollectingGraphWriter()
        runner = EngineRunner(reader, w, AttributionStub(), JSONRulePackLoader(), _REFERENCE_YEAR)
        runner.run()
        return w

    def test_obligations_written(self, writer):
        assert len(writer.obligations) > 0

    def test_loss_updates_written(self, writer):
        de_updates = [u for u in writer.loss_updates if u[0] == "LENOVO-DE"]
        assert len(de_updates) >= 1

    def test_summaries_written(self, writer):
        assert len(writer.summaries) > 0
