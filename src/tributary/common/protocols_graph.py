"""
Module: protocols_graph
Layer: common
Purpose: Structural protocols (GraphReader, GraphWriter) the engine depends on for
    graph access. Defined in common/ because the engine may not import graph/
    implementations and the graph layer may not import engine/ — common is the only
    shared layer both can depend on (DEC-018).
Dependencies: typing, datetime, models_entity, models_engine
Used by: engine (depends on protocols), graph (implements them), tests (fakes)
"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from .models_engine import (
    EngineRunResult,
    LossCarryforwardRecord,
    ObligationResult,
)
from .models_entity import (
    ActivityType,
    CounterpartyRecord,
    EntityRecord,
    JurisdictionCode,
    OwnershipRecord,
    PresenceRecord,
    PriorPeriodLoss,
    TransactionRecord,
)


@runtime_checkable
class GraphReader(Protocol):
    """Read-only access to the graph for the deterministic engine.

    All methods are pure reads with no side effects. All monetary amounts returned
    are already FX-normalised to HKD at ingestion.
    """

    def get_entity(self, entity_id: str) -> EntityRecord:
        """Fetch one entity by ID.

        Args:
            entity_id: The entity to fetch.
        Returns:
            The matching entity record.
        Raises:
            EntityNotFoundError: If entity_id does not exist.
        """
        ...

    def get_all_entities(self) -> list[EntityRecord]:
        """Return all entities in the graph.

        Returns:
            Every entity record; used to enumerate engine runs.
        """
        ...

    def get_entity_ownership(self, entity_id: str) -> list[OwnershipRecord]:
        """Return all ownership edges where entity_id is the owner.

        Args:
            entity_id: The owning entity.
        Returns:
            Ownership edges (empty if no subsidiaries).
        """
        ...

    def get_related_party_ids(self, entity_id: str, max_hops: int = 5) -> list[str]:
        """Return entity_ids within max_hops ownership hops of entity_id.

        Args:
            entity_id: Starting entity.
            max_hops: Maximum ownership hops to traverse.
        Returns:
            Related entity_ids, excluding entity_id itself.
        """
        ...

    def get_transactions_for_entity(
        self,
        entity_id: str,
        period_start: date,
        period_end: date,
    ) -> list[TransactionRecord]:
        """Return transactions where source_entity_id == entity_id within the period.

        Args:
            entity_id: The source (payer / recipient-of-revenue) entity.
            period_start: First date of the period (inclusive).
            period_end: Last date of the period (inclusive).
        Returns:
            Matching transactions ordered by transaction_date ascending.
        """
        ...

    def get_transactions_involving_entity(
        self,
        entity_id: str,
        period_start: date,
        period_end: date,
    ) -> list[TransactionRecord]:
        """Return transactions where the entity is on EITHER side of the flow.

        Matches source_entity_id == entity_id OR counterparty_entity_id == entity_id.
        This is the method the engine uses to reconstruct an entity's full books:
        income flows where it is the payee and expense/distribution flows where it is
        the payer (DEC-016).

        Args:
            entity_id: The entity on either side of the flow.
            period_start: First date of the period (inclusive).
            period_end: Last date of the period (inclusive).
        Returns:
            Matching transactions ordered by transaction_date ascending.
        """
        ...

    def get_intercompany_transactions(
        self,
        entity_id: str,
        period_start: date,
        period_end: date,
    ) -> list[TransactionRecord]:
        """Return intercompany transactions involving entity_id within the period.

        Args:
            entity_id: The entity on either side of the flow.
            period_start: First date of the period (inclusive).
            period_end: Last date of the period (inclusive).
        Returns:
            Transactions with is_intercompany == True involving the entity.
        """
        ...

    def get_transactions_by_activity_type(
        self,
        entity_id: str,
        activity_type: ActivityType,
        period_start: date,
        period_end: date,
    ) -> list[TransactionRecord]:
        """Return transactions involving entity_id filtered by activity_type.

        Args:
            entity_id: The entity on either side of the flow.
            activity_type: The activity hint to filter on.
            period_start: First date of the period (inclusive).
            period_end: Last date of the period (inclusive).
        Returns:
            Matching transactions ordered by transaction_date ascending.
        """
        ...

    def get_presence_records(
        self,
        entity_id: str,
        jurisdiction: JurisdictionCode,
        period_start: date,
        period_end: date,
    ) -> list[PresenceRecord]:
        """Return presence records for entity_id in jurisdiction within the period.

        Args:
            entity_id: The entity whose employees/agents are present.
            jurisdiction: The jurisdiction of presence.
            period_start: First date of the period (inclusive).
            period_end: Last date of the period (inclusive).
        Returns:
            Matching presence records.
        """
        ...

    def get_prior_period_losses(
        self,
        entity_id: str,
        jurisdiction: JurisdictionCode,
    ) -> list[PriorPeriodLoss]:
        """Return unabsorbed prior-period losses (oldest first, FIFO offset order).

        Args:
            entity_id: The entity whose losses to fetch.
            jurisdiction: The jurisdiction where losses arose.
        Returns:
            Losses with remaining_loss_hkd > 0, oldest first.
        """
        ...

    def get_counterparty(self, counterparty_id: str) -> CounterpartyRecord:
        """Fetch counterparty details by ID.

        Args:
            counterparty_id: The counterparty to fetch.
        Returns:
            The matching counterparty record.
        Raises:
            CounterpartyNotFoundError: If counterparty_id does not exist.
        """
        ...


@runtime_checkable
class GraphWriter(Protocol):
    """Write-only interface for the engine to persist computation results.

    All writes must be idempotent — safe to re-run on the same id.
    """

    def write_obligation(self, entity_id: str, obligation: ObligationResult) -> None:
        """Persist one computed obligation, idempotent on obligation_id.

        Args:
            entity_id: The entity the obligation belongs to.
            obligation: The computed obligation result.
        Raises:
            GraphWriteError: On write failure.
        """
        ...

    def update_loss_carryforward(
        self,
        entity_id: str,
        loss_record: LossCarryforwardRecord,
    ) -> None:
        """Update remaining loss after the engine applied an offset.

        Args:
            entity_id: The entity whose loss position to update.
            loss_record: Which loss was used and how much remains.
        Raises:
            GraphWriteError: On write failure.
        """
        ...

    def write_engine_run_summary(self, summary: EngineRunResult) -> None:
        """Persist a summary node for one engine run, idempotent on run_id.

        Args:
            summary: The complete result for one entity + period.
        Raises:
            GraphWriteError: On write failure.
        """
        ...
