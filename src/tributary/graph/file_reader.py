"""
Module: file_reader
Layer: graph
Purpose: File-backed GraphReader for offline demo and unit tests. Loads golden scenario
    JSON files once at construction and serves all GraphReader methods from memory.
    No Neo4j required — used by `make demo` and fast integration tests.
Dependencies: json, pathlib, decimal, datetime, pydantic, tributary.common
Used by: engine.cli (demo command), tests
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from tributary.common.errors import (
    CounterpartyNotFoundError,
    EntityNotFoundError,
    IngestionError,
)
from tributary.common.logging import get_logger
from tributary.common.models_entity import (
    ActivityType,
    CounterpartyRecord,
    EntityRecord,
    JurisdictionCode,
    OwnershipRecord,
    PresenceRecord,
    PriorPeriodLoss,
    TransactionRecord,
)

logger = get_logger(__name__)

_M = TypeVar("_M", bound=BaseModel)
_DEFAULT_DATA_DIR = Path("data/golden")


def _load_json_as(path: Path, model_cls: type[_M]) -> list[_M]:
    """Load a JSON file and validate each item against model_cls.

    Args:
        path: Path to the JSON file.
        model_cls: Pydantic model to validate each item against.
    Returns:
        List of validated model instances.
    Raises:
        IngestionError: If the file is missing or any item fails validation.
    """
    if not path.exists():
        raise IngestionError(f"Data file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    instances: list[_M] = []
    for i, item in enumerate(raw):
        try:
            instances.append(model_cls.model_validate(item))
        except Exception as exc:
            raise IngestionError(
                f"Validation failed for {model_cls.__name__}[{i}]: {exc}"
            ) from exc
    return instances


class GoldenFileReader:
    """GraphReader backed by golden scenario JSON files in data/golden/.

    Loads all data once at construction; all reads are in-memory lookups.
    No Neo4j required — suitable for offline demo and fast unit tests.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        """Load all golden JSON files into memory.

        Args:
            data_dir: Directory containing the golden JSON files.
        Raises:
            IngestionError: If any required file is missing or fails validation.
        """
        self._entities = _load_json_as(data_dir / "entities.json", EntityRecord)
        self._transactions = _load_json_as(data_dir / "transactions.json", TransactionRecord)
        self._ownership = _load_json_as(data_dir / "ownership.json", OwnershipRecord)
        self._presence = _load_json_as(data_dir / "presence_records.json", PresenceRecord)
        self._losses = _load_json_as(data_dir / "prior_losses.json", PriorPeriodLoss)
        logger.info(
            "GoldenFileReader loaded",
            extra={"entities": len(self._entities), "transactions": len(self._transactions)},
        )

    def get_entity(self, entity_id: str) -> EntityRecord:
        """Fetch one entity by ID.

        Args:
            entity_id: The entity to fetch.
        Returns:
            The matching entity record.
        Raises:
            EntityNotFoundError: If entity_id does not exist.
        """
        for entity in self._entities:
            if entity.entity_id == entity_id:
                return entity
        raise EntityNotFoundError(f"Entity not found: {entity_id}")

    def get_all_entities(self) -> list[EntityRecord]:
        """Return all entities.

        Returns:
            Every entity record.
        """
        return list(self._entities)

    def get_entity_ownership(self, entity_id: str) -> list[OwnershipRecord]:
        """Return ownership edges where entity_id is the owner.

        Args:
            entity_id: The owning entity.
        Returns:
            Ownership edges (empty if no subsidiaries).
        """
        return [o for o in self._ownership if o.owner_entity_id == entity_id]

    def get_related_party_ids(self, entity_id: str, max_hops: int = 5) -> list[str]:
        """BFS over ownership records to find related entity_ids within max_hops.

        Args:
            entity_id: Starting entity.
            max_hops: Maximum ownership hops to traverse.
        Returns:
            Related entity_ids, excluding entity_id itself, sorted ascending.
        """
        visited: set[str] = set()
        frontier: set[str] = {entity_id}
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for eid in frontier:
                for o in self._ownership:
                    if o.owner_entity_id == eid and o.owned_entity_id not in visited:
                        next_frontier.add(o.owned_entity_id)
            visited.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
        visited.discard(entity_id)
        return sorted(visited)

    def get_transactions_for_entity(
        self, entity_id: str, period_start: date, period_end: date
    ) -> list[TransactionRecord]:
        """Return transactions where source_entity_id == entity_id within the period.

        Args:
            entity_id: The source entity.
            period_start: First date of the period (inclusive).
            period_end: Last date of the period (inclusive).
        Returns:
            Matching transactions ordered by date ascending.
        """
        return sorted(
            [
                t for t in self._transactions
                if t.source_entity_id == entity_id
                and period_start <= t.transaction_date <= period_end
            ],
            key=lambda t: t.transaction_date,
        )

    def get_transactions_involving_entity(
        self, entity_id: str, period_start: date, period_end: date
    ) -> list[TransactionRecord]:
        """Return transactions where the entity appears on either side of the flow.

        Args:
            entity_id: The entity on either side.
            period_start: First date of the period (inclusive).
            period_end: Last date of the period (inclusive).
        Returns:
            Matching transactions ordered by date ascending.
        """
        return sorted(
            [
                t for t in self._transactions
                if (t.source_entity_id == entity_id or t.counterparty_entity_id == entity_id)
                and period_start <= t.transaction_date <= period_end
            ],
            key=lambda t: t.transaction_date,
        )

    def get_intercompany_transactions(
        self, entity_id: str, period_start: date, period_end: date
    ) -> list[TransactionRecord]:
        """Return intercompany transactions involving entity_id within the period.

        Args:
            entity_id: The entity on either side.
            period_start: First date of the period (inclusive).
            period_end: Last date of the period (inclusive).
        Returns:
            Intercompany transactions ordered by date ascending.
        """
        return sorted(
            [
                t for t in self._transactions
                if t.is_intercompany
                and (t.source_entity_id == entity_id or t.counterparty_entity_id == entity_id)
                and period_start <= t.transaction_date <= period_end
            ],
            key=lambda t: t.transaction_date,
        )

    def get_transactions_by_activity_type(
        self,
        entity_id: str,
        activity_type: ActivityType,
        period_start: date,
        period_end: date,
    ) -> list[TransactionRecord]:
        """Return transactions involving entity_id filtered by activity_type.

        Args:
            entity_id: The entity on either side.
            activity_type: The activity type to filter on.
            period_start: First date of the period (inclusive).
            period_end: Last date of the period (inclusive).
        Returns:
            Matching transactions ordered by date ascending.
        """
        return sorted(
            [
                t for t in self._transactions
                if t.activity_type == activity_type
                and (t.source_entity_id == entity_id or t.counterparty_entity_id == entity_id)
                and period_start <= t.transaction_date <= period_end
            ],
            key=lambda t: t.transaction_date,
        )

    def get_presence_records(
        self,
        entity_id: str,
        jurisdiction: JurisdictionCode,
        period_start: date,
        period_end: date,
    ) -> list[PresenceRecord]:
        """Return presence records for entity_id in jurisdiction overlapping the period.

        Args:
            entity_id: The entity whose employees/agents are present.
            jurisdiction: The jurisdiction of presence.
            period_start: First date of the period (inclusive).
            period_end: Last date of the period (inclusive).
        Returns:
            Matching presence records.
        """
        return [
            p for p in self._presence
            if p.entity_id == entity_id
            and p.jurisdiction == jurisdiction
            and p.period_start <= period_end
            and p.period_end >= period_start
        ]

    def get_prior_period_losses(
        self, entity_id: str, jurisdiction: JurisdictionCode
    ) -> list[PriorPeriodLoss]:
        """Return unabsorbed prior-period losses for entity_id in jurisdiction, oldest first.

        Args:
            entity_id: The entity whose losses to fetch.
            jurisdiction: The jurisdiction where losses arose.
        Returns:
            Losses with remaining_loss_hkd > 0, oldest first.
        """
        return sorted(
            [
                loss for loss in self._losses
                if loss.entity_id == entity_id
                and loss.jurisdiction == jurisdiction
                and loss.remaining_loss_hkd > Decimal("0")
            ],
            key=lambda loss: loss.loss_period_start,
        )

    def get_counterparty(self, counterparty_id: str) -> CounterpartyRecord:
        """Fetch counterparty details by ID. Falls back to entity lookup for intercompany.

        Args:
            counterparty_id: The counterparty to fetch.
        Returns:
            The matching counterparty record.
        Raises:
            CounterpartyNotFoundError: If counterparty_id matches no known entity.
        """
        for entity in self._entities:
            if entity.entity_id == counterparty_id:
                return CounterpartyRecord(
                    counterparty_id=entity.entity_id,
                    name=entity.name,
                    jurisdiction=entity.resident_jurisdiction,
                    is_related_party=entity.is_group_member,
                )
        raise CounterpartyNotFoundError(f"Counterparty not found: {counterparty_id}")
