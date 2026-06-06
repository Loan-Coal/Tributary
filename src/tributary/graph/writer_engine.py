"""
Module: writer_engine
Layer: graph
Purpose: Neo4j-backed GraphWriter for persisting engine computation results. Writes
    ObligationResult, LossCarryforwardRecord, and EngineRunResult summaries as nodes.
    All writes are idempotent via MERGE on stable IDs.
Dependencies: json, neo4j, tributary.common, tributary.config
Used by: engine.cli (run-golden command), integration tests
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Generator

from tributary.common.errors import GraphWriteError
from tributary.common.logging import get_logger
from tributary.common.models_engine import EngineRunResult, LossCarryforwardRecord, ObligationResult

logger = get_logger(__name__)


class Neo4jGraphWriter:
    """Neo4j-backed GraphWriter. Persists engine results back to the graph.

    All writes are idempotent — safe to re-run with the same input.
    Monetary amounts are stored as floats (ISSUE-007).
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

    def write_obligation(self, entity_id: str, obligation: ObligationResult) -> None:
        """Persist one computed obligation, idempotent on obligation_id.

        Args:
            entity_id: The entity the obligation belongs to.
            obligation: The computed obligation result.
        Raises:
            GraphWriteError: On Neo4j write failure.
        """
        try:
            with self._session() as session:
                session.run(
                    """
                    MERGE (o:ObligationResult {obligation_id: $obligation_id})
                    SET o.entity_id = $entity_id,
                        o.jurisdiction = $jurisdiction,
                        o.obligation_type = $obligation_type,
                        o.taxable_base_hkd = $taxable_base_hkd,
                        o.rate = $rate,
                        o.net_amount_hkd = $net_amount_hkd,
                        o.rule_id = $rule_id,
                        o.as_of_date = $as_of_date,
                        o.source_flow_ids = $source_flow_ids,
                        o.needs_review = $needs_review
                    WITH o
                    MATCH (e:Entity {entity_id: $entity_id})
                    MERGE (e)-[:HAS_OBLIGATION]->(o)
                    """,
                    obligation_id=obligation.obligation_id,
                    entity_id=entity_id,
                    jurisdiction=obligation.jurisdiction,
                    obligation_type=obligation.obligation_type.value,
                    taxable_base_hkd=float(obligation.taxable_base_hkd),
                    rate=float(obligation.rate),
                    net_amount_hkd=float(obligation.net_amount_hkd),
                    rule_id=obligation.rule_id,
                    as_of_date=obligation.as_of_date.isoformat(),
                    source_flow_ids=json.dumps(obligation.source_flow_ids),
                    needs_review=obligation.needs_review,
                )
        except Exception as exc:
            raise GraphWriteError(f"Failed to write obligation {obligation.obligation_id}: {exc}") from exc
        logger.debug(
            "Persisted obligation",
            extra={"obligation_id": obligation.obligation_id, "entity_id": entity_id},
        )

    def update_loss_carryforward(
        self, entity_id: str, loss_record: LossCarryforwardRecord
    ) -> None:
        """Update remaining loss after the engine applied an offset, idempotent on key fields.

        Args:
            entity_id: The entity whose loss position to update.
            loss_record: Which loss was used and how much remains.
        Raises:
            GraphWriteError: On Neo4j write failure.
        """
        try:
            with self._session() as session:
                session.run(
                    """
                    MATCH (l:PriorPeriodLoss {
                        entity_id: $entity_id,
                        jurisdiction: $jurisdiction,
                        loss_period_start: $period_start,
                        loss_period_end: $period_end
                    })
                    SET l.remaining_loss_hkd = $remaining,
                        l.used_this_period_hkd = $used
                    """,
                    entity_id=entity_id,
                    jurisdiction=loss_record.jurisdiction,
                    period_start=loss_record.loss_period.start_date.isoformat(),
                    period_end=loss_record.loss_period.end_date.isoformat(),
                    remaining=float(loss_record.remaining_loss_hkd),
                    used=float(loss_record.used_this_period_hkd),
                )
        except Exception as exc:
            raise GraphWriteError(
                f"Failed to update loss carryforward for {entity_id}: {exc}"
            ) from exc
        logger.debug(
            "Updated loss carryforward",
            extra={"entity_id": entity_id, "jurisdiction": loss_record.jurisdiction},
        )

    def write_engine_run_summary(self, summary: EngineRunResult) -> None:
        """Persist a summary node for one engine run, idempotent on run_id.

        Args:
            summary: The complete result for one entity + period.
        Raises:
            GraphWriteError: On Neo4j write failure.
        """
        try:
            with self._session() as session:
                session.run(
                    """
                    MERGE (r:EngineRunResult {run_id: $run_id})
                    SET r.entity_id = $entity_id,
                        r.fiscal_period_start = $period_start,
                        r.fiscal_period_end = $period_end,
                        r.jurisdiction = $jurisdiction,
                        r.obligation_count = $obligation_count,
                        r.conflict_count = $conflict_count,
                        r.has_unresolved_items = $has_unresolved_items
                    WITH r
                    MATCH (e:Entity {entity_id: $entity_id})
                    MERGE (e)-[:HAS_RUN]->(r)
                    """,
                    run_id=summary.run_id,
                    entity_id=summary.entity_id,
                    period_start=summary.fiscal_period.start_date.isoformat(),
                    period_end=summary.fiscal_period.end_date.isoformat(),
                    jurisdiction=summary.fiscal_period.jurisdiction,
                    obligation_count=len(summary.obligations),
                    conflict_count=len(summary.conflicts),
                    has_unresolved_items=summary.has_unresolved_items,
                )
        except Exception as exc:
            raise GraphWriteError(
                f"Failed to write engine run summary {summary.run_id}: {exc}"
            ) from exc
        logger.debug(
            "Persisted engine run summary",
            extra={"run_id": summary.run_id, "entity_id": summary.entity_id},
        )
