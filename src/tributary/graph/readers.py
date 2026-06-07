"""
Module: readers
Layer: graph
Purpose: Neo4j-backed GraphReader implementation. Reconstructs canonical Pydantic models
    from Neo4j node properties. Monetary values are stored as floats in Neo4j (ISSUE-007)
    and converted back to Decimal on read. Dates are stored as ISO strings.
Dependencies: neo4j, decimal, datetime, tributary.common, tributary.config
Used by: engine.cli (run-golden command), integration tests
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any, Generator

from tributary.common.errors import (
    CounterpartyNotFoundError,
    EntityNotFoundError,
    GraphError,
    IngestionError,
)
from tributary.common.logging import get_logger
from tributary.common.models_entity import (
    ActivityType,
    CounterpartyRecord,
    EntityRecord,
    EntityType,
    JurisdictionCode,
    OwnershipRecord,
    PresenceActivity,
    PresenceRecord,
    PriorPeriodLoss,
    TransactionRecord,
)

logger = get_logger(__name__)


def _to_date(value: str | None) -> date:
    """Convert an ISO string to a date.

    Args:
        value: ISO-format date string (YYYY-MM-DD).
    Returns:
        Parsed date.
    Raises:
        IngestionError: If value is None or cannot be parsed.
    """
    if value is None:
        raise IngestionError("Expected date string, got None")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise IngestionError(f"Invalid date string: {value!r}") from exc


def _to_optional_date(value: str | None) -> date | None:
    """Convert an ISO string to a date or None.

    Args:
        value: ISO-format date string or None.
    Returns:
        Parsed date or None.
    """
    return date.fromisoformat(value) if value is not None else None


def _to_decimal(value: float | None) -> Decimal:
    """Convert a float Neo4j property to Decimal.

    Args:
        value: Float value from Neo4j.
    Returns:
        Decimal representation.
    Raises:
        IngestionError: If value is None.
    """
    if value is None:
        raise IngestionError("Expected numeric value, got None")
    return Decimal(str(value))


def _row_to_entity(props: dict[str, Any]) -> EntityRecord:
    """Reconstruct an EntityRecord from Neo4j node properties.

    Args:
        props: Property dict from a Neo4j Entity node.
    Returns:
        Validated EntityRecord.
    Raises:
        IngestionError: On malformed properties.
    """
    try:
        return EntityRecord(
            entity_id=props["entity_id"],
            name=props["name"],
            entity_type=EntityType(props["entity_type"]),
            incorporation_jurisdiction=props["incorporation_jurisdiction"],
            resident_jurisdiction=props["resident_jurisdiction"],
            is_group_member=props["is_group_member"],
        )
    except (KeyError, ValueError) as exc:
        raise IngestionError(f"Malformed Entity node: {exc}") from exc


def _row_to_transaction(props: dict[str, Any]) -> TransactionRecord:
    """Reconstruct a TransactionRecord from Neo4j node properties.

    Args:
        props: Property dict from a Neo4j Transaction node.
    Returns:
        Validated TransactionRecord.
    Raises:
        IngestionError: On malformed properties.
    """
    try:
        activity_raw = props.get("activity_type")
        return TransactionRecord(
            transaction_id=props["transaction_id"],
            transaction_date=_to_date(props["transaction_date"]),
            description=props["description"],
            amount_hkd=_to_decimal(props["amount_hkd"]),
            source_amount=_to_decimal(props["source_amount"]),
            fx_rate=_to_decimal(props["fx_rate"]),
            fx_date=_to_date(props["fx_date"]),
            source_currency=props["source_currency"],
            source_entity_id=props["source_entity_id"],
            counterparty_entity_id=props.get("counterparty_entity_id"),
            counterparty_jurisdiction=props.get("counterparty_jurisdiction"),
            is_intercompany=props["is_intercompany"],
            activity_type=ActivityType(activity_raw) if activity_raw else None,
            days_present=props.get("days_present"),
            has_agent_authority=props["has_agent_authority"],
        )
    except (KeyError, ValueError) as exc:
        raise IngestionError(f"Malformed Transaction node: {exc}") from exc


def _row_to_presence(props: dict[str, Any]) -> PresenceRecord:
    """Reconstruct a PresenceRecord from Neo4j node properties.

    Args:
        props: Property dict from a Neo4j PresenceRecord node.
    Returns:
        Validated PresenceRecord.
    Raises:
        IngestionError: On malformed properties.
    """
    try:
        return PresenceRecord(
            presence_id=props["presence_id"],
            entity_id=props["entity_id"],
            jurisdiction=props["jurisdiction"],
            period_start=_to_date(props["period_start"]),
            period_end=_to_date(props["period_end"]),
            total_days_present=int(props["total_days_present"]),
            activity_type=PresenceActivity(props["activity_type"]),
            has_agent_authority=props["has_agent_authority"],
            has_fixed_place=props["has_fixed_place"],
        )
    except (KeyError, ValueError) as exc:
        raise IngestionError(f"Malformed PresenceRecord node: {exc}") from exc


def _row_to_loss(props: dict[str, Any]) -> PriorPeriodLoss:
    """Reconstruct a PriorPeriodLoss from Neo4j node properties.

    Args:
        props: Property dict from a Neo4j PriorPeriodLoss node.
    Returns:
        Validated PriorPeriodLoss.
    Raises:
        IngestionError: On malformed properties.
    """
    try:
        return PriorPeriodLoss(
            loss_id=props["loss_id"],
            entity_id=props["entity_id"],
            jurisdiction=props["jurisdiction"],
            loss_period_start=_to_date(props["loss_period_start"]),
            loss_period_end=_to_date(props["loss_period_end"]),
            original_loss_hkd=_to_decimal(props["original_loss_hkd"]),
            remaining_loss_hkd=_to_decimal(props["remaining_loss_hkd"]),
            created_at=_to_date(props["created_at"]),
        )
    except (KeyError, ValueError) as exc:
        raise IngestionError(f"Malformed PriorPeriodLoss node: {exc}") from exc


class Neo4jGraphReader:
    """Neo4j-backed GraphReader. Reconstructs canonical Pydantic models from graph nodes.

    All Cypher queries are parameterized (no f-string interpolation per security rules).
    Monetary amounts are stored as floats in Neo4j; converted to Decimal on read (ISSUE-007).
    """

    def __init__(self, driver: Any) -> None:
        """Wire the Neo4j driver.

        Args:
            driver: Active neo4j.GraphDatabase.Driver instance.
        """
        self._driver = driver

    @contextmanager
    def _session(self) -> Generator[Any, None, None]:
        """Open a Neo4j session as a context manager."""
        with self._driver.session() as session:
            yield session

    def get_entity(self, entity_id: str) -> EntityRecord:
        """Fetch one entity by ID.

        Args:
            entity_id: The entity to fetch.
        Returns:
            The matching entity record.
        Raises:
            EntityNotFoundError: If entity_id does not exist.
        """
        with self._session() as session:
            result = session.run(
                "MATCH (e:Entity {entity_id: $entity_id}) RETURN e",
                entity_id=entity_id,
            )
            record = result.single()
        if record is None:
            raise EntityNotFoundError(f"Entity not found: {entity_id}")
        return _row_to_entity(dict(record["e"]))

    def get_all_entities(self) -> list[EntityRecord]:
        """Return all entities in the graph.

        Returns:
            Every entity record, ordered by entity_id.
        """
        with self._session() as session:
            result = session.run("MATCH (e:Entity) RETURN e ORDER BY e.entity_id")
            return [_row_to_entity(dict(record["e"])) for record in result]

    def get_entity_ownership(self, entity_id: str) -> list[OwnershipRecord]:
        """Return ownership edges where entity_id is the owner.

        Args:
            entity_id: The owning entity.
        Returns:
            Ownership edges.
        """
        with self._session() as session:
            result = session.run(
                """
                MATCH (owner:Entity {entity_id: $entity_id})-[r:OWNS]->(owned:Entity)
                RETURN r.owner_entity_id AS owner_entity_id,
                       r.owned_entity_id AS owned_entity_id,
                       r.ownership_pct AS ownership_pct,
                       r.effective_from AS effective_from,
                       r.effective_to AS effective_to
                """,
                entity_id=entity_id,
            )
            return [
                OwnershipRecord(
                    owner_entity_id=rec["owner_entity_id"],
                    owned_entity_id=rec["owned_entity_id"],
                    ownership_pct=Decimal(str(rec["ownership_pct"])),
                    effective_from=_to_date(rec["effective_from"]),
                    effective_to=_to_optional_date(rec["effective_to"]),
                )
                for rec in result
            ]

    def get_related_party_ids(self, entity_id: str, max_hops: int = 5) -> list[str]:
        """Return entity_ids within max_hops ownership hops of entity_id.

        Args:
            entity_id: Starting entity.
            max_hops: Maximum ownership hops (used as Cypher path length upper bound).
        Returns:
            Related entity_ids, excluding entity_id itself.
        """
        with self._session() as session:
            result = session.run(
                """
                MATCH (root:Entity {entity_id: $entity_id})-[:OWNS*1..5]->(rel:Entity)
                RETURN DISTINCT rel.entity_id AS entity_id
                ORDER BY rel.entity_id
                """,
                entity_id=entity_id,
            )
            return [rec["entity_id"] for rec in result]

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
        with self._session() as session:
            result = session.run(
                """
                MATCH (t:Transaction {source_entity_id: $entity_id})
                WHERE t.transaction_date >= $period_start AND t.transaction_date <= $period_end
                RETURN t ORDER BY t.transaction_date ASC
                """,
                entity_id=entity_id,
                period_start=period_start.isoformat(),
                period_end=period_end.isoformat(),
            )
            return [_row_to_transaction(dict(rec["t"])) for rec in result]

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
        with self._session() as session:
            result = session.run(
                """
                MATCH (t:Transaction)
                WHERE (t.source_entity_id = $entity_id OR t.counterparty_entity_id = $entity_id)
                  AND t.transaction_date >= $period_start
                  AND t.transaction_date <= $period_end
                RETURN t ORDER BY t.transaction_date ASC
                """,
                entity_id=entity_id,
                period_start=period_start.isoformat(),
                period_end=period_end.isoformat(),
            )
            return [_row_to_transaction(dict(rec["t"])) for rec in result]

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
        with self._session() as session:
            result = session.run(
                """
                MATCH (t:Transaction)
                WHERE t.is_intercompany = true
                  AND (t.source_entity_id = $entity_id OR t.counterparty_entity_id = $entity_id)
                  AND t.transaction_date >= $period_start
                  AND t.transaction_date <= $period_end
                RETURN t ORDER BY t.transaction_date ASC
                """,
                entity_id=entity_id,
                period_start=period_start.isoformat(),
                period_end=period_end.isoformat(),
            )
            return [_row_to_transaction(dict(rec["t"])) for rec in result]

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
        with self._session() as session:
            result = session.run(
                """
                MATCH (t:Transaction)
                WHERE t.activity_type = $activity_type
                  AND (t.source_entity_id = $entity_id OR t.counterparty_entity_id = $entity_id)
                  AND t.transaction_date >= $period_start
                  AND t.transaction_date <= $period_end
                RETURN t ORDER BY t.transaction_date ASC
                """,
                entity_id=entity_id,
                activity_type=activity_type.value,
                period_start=period_start.isoformat(),
                period_end=period_end.isoformat(),
            )
            return [_row_to_transaction(dict(rec["t"])) for rec in result]

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
        with self._session() as session:
            result = session.run(
                """
                MATCH (p:PresenceRecord {entity_id: $entity_id, jurisdiction: $jurisdiction})
                WHERE p.period_start <= $period_end AND p.period_end >= $period_start
                RETURN p
                """,
                entity_id=entity_id,
                jurisdiction=jurisdiction,
                period_start=period_start.isoformat(),
                period_end=period_end.isoformat(),
            )
            return [_row_to_presence(dict(rec["p"])) for rec in result]

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
        with self._session() as session:
            result = session.run(
                """
                MATCH (l:PriorPeriodLoss {entity_id: $entity_id, jurisdiction: $jurisdiction})
                WHERE l.remaining_loss_hkd > 0
                RETURN l ORDER BY l.loss_period_start ASC
                """,
                entity_id=entity_id,
                jurisdiction=jurisdiction,
            )
            return [_row_to_loss(dict(rec["l"])) for rec in result]

    def get_counterparty(self, counterparty_id: str) -> CounterpartyRecord:
        """Fetch counterparty details. Falls back to Entity lookup for intercompany parties.

        Args:
            counterparty_id: The counterparty to fetch.
        Returns:
            The matching counterparty record.
        Raises:
            CounterpartyNotFoundError: If counterparty_id matches no entity.
        """
        with self._session() as session:
            result = session.run(
                "MATCH (e:Entity {entity_id: $entity_id}) RETURN e",
                entity_id=counterparty_id,
            )
            record = result.single()
        if record is None:
            raise CounterpartyNotFoundError(f"Counterparty not found: {counterparty_id}")
        entity = _row_to_entity(dict(record["e"]))
        return CounterpartyRecord(
            counterparty_id=entity.entity_id,
            name=entity.name,
            jurisdiction=entity.resident_jurisdiction,
            is_related_party=entity.is_group_member,
        )
