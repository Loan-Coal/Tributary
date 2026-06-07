"""
Module: test_golden_data
Layer: common / test-support
Purpose: Validate the golden fixtures against the canonical models WITHOUT Neo4j (closes the
    CI blind spot where the ingestion path was only exercised by Neo4j-gated tests), and prove
    the DEC-016 fix: each entity can reconstruct its full books via
    get_transactions_involving_entity. Pins the shape the real ingestion layer must produce.
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
FR_START, FR_END = date(2025, 1, 1), date(2025, 12, 31)


class TestGoldenLoads:
    """The golden fixtures validate against the models with no infrastructure."""

    def test_all_fixtures_validate(self) -> None:
        """Every golden JSON file parses into its model (would fail on schema drift)."""
        data = load_golden_models()
        assert len(data["entities"]) == 4  # HK, DE, FR, US (W7d)
        assert len(data["transactions"]) == 11  # T001–T009 + T010/T011 US (W7d)
        assert len(data["ownership"]) == 3  # HK→DE, DE→FR, HK→US (W7d)
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
    """DEC-016: each entity sees both sides of its intercompany flows."""

    def test_hk_sees_all_its_income_flows(self) -> None:
        """MERID-HK reconstructs T001+T007 income and counterparty flows T005/T006/T011."""
        reader = FakeGraphReader()
        ids = {t.transaction_id for t in reader.get_transactions_involving_entity("MERID-HK", HK_START, HK_END)}
        assert ids == {"T001", "T005", "T006", "T007", "T011"}

    def test_de_sees_income_and_expense_flows(self) -> None:
        """MERID-DE sees its revenue, dividend income, and royalty/interest expenses."""
        reader = FakeGraphReader()
        ids = {t.transaction_id for t in reader.get_transactions_involving_entity("MERID-DE", DE_START, DE_END)}
        assert ids == {"T001", "T002", "T003", "T004", "T005", "T006", "T008"}

    def test_fr_sees_income_and_expense_flows(self) -> None:
        """MERID-FR sees royalty income (T002), revenue (T009), and its outbound flows."""
        reader = FakeGraphReader()
        ids = {t.transaction_id for t in reader.get_transactions_involving_entity("MERID-FR", FR_START, FR_END)}
        assert ids == {"T002", "T004", "T007", "T009"}

    def test_source_only_fetch_is_narrower(self) -> None:
        """get_transactions_for_entity (source side only) misses counterparty-side flows."""
        reader = FakeGraphReader()
        source_only = {t.transaction_id for t in reader.get_transactions_for_entity("MERID-HK", HK_START, HK_END)}
        # As payer, HK is the source of nothing in the golden set — it is always the payee.
        assert "T001" not in source_only

    def test_t001_now_in_hk_fiscal_year(self) -> None:
        """Regression: T001 (2025-04-30) falls inside HK FY 2025 (Apr–Mar)."""
        reader = FakeGraphReader()
        ids = {t.transaction_id for t in reader.get_transactions_involving_entity("MERID-HK", HK_START, HK_END)}
        assert "T001" in ids


class TestPresenceAndLosses:
    """Presence and loss fixtures are queryable for the PE and loss engines."""

    def test_pe_presence_record(self) -> None:
        """The 185-day France presence record is returned for MERID-DE."""
        reader = FakeGraphReader()
        records = reader.get_presence_records("MERID-DE", "FR", DE_START, DE_END)
        assert len(records) == 1 and records[0].total_days_present == 185

    def test_prior_loss(self) -> None:
        """The DE FY2024 prior loss is available for carryforward."""
        reader = FakeGraphReader()
        losses = reader.get_prior_period_losses("MERID-DE", "DE")
        assert len(losses) == 1 and losses[0].remaining_loss_hkd == 1_600_000
