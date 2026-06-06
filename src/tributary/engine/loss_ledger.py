"""
Module: loss_ledger
Layer: engine
Purpose: Apply prior-period loss carryforward against a taxable base using the jurisdiction's
    loss-relief rule (full offset up to a de-minimis, then a cap fraction — e.g. German
    Mindestbesteuerung, French 50% cap, HK unlimited). Country-agnostic; all limits from the pack.
Dependencies: decimal, tributary.common, tributary.rules
Used by: engine.runner, engine tests
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from tributary.common.models import (
    FiscalPeriod,
    JurisdictionCode,
    LossCarryforwardRecord,
    PriorPeriodLoss,
)
from tributary.rules.models import Rule


class LossOffsetResult(BaseModel):
    """Outcome of applying loss carryforward to a base."""

    post_loss_base_hkd: Decimal
    total_offset_hkd: Decimal
    limitation_applied: bool
    records: list[LossCarryforwardRecord]


def _allowable_offset(base: Decimal, total_loss: Decimal, rule: Rule | None) -> tuple[Decimal, bool]:
    """Compute the allowable offset and whether a limitation capped it.

    Args:
        base: Positive taxable base before offset.
        total_loss: Sum of available prior losses.
        rule: The loss-relief rule (None = unlimited offset).
    Returns:
        (allowable_offset, limitation_applied).
    """
    uncapped = min(total_loss, base)
    if rule is None or rule.parameters.unlimited:
        return uncapped, False
    de_minimis = rule.parameters.de_minimis_hkd or Decimal("0")
    cap_fraction = rule.parameters.cap_fraction or Decimal("1")
    if base <= de_minimis:
        return uncapped, False
    capped_allowance = de_minimis + cap_fraction * (base - de_minimis)
    allowable = min(total_loss, capped_allowance)
    return allowable, allowable < uncapped


def apply_loss_offset(
    base_hkd: Decimal,
    losses: list[PriorPeriodLoss],
    rule: Rule | None,
    jurisdiction: JurisdictionCode,
) -> LossOffsetResult:
    """Apply FIFO loss carryforward to a taxable base.

    Args:
        base_hkd: Taxable base before loss offset.
        losses: Prior losses, oldest first (FIFO).
        rule: The jurisdiction's loss-relief rule (None = no rule → unlimited).
        jurisdiction: The jurisdiction (for the produced records).
    Returns:
        LossOffsetResult with post-loss base and per-loss audit records.
    """
    if base_hkd <= 0 or not losses:
        return LossOffsetResult(
            post_loss_base_hkd=max(base_hkd, Decimal("0")),
            total_offset_hkd=Decimal("0"),
            limitation_applied=False,
            records=[],
        )
    total_loss = sum((loss.remaining_loss_hkd for loss in losses), Decimal("0"))
    allowable, limited = _allowable_offset(base_hkd, total_loss, rule)
    records = _allocate_fifo(losses, allowable, limited, jurisdiction)
    return LossOffsetResult(
        post_loss_base_hkd=base_hkd - allowable,
        total_offset_hkd=allowable,
        limitation_applied=limited,
        records=records,
    )


def _allocate_fifo(
    losses: list[PriorPeriodLoss],
    allowable: Decimal,
    limited: bool,
    jurisdiction: JurisdictionCode,
) -> list[LossCarryforwardRecord]:
    """Distribute the allowable offset across prior losses oldest-first."""
    remaining_to_use = allowable
    records: list[LossCarryforwardRecord] = []
    for loss in losses:
        used = min(loss.remaining_loss_hkd, remaining_to_use)
        remaining_to_use -= used
        records.append(
            LossCarryforwardRecord(
                entity_id=loss.entity_id,
                jurisdiction=jurisdiction,
                loss_period=FiscalPeriod(
                    jurisdiction=jurisdiction,
                    start_date=loss.loss_period_start,
                    end_date=loss.loss_period_end,
                ),
                original_loss_hkd=loss.original_loss_hkd,
                used_this_period_hkd=used,
                remaining_loss_hkd=loss.remaining_loss_hkd - used,
                limitation_applied=limited,
                limitation_rule_id=None,
            )
        )
        if remaining_to_use <= 0:
            break
    return records
