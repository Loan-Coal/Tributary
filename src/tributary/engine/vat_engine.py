"""
Module: vat_engine
Layer: engine
Purpose: VAT obligation determination (v1 = filing-obligation flag only, no net VAT arithmetic
    — ISSUE-005). Checks turnover against the registration threshold and, if breached, produces
    the filing deadline. Activated only when the rule pack contains a VAT threshold rule.
Dependencies: tributary.common, tributary.rules, engine.aggregator, engine.thresholds,
    engine.deadlines
Used by: engine.runner, engine tests
"""
from __future__ import annotations

from pydantic import BaseModel

from tributary.common.models import DeadlineResult, ObligationType, ThresholdResult
from tributary.engine.aggregator import EntityBase
from tributary.engine.deadlines import compute_deadline
from tributary.engine.thresholds import vat_threshold_check
from tributary.rules.models import Rule


class VatResult(BaseModel):
    """VAT outcome: the threshold check plus a filing deadline when the obligation is triggered."""

    threshold: ThresholdResult
    deadline: DeadlineResult | None


def compute_vat(
    base: EntityBase,
    threshold_rule: Rule,
    filing_rule: Rule | None,
) -> VatResult:
    """Determine the VAT filing obligation for an entity.

    Args:
        base: Aggregated entity base (third-party turnover drives the check).
        threshold_rule: The VAT registration threshold rule.
        filing_rule: The VAT filing deadline rule (None → no deadline emitted).
    Returns:
        VatResult; deadline is populated only when the threshold is breached.
    """
    check = vat_threshold_check(base, threshold_rule)
    deadline: DeadlineResult | None = None
    if check.breached and filing_rule is not None:
        deadline = compute_deadline(base.entity_id, ObligationType.VAT, base.period, filing_rule)
    return VatResult(threshold=check, deadline=deadline)
