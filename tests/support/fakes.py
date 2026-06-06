"""
Module: fakes
Layer: test-support
Purpose: In-memory test doubles for the graph layer (FakeGraphReader / CollectingGraphWriter)
    backed by the golden JSON fixtures. They implement the GraphReader / GraphWriter protocols
    so the engine can be tested as if a real Neo4j-backed graph were present. The golden JSON
    also stands in for the ingestion layer's normalised output.
Dependencies: json, pathlib, tributary.common
Used by: engine unit + integration tests
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from tributary.common.errors import CounterpartyNotFoundError, EntityNotFoundError
from tributary.common.models import (
    ActivityType,
    CounterpartyRecord,
    EngineRunResult,
    EntityRecord,
    JurisdictionCode,
    LossCarryforwardRecord,
    ObligationResult,
    OwnershipRecord,
    PresenceRecord,
    PriorPeriodLoss,
    TransactionRecord,
)

_M = TypeVar("_M", bound=BaseModel)

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "data" / "golden"


def _load(path: Path, model_cls: type[_M]) -> list[_M]:
    """Load a JSON array file and validate each item as model_cls."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [model_cls.model_validate(item) for item in raw]


def load_golden_models(golden_dir: Path = GOLDEN_DIR) -> dict[str, list[Any]]:
    """Load and validate the golden fixtures into Pydantic models.

    Args:
        golden_dir: Directory containing the golden JSON files.
    Returns:
        Dict of model lists keyed by data type.
    """
    return {
        "entities": _load(golden_dir / "entities.json", EntityRecord),
        "ownership": _load(golden_dir / "ownership.json", OwnershipRecord),
        "transactions": _load(golden_dir / "transactions.json", TransactionRecord),
        "presence": _load(golden_dir / "presence_records.json", PresenceRecord),
        "losses": _load(golden_dir / "prior_losses.json", PriorPeriodLoss),
    }


class FakeGraphReader:
    """In-memory GraphReader backed by golden fixtures (implements the GraphReader protocol)."""

    def __init__(self, golden_dir: Path = GOLDEN_DIR) -> None:
        """Load the golden fixtures into memory.

        Args:
            golden_dir: Directory containing the golden JSON files.
        """
        data = load_golden_models(golden_dir)
        self._entities: list[EntityRecord] = data["entities"]
        self._ownership: list[OwnershipRecord] = data["ownership"]
        self._transactions: list[TransactionRecord] = data["transactions"]
        self._presence: list[PresenceRecord] = data["presence"]
        self._losses: list[PriorPeriodLoss] = data["losses"]

    def get_entity(self, entity_id: str) -> EntityRecord:
        for entity in self._entities:
            if entity.entity_id == entity_id:
                return entity
        raise EntityNotFoundError(f"Entity not found: {entity_id}")

    def get_all_entities(self) -> list[EntityRecord]:
        return list(self._entities)

    def get_entity_ownership(self, entity_id: str) -> list[OwnershipRecord]:
        return [o for o in self._ownership if o.owner_entity_id == entity_id]

    def get_related_party_ids(self, entity_id: str, max_hops: int = 5) -> list[str]:
        related: set[str] = set()
        frontier = {entity_id}
        for _ in range(max_hops):
            nxt: set[str] = set()
            for owner in frontier:
                for edge in self._ownership:
                    if edge.owner_entity_id == owner and edge.owned_entity_id not in related:
                        related.add(edge.owned_entity_id)
                        nxt.add(edge.owned_entity_id)
                    if edge.owned_entity_id == owner and edge.owner_entity_id not in related:
                        related.add(edge.owner_entity_id)
                        nxt.add(edge.owner_entity_id)
            if not nxt:
                break
            frontier = nxt
        related.discard(entity_id)
        return sorted(related)

    def _in_period(self, txn: TransactionRecord, start: date, end: date) -> bool:
        return start <= txn.transaction_date <= end

    def get_transactions_for_entity(
        self, entity_id: str, period_start: date, period_end: date
    ) -> list[TransactionRecord]:
        out = [
            t for t in self._transactions
            if t.source_entity_id == entity_id and self._in_period(t, period_start, period_end)
        ]
        return sorted(out, key=lambda t: t.transaction_date)

    def get_transactions_involving_entity(
        self, entity_id: str, period_start: date, period_end: date
    ) -> list[TransactionRecord]:
        out = [
            t for t in self._transactions
            if (t.source_entity_id == entity_id or t.counterparty_entity_id == entity_id)
            and self._in_period(t, period_start, period_end)
        ]
        return sorted(out, key=lambda t: t.transaction_date)

    def get_intercompany_transactions(
        self, entity_id: str, period_start: date, period_end: date
    ) -> list[TransactionRecord]:
        return [
            t for t in self.get_transactions_involving_entity(entity_id, period_start, period_end)
            if t.is_intercompany
        ]

    def get_transactions_by_activity_type(
        self,
        entity_id: str,
        activity_type: ActivityType,
        period_start: date,
        period_end: date,
    ) -> list[TransactionRecord]:
        return [
            t for t in self.get_transactions_involving_entity(entity_id, period_start, period_end)
            if t.activity_type == activity_type
        ]

    def get_presence_records(
        self,
        entity_id: str,
        jurisdiction: JurisdictionCode,
        period_start: date,
        period_end: date,
    ) -> list[PresenceRecord]:
        return [
            p for p in self._presence
            if p.entity_id == entity_id
            and p.jurisdiction == jurisdiction
            and p.period_start >= period_start
            and p.period_end <= period_end
        ]

    def get_prior_period_losses(
        self, entity_id: str, jurisdiction: JurisdictionCode
    ) -> list[PriorPeriodLoss]:
        out = [
            loss for loss in self._losses
            if loss.entity_id == entity_id
            and loss.jurisdiction == jurisdiction
            and loss.remaining_loss_hkd > 0
        ]
        return sorted(out, key=lambda loss: loss.loss_period_start)

    def get_counterparty(self, counterparty_id: str) -> CounterpartyRecord:
        raise CounterpartyNotFoundError(
            f"No counterparty fixture for {counterparty_id} (golden uses group entities)"
        )


class CollectingGraphWriter:
    """GraphWriter that records writes in memory for assertions (implements GraphWriter)."""

    def __init__(self) -> None:
        self.obligations: list[tuple[str, ObligationResult]] = []
        self.loss_updates: list[tuple[str, LossCarryforwardRecord]] = []
        self.summaries: list[EngineRunResult] = []

    def write_obligation(self, entity_id: str, obligation: ObligationResult) -> None:
        self.obligations.append((entity_id, obligation))

    def update_loss_carryforward(
        self, entity_id: str, loss_record: LossCarryforwardRecord
    ) -> None:
        self.loss_updates.append((entity_id, loss_record))

    def write_engine_run_summary(self, summary: EngineRunResult) -> None:
        self.summaries.append(summary)
