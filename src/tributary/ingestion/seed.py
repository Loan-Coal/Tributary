"""
Module: seed
Layer: ingestion
Purpose: Load golden scenario JSON files into Neo4j for development and integration testing.
Dependencies: neo4j, json, pathlib, tributary.common, tributary.config
Used by: tributary.ingestion.cli (via make ingest), integration tests

File length note (see DEC-014): This module is 389 total lines but only ~257 non-blank,
non-docstring code lines. A split into seed_writers.py + seed.py would be artificial —
all functions form a single cohesive seeding pipeline. The overcount is due to docstrings
and Cypher query strings embedded as multi-line string literals.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from tributary.common import (
    AccountRecord,
    EntityRecord,
    OwnershipRecord,
    PresenceRecord,
    PriorPeriodLoss,
    TransactionRecord,
)
from tributary.common.errors import IngestionError
from tributary.common.logging import get_logger
from tributary.config.settings import DATA_DIR, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER

logger = get_logger(__name__)

M = TypeVar("M", bound=BaseModel)

# ---------------------------------------------------------------------------
# JSON loading and validation
# ---------------------------------------------------------------------------


def _load_json_as(path: Path, model_cls: type[M]) -> list[M]:
    """Load a JSON file and validate each item as model_cls.

    Args:
        path: Absolute path to the JSON file.
        model_cls: Pydantic model class to validate each item against.
    Returns:
        List of validated model instances.
    Raises:
        IngestionError: If the file is missing or any record fails validation.
    """
    if not path.exists():
        raise IngestionError(f"Golden data file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IngestionError(f"Invalid JSON in {path}: {exc}") from exc
    results: list[M] = []
    for i, item in enumerate(raw):
        try:
            results.append(model_cls.model_validate(item))
        except Exception as exc:
            raise IngestionError(f"Validation failed for {model_cls.__name__}[{i}]: {exc}") from exc
    return results


def load_golden_data(data_dir: Path) -> dict[str, list[Any]]:
    """Load and validate all golden JSON files.

    Fails fast on missing files or validation errors.

    Args:
        data_dir: Root data directory (e.g. Path("data")).
    Returns:
        Dict mapping data-type names to lists of validated model instances.
    Raises:
        IngestionError: On missing file, invalid JSON, or schema mismatch.
    """
    golden = data_dir / "golden"
    return {
        "entities": _load_json_as(golden / "entities.json", EntityRecord),
        "accounts": _load_json_as(golden / "accounts.json", AccountRecord),
        "ownership": _load_json_as(golden / "ownership.json", OwnershipRecord),
        "transactions": _load_json_as(golden / "transactions.json", TransactionRecord),
        "presence_records": _load_json_as(golden / "presence_records.json", PresenceRecord),
        "prior_losses": _load_json_as(golden / "prior_losses.json", PriorPeriodLoss),
    }


# ---------------------------------------------------------------------------
# Type conversion helpers
# ---------------------------------------------------------------------------


def _decimal_to_float(value: Decimal | None) -> float | None:
    """Convert Decimal to float for Neo4j storage.

    See ISSUE-007: Wave 2 graph layer should handle Decimal precision properly.

    Args:
        value: Decimal value or None.
    Returns:
        Float representation or None.
    """
    return float(value) if value is not None else None


def _date_to_str(value: Any) -> str | None:
    """Convert a date to an ISO string for Neo4j storage.

    Args:
        value: date object or None.
    Returns:
        ISO-format string (YYYY-MM-DD) or None.
    """
    return value.isoformat() if value is not None else None


# ---------------------------------------------------------------------------
# Entity seeding
# ---------------------------------------------------------------------------


def seed_entities(session: Any, entities: list[EntityRecord]) -> None:
    """MERGE Entity nodes into Neo4j.

    Args:
        session: Active Neo4j driver session.
        entities: Validated entity records to seed.
    """
    for record in entities:
        session.run(
            """
            MERGE (e:Entity {entity_id: $entity_id})
            SET e.name = $name,
                e.entity_type = $entity_type,
                e.incorporation_jurisdiction = $incorporation_jurisdiction,
                e.resident_jurisdiction = $resident_jurisdiction,
                e.is_group_member = $is_group_member
            """,
            entity_id=record.entity_id,
            name=record.name,
            entity_type=record.entity_type.value,
            incorporation_jurisdiction=record.incorporation_jurisdiction,
            resident_jurisdiction=record.resident_jurisdiction,
            is_group_member=record.is_group_member,
        )
    logger.info("Seeded entities", extra={"count": len(entities)})


# ---------------------------------------------------------------------------
# Account seeding
# ---------------------------------------------------------------------------


def seed_accounts(session: Any, accounts: list[AccountRecord]) -> None:
    """MERGE Account nodes and HOLDS relationships.

    Args:
        session: Active Neo4j driver session.
        accounts: Validated account records to seed.
    """
    for record in accounts:
        session.run(
            """
            MERGE (a:Account {account_id: $account_id})
            SET a.entity_id = $entity_id,
                a.account_name = $account_name,
                a.account_type = $account_type
            WITH a
            MATCH (e:Entity {entity_id: $entity_id})
            MERGE (e)-[:HOLDS]->(a)
            """,
            account_id=record.account_id,
            entity_id=record.entity_id,
            account_name=record.account_name,
            account_type=record.account_type,
        )
    logger.info("Seeded accounts", extra={"count": len(accounts)})


# ---------------------------------------------------------------------------
# Ownership seeding
# ---------------------------------------------------------------------------


def seed_ownership(session: Any, ownership: list[OwnershipRecord]) -> None:
    """MERGE OWNS relationships between Entity nodes.

    Args:
        session: Active Neo4j driver session.
        ownership: Validated ownership records to seed.
    """
    for record in ownership:
        session.run(
            """
            MATCH (owner:Entity {entity_id: $owner_id})
            MATCH (owned:Entity {entity_id: $owned_id})
            MERGE (owner)-[r:OWNS {owner_entity_id: $owner_id, owned_entity_id: $owned_id}]->(owned)
            SET r.ownership_pct = $pct,
                r.effective_from = $eff_from,
                r.effective_to = $eff_to
            """,
            owner_id=record.owner_entity_id,
            owned_id=record.owned_entity_id,
            pct=_decimal_to_float(record.ownership_pct),
            eff_from=_date_to_str(record.effective_from),
            eff_to=_date_to_str(record.effective_to),
        )
    logger.info("Seeded ownership relationships", extra={"count": len(ownership)})


# ---------------------------------------------------------------------------
# Transaction seeding
# ---------------------------------------------------------------------------


def _build_transaction_props(record: TransactionRecord) -> dict[str, Any]:
    """Build a property dict for a Transaction node.

    All Decimal values are converted to float (see ISSUE-007).
    All date values are stored as ISO strings.

    Args:
        record: Validated transaction record.
    Returns:
        Dict of Neo4j-compatible property values.
    """
    return {
        "transaction_id": record.transaction_id,
        "transaction_date": _date_to_str(record.transaction_date),
        "description": record.description,
        "amount_hkd": _decimal_to_float(record.amount_hkd),
        "source_amount": _decimal_to_float(record.source_amount),
        "fx_rate": _decimal_to_float(record.fx_rate),
        "fx_date": _date_to_str(record.fx_date),
        "source_currency": record.source_currency,
        "source_entity_id": record.source_entity_id,
        "counterparty_entity_id": record.counterparty_entity_id,
        "counterparty_jurisdiction": record.counterparty_jurisdiction,
        "is_intercompany": record.is_intercompany,
        "activity_type": record.activity_type.value if record.activity_type is not None else None,
        "days_present": record.days_present,
        "has_agent_authority": record.has_agent_authority,
    }


def seed_transactions(session: Any, transactions: list[TransactionRecord]) -> None:
    """MERGE Transaction nodes and RECORDS relationships.

    The RECORDS relationship is created from the source entity's Account node.

    Args:
        session: Active Neo4j driver session.
        transactions: Validated transaction records to seed.
    """
    for record in transactions:
        props = _build_transaction_props(record)
        session.run(
            """
            MERGE (t:Transaction {transaction_id: $transaction_id})
            SET t += $props
            WITH t
            MATCH (a:Account {entity_id: $source_entity_id})
            MERGE (a)-[:RECORDS]->(t)
            """,
            transaction_id=record.transaction_id,
            props=props,
            source_entity_id=record.source_entity_id,
        )
    logger.info("Seeded transactions", extra={"count": len(transactions)})


# ---------------------------------------------------------------------------
# Presence record seeding
# ---------------------------------------------------------------------------


def seed_presence_records(session: Any, records: list[PresenceRecord]) -> None:
    """MERGE PresenceRecord nodes and HAS_PRESENCE relationships.

    Args:
        session: Active Neo4j driver session.
        records: Validated presence records to seed.
    """
    for record in records:
        session.run(
            """
            MERGE (p:PresenceRecord {presence_id: $presence_id})
            SET p.entity_id = $entity_id,
                p.jurisdiction = $jurisdiction,
                p.period_start = $period_start,
                p.period_end = $period_end,
                p.total_days_present = $total_days_present,
                p.activity_type = $activity_type,
                p.has_agent_authority = $has_agent_authority,
                p.has_fixed_place = $has_fixed_place
            WITH p
            MATCH (e:Entity {entity_id: $entity_id})
            MERGE (e)-[:HAS_PRESENCE]->(p)
            """,
            presence_id=record.presence_id,
            entity_id=record.entity_id,
            jurisdiction=record.jurisdiction,
            period_start=_date_to_str(record.period_start),
            period_end=_date_to_str(record.period_end),
            total_days_present=record.total_days_present,
            activity_type=record.activity_type.value,
            has_agent_authority=record.has_agent_authority,
            has_fixed_place=record.has_fixed_place,
        )
    logger.info("Seeded presence records", extra={"count": len(records)})


# ---------------------------------------------------------------------------
# Prior loss seeding
# ---------------------------------------------------------------------------


def seed_prior_losses(session: Any, losses: list[PriorPeriodLoss]) -> None:
    """MERGE PriorPeriodLoss nodes and HAS_PRIOR_LOSS relationships.

    Args:
        session: Active Neo4j driver session.
        losses: Validated prior period loss records to seed.
    """
    for record in losses:
        session.run(
            """
            MERGE (l:PriorPeriodLoss {loss_id: $loss_id})
            SET l.entity_id = $entity_id,
                l.jurisdiction = $jurisdiction,
                l.loss_period_start = $loss_period_start,
                l.loss_period_end = $loss_period_end,
                l.original_loss_hkd = $original_loss_hkd,
                l.remaining_loss_hkd = $remaining_loss_hkd,
                l.created_at = $created_at
            WITH l
            MATCH (e:Entity {entity_id: $entity_id})
            MERGE (e)-[:HAS_PRIOR_LOSS]->(l)
            """,
            loss_id=record.loss_id,
            entity_id=record.entity_id,
            jurisdiction=record.jurisdiction,
            loss_period_start=_date_to_str(record.loss_period_start),
            loss_period_end=_date_to_str(record.loss_period_end),
            original_loss_hkd=_decimal_to_float(record.original_loss_hkd),
            remaining_loss_hkd=_decimal_to_float(record.remaining_loss_hkd),
            created_at=_date_to_str(record.created_at),
        )
    logger.info("Seeded prior losses", extra={"count": len(losses)})


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_seed(data_dir: Path | None = None) -> None:
    """Orchestrate the full golden data seed. Entry point for CLI.

    Loads all golden JSON files, validates them, then writes to Neo4j
    using MERGE (idempotent — safe to re-run).

    Args:
        data_dir: Root data directory. Defaults to the DATA_DIR config value.
    Raises:
        IngestionError: If Neo4j is unreachable or data validation fails.
    """
    from neo4j import GraphDatabase  # noqa: PLC0415

    resolved_dir = Path(data_dir) if data_dir is not None else Path(DATA_DIR)
    logger.info("Loading golden data", extra={"data_dir": str(resolved_dir)})
    golden = load_golden_data(resolved_dir)

    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
    except Exception as exc:
        logger.error("Neo4j unreachable", extra={"error": str(exc)})
        raise IngestionError("Start Neo4j with 'docker-compose up -d' before seeding") from exc

    logger.info("Neo4j connected — seeding golden scenario")
    with driver.session() as session:
        seed_entities(session, golden["entities"])
        seed_accounts(session, golden["accounts"])
        seed_ownership(session, golden["ownership"])
        seed_transactions(session, golden["transactions"])
        seed_presence_records(session, golden["presence_records"])
        seed_prior_losses(session, golden["prior_losses"])

    driver.close()
    logger.info("Golden seed complete")
