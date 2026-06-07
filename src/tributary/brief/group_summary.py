"""
Module: group_summary
Layer: brief
Purpose: Build a GroupSummary aggregating tax exposure across all entities.
Dependencies: decimal, datetime, common.models_engine, common.models_entity
Used by: engine.cli (_run → _write_outputs)
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel

from tributary.common.models_engine import (
    ConflictFlag,
    EngineRunResult,
    GroupReliefOpportunity,
    ObligationType,
)
from tributary.common.models_entity import EntityRecord

_ZERO = Decimal("0")


class EntityTaxLine(BaseModel):
    """Per-entity row for the group summary table."""

    entity_id: str
    entity_name: str
    jurisdiction: str
    cit_hkd: Decimal
    trade_tax_hkd: Decimal
    wht_net_hkd: Decimal
    total_hkd: Decimal
    needs_review: bool


class GroupSummary(BaseModel):
    """Aggregated tax exposure across all entities in the group."""

    generated_at: datetime
    fiscal_year: int
    entity_lines: list[EntityTaxLine]
    total_cit_hkd: Decimal
    total_trade_tax_hkd: Decimal
    total_wht_hkd: Decimal
    total_obligation_hkd: Decimal
    residual_double_tax_hkd: Decimal
    conflicts: list[ConflictFlag]
    group_relief_opportunities: list[GroupReliefOpportunity]
    review_flag_count: int
    open_items: list[str]


def build_group_summary(
    results: list[EngineRunResult],
    entities: dict[str, EntityRecord],
) -> GroupSummary:
    """Aggregate engine results into a group-level summary.

    Args:
        results: One EngineRunResult per entity.
        entities: Map of entity_id → EntityRecord for name/jurisdiction lookup.
    Returns:
        GroupSummary with totals, conflicts de-duplicated, and open items aggregated.
    """
    lines: list[EntityTaxLine] = []
    all_conflicts: list[ConflictFlag] = []
    seen_conflict_ids: set[str] = set()
    all_relief: list[GroupReliefOpportunity] = []
    seen_relief_ids: set[str] = set()
    open_items: list[str] = []

    fiscal_year = results[0].fiscal_period.end_date.year if results else 2025

    for result in results:
        entity = entities.get(result.entity_id)
        entity_name = entity.name if entity else result.entity_id
        jurisdiction = entity.resident_jurisdiction if entity else "??"

        cit = sum(
            (o.net_amount_hkd for o in result.obligations if o.obligation_type == ObligationType.CIT),
            _ZERO,
        )
        trade_tax = sum(
            (o.net_amount_hkd for o in result.obligations if o.obligation_type == ObligationType.TRADE_TAX),
            _ZERO,
        )
        wht = sum(
            (o.net_amount_hkd for o in result.obligations if o.obligation_type == ObligationType.WHT),
            _ZERO,
        )
        total = cit + trade_tax + wht
        needs_review = result.has_unresolved_items or any(o.needs_review for o in result.obligations)

        lines.append(EntityTaxLine(
            entity_id=result.entity_id,
            entity_name=entity_name,
            jurisdiction=jurisdiction,
            cit_hkd=cit,
            trade_tax_hkd=trade_tax,
            wht_net_hkd=wht,
            total_hkd=total,
            needs_review=needs_review,
        ))

        for conflict in result.conflicts:
            if conflict.conflict_id not in seen_conflict_ids:
                all_conflicts.append(conflict)
                seen_conflict_ids.add(conflict.conflict_id)

        for opp in result.group_relief_opportunities:
            if opp.opportunity_id not in seen_relief_ids:
                all_relief.append(opp)
                seen_relief_ids.add(opp.opportunity_id)

        for ob in result.obligations:
            if ob.needs_review and ob.review_reason:
                open_items.append(f"{result.entity_id} [{ob.obligation_type.value}]: {ob.review_reason}")

    total_cit = sum((ln.cit_hkd for ln in lines), _ZERO)
    total_trade = sum((ln.trade_tax_hkd for ln in lines), _ZERO)
    total_wht = sum((ln.wht_net_hkd for ln in lines), _ZERO)
    total_all = total_cit + total_trade + total_wht
    residual_dt = sum((c.residual_double_tax_hkd for c in all_conflicts), _ZERO)
    review_count = sum(1 for ln in lines if ln.needs_review)

    return GroupSummary(
        generated_at=datetime.now(tz=timezone.utc),
        fiscal_year=fiscal_year,
        entity_lines=lines,
        total_cit_hkd=total_cit,
        total_trade_tax_hkd=total_trade,
        total_wht_hkd=total_wht,
        total_obligation_hkd=total_all,
        residual_double_tax_hkd=residual_dt,
        conflicts=all_conflicts,
        group_relief_opportunities=all_relief,
        review_flag_count=review_count,
        open_items=open_items,
    )
