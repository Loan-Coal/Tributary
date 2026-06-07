"""
Module: test_golden_data
Layer: common / test-support
Purpose: Validate the normalised CSV fixtures against canonical models WITHOUT Neo4j, and
    prove that each entity can reconstruct its full books via get_transactions_involving_entity.
    Pins the shape the real ingestion layer must produce (Lenovo scenario: 3 entities, 7 txns).
Dependencies: pytest, datetime, tributary.common, tests.support
Used by: pytest test suite
"""
from __future__ import annotations

from datetime import date

from tributary.common import GraphReader
from tributary.common.models import ActivityType
from tests.support import FakeGraphReader, load_golden_models

HK_START, HK_END = date(2025, 4, 1), date(2026, 3, 31)
DE_START, DE_END = date(2025, 1, 1), date(2025, 12, 31)
US_START, US_END = date(2025, 1, 1), date(2025, 12, 31)


class TestGoldenLoads:
    """The normalised CSV fixtures validate against the models with no infrastructure."""

    def test_all_fixtures_validate(self) -> None:
        """CSV normaliser produces the expected counts for the Lenovo scenario."""
        data = load_golden_models()
        assert len(data["entities"]) == 3  # LENOVO-HK, LENOVO-DE, LENOVO-US
        assert len(data["transactions"]) == 7  # T001–T007
        assert len(data["ownership"]) == 2  # HK→DE, HK→US
        assert len(data["presence"]) == 1
        assert len(data["losses"]) == 1

    def test_transactions_have_source_amount_and_typed_activity(self) -> None:
        """Each transaction carries source_amount and a typed ActivityType (or None)."""
        data = load_golden_models()
        for txn in data["transactions"]:
            assert txn.source_amount is not None
            assert txn.activity_type is None or isinstance(txn.activity_type, ActivityType)


class TestProtocolConformance:
    """FakeGraphReader structurally satisfies the published GraphReader protocol."""

    def test_fake_is_graph_reader(self) -> None:
        """The fake conforms to GraphReader (runtime_checkable structural check)."""
        assert isinstance(FakeGraphReader(), GraphReader)


class TestBooksReconstruction:
    """Each entity sees both sides of its intercompany flows."""

    def test_hk_sees_all_its_income_flows(self) -> None:
        """LENOVO-HK reconstructs royalty, dividend, and interest income flows."""
        reader = FakeGraphReader()
        ids = {t.transaction_id for t in reader.get_transactions_involving_entity("LENOVO-HK", HK_START, HK_END)}
        # T001 royalty, T002 DE dividend, T003 interest, T006 US dividend
        assert "T001" in ids
        assert "T002" in ids
        assert "T003" in ids
        assert "T006" in ids

    def test_de_sees_income_and_expense_flows(self) -> None:
        """LENOVO-DE sees its revenue and outbound royalty/dividend/interest."""
        reader = FakeGraphReader()
        ids = {t.transaction_id for t in reader.get_transactions_involving_entity("LENOVO-DE", DE_START, DE_END)}
        # T001 royalty out, T002 dividend out, T003 interest out, T004 presence, T005 revenue
        assert {"T001", "T002", "T003", "T004", "T005"}.issubset(ids)

    def test_us_sees_its_flows(self) -> None:
        """LENOVO-US sees its revenue and outbound dividend."""
        reader = FakeGraphReader()
        ids = {t.transaction_id for t in reader.get_transactions_involving_entity("LENOVO-US", US_START, US_END)}
        assert "T006" in ids
        assert "T007" in ids

    def test_source_only_fetch_is_narrower(self) -> None:
        """get_transactions_for_entity (source side only) misses counterparty-side flows."""
        reader = FakeGraphReader()
        source_only = {t.transaction_id for t in reader.get_transactions_for_entity("LENOVO-HK", HK_START, HK_END)}
        # HK is always the payee in the Lenovo scenario — never the source payer.
        assert "T001" not in source_only


class TestPresenceAndLosses:
    """Presence and loss fixtures are queryable for the PE and loss engines."""

    def test_pe_presence_record(self) -> None:
        """The 185-day US presence record is returned for LENOVO-DE."""
        reader = FakeGraphReader()
        records = reader.get_presence_records("LENOVO-DE", "US", DE_START, DE_END)
        assert len(records) == 1 and records[0].total_days_present == 185

    def test_prior_loss(self) -> None:
        """The DE FY2024 prior loss is available for carryforward."""
        reader = FakeGraphReader()
        losses = reader.get_prior_period_losses("LENOVO-DE", "DE")
        assert len(losses) == 1 and losses[0].remaining_loss_hkd > 0
