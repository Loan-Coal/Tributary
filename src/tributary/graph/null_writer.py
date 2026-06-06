"""
Module: null_writer
Layer: graph
Purpose: No-op GraphWriter for demo mode and offline testing. Logs all write operations
    at DEBUG level without persisting anything. Satisfies the GraphWriter protocol.
Dependencies: tributary.common
Used by: engine.cli (demo command), unit tests
"""
from __future__ import annotations

from tributary.common.logging import get_logger
from tributary.common.models_engine import EngineRunResult, LossCarryforwardRecord, ObligationResult

logger = get_logger(__name__)


class NullGraphWriter:
    """GraphWriter that logs writes at DEBUG level and returns without persisting.

    Satisfies the GraphWriter protocol for demo and offline testing contexts.
    All write methods are no-ops; they are safe to call any number of times.
    """

    def write_obligation(self, entity_id: str, obligation: ObligationResult) -> None:
        """Log a write_obligation call without persisting.

        Args:
            entity_id: The entity the obligation belongs to.
            obligation: The computed obligation result.
        """
        logger.debug(
            "NullGraphWriter.write_obligation (no-op)",
            extra={"entity_id": entity_id, "obligation_id": obligation.obligation_id},
        )

    def update_loss_carryforward(
        self, entity_id: str, loss_record: LossCarryforwardRecord
    ) -> None:
        """Log an update_loss_carryforward call without persisting.

        Args:
            entity_id: The entity whose loss position to update.
            loss_record: Which loss was used and how much remains.
        """
        logger.debug(
            "NullGraphWriter.update_loss_carryforward (no-op)",
            extra={"entity_id": entity_id, "jurisdiction": loss_record.jurisdiction},
        )

    def write_engine_run_summary(self, summary: EngineRunResult) -> None:
        """Log a write_engine_run_summary call without persisting.

        Args:
            summary: The complete result for one entity + period.
        """
        logger.debug(
            "NullGraphWriter.write_engine_run_summary (no-op)",
            extra={"run_id": summary.run_id, "entity_id": summary.entity_id},
        )
