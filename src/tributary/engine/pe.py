"""
Module: pe
Layer: engine
Purpose: Permanent-establishment detection and profit attribution. When an entity's accumulated
    presence in another jurisdiction exceeds the treaty service-PE day threshold, a share of its
    net income (the treaty attribution_pct) is attributed to the PE jurisdiction. Country-agnostic.
Dependencies: decimal, tributary.common, tributary.rules, engine.aggregator, engine.thresholds,
    engine.money
Used by: engine.runner, engine.conflict, engine tests
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from tributary.common.models import (
    GraphReader,
    JurisdictionCode,
    ThresholdResult,
)
from tributary.engine.aggregator import EntityBase
from tributary.engine.money import round_hkd
from tributary.engine.thresholds import pe_days_check
from tributary.rules.models import Rule, RuleCategory, RulePackLoader


class PeAttribution(BaseModel):
    """A triggered permanent establishment and its attributed profit."""

    entity_id: str
    residence_jurisdiction: JurisdictionCode
    pe_jurisdiction: JurisdictionCode
    total_days: int
    attribution_pct: Decimal
    attributed_income_hkd: Decimal
    threshold: ThresholdResult
    treaty_pe_rule_id: str
    trigger_presence_ids: list[str]


def _pe_rule(loader: RulePackLoader, residence: JurisdictionCode, other: JurisdictionCode) -> Rule | None:
    """Return the treaty service-PE rule between two jurisdictions, if any."""
    for rule in loader.get_treaty_rules(residence, other):
        if rule.category == RuleCategory.TREATY_PE:
            return rule
    return None


def detect_pe(
    reader: GraphReader,
    loader: RulePackLoader,
    base: EntityBase,
    candidate_jurisdictions: list[JurisdictionCode],
) -> PeAttribution | None:
    """Detect a service PE for an entity in another jurisdiction and attribute profit.

    Args:
        reader: Graph reader (presence records).
        loader: Rule-pack loader (treaty PE rule).
        base: The entity's aggregated base (net_income_hkd is the attribution base).
        candidate_jurisdictions: Jurisdictions other than residence to test for presence.
    Returns:
        A PeAttribution if a PE is triggered, else None. The first triggered PE is returned
        (the golden scenario has exactly one).
    """
    for other in candidate_jurisdictions:
        if other == base.jurisdiction:
            continue
        records = reader.get_presence_records(
            base.entity_id, other, base.period.start_date, base.period.end_date
        )
        if not records:
            continue
        rule = _pe_rule(loader, base.jurisdiction, other)
        if rule is None:
            continue
        total_days = sum(r.total_days_present for r in records)
        threshold = pe_days_check(base.entity_id, other, total_days, rule)
        if not threshold.breached:
            continue
        pct = rule.parameters.attribution_pct or Decimal("0")
        return PeAttribution(
            entity_id=base.entity_id,
            residence_jurisdiction=base.jurisdiction,
            pe_jurisdiction=other,
            total_days=total_days,
            attribution_pct=pct,
            attributed_income_hkd=round_hkd(base.net_income_hkd * pct),
            threshold=threshold,
            treaty_pe_rule_id=rule.id,
            trigger_presence_ids=[r.presence_id for r in records],
        )
    return None
