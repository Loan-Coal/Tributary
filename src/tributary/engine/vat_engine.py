"""
Module: vat_engine
Layer: engine
Purpose: VAT obligation determination (v1 = filing-obligation flag only, no net VAT arithmetic
    — ISSUE-005). Checks turnover against the registration threshold and, if breached, produces
    the filing deadline and a VAT ObligationResult with needs_review=True (Wave 7b).
Dependencies: decimal, uuid, tributary.common, tributary.rules, engine.aggregator,
    engine.thresholds, engine.deadlines
Used by: engine.entity_run
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel

from tributary.common.models import (
    DeadlineResult,
    ObligationResult,
    ObligationType,
    ThresholdResult,
)
from tributary.engine.aggregator import EntityBase
from tributary.engine.deadlines import compute_deadline
from tributary.engine.thresholds import vat_threshold_check
from tributary.rules.models import Rule

_VAT_REVIEW_REASON = (
    "VAT net arithmetic not modelled; filing obligation requires quarterly returns. "
    "Net VAT payable and input VAT recovery are out of scope for v1 (ISSUE-005)."
)


class VatResult(BaseModel):
    """VAT outcome: threshold check, optional filing deadline, and optional VAT obligation."""

    threshold: ThresholdResult
    deadline: DeadlineResult | None
    obligation: ObligationResult | None


def _build_vat_obligation(base: EntityBase, threshold_rule: Rule) -> ObligationResult:
    """Build a VAT ObligationResult (filing-flag only; net amount = 0).

    Args:
        base: Aggregated entity base (provides entity_id, jurisdiction, period).
        threshold_rule: The VAT threshold rule (used for rule_id, citation, as_of_date).
    Returns:
        ObligationResult flagged needs_review=True with zero arithmetic amounts.
    """
    return ObligationResult(
        obligation_id=str(uuid.uuid4()),
        entity_id=base.entity_id,
        jurisdiction=base.jurisdiction,
        obligation_type=ObligationType.VAT,
        fiscal_period=base.period,
        taxable_base_hkd=base.third_party_income_hkd,
        rate=Decimal("0"),
        gross_amount_hkd=Decimal("0"),
        treaty_relief_hkd=Decimal("0"),
        net_amount_hkd=Decimal("0"),
        rule_id=threshold_rule.id,
        as_of_date=threshold_rule.as_of_date,
        source_citation=threshold_rule.source_citation,
        treaty_citation=None,
        source_flow_ids=[],
        computation_trace=[],
        needs_review=True,
        review_reason=_VAT_REVIEW_REASON,
    )


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
        VatResult; deadline and obligation are populated only when the threshold is breached.
    """
    check = vat_threshold_check(base, threshold_rule)
    if not check.breached:
        return VatResult(threshold=check, deadline=None, obligation=None)
    deadline: DeadlineResult | None = None
    if filing_rule is not None:
        deadline = compute_deadline(base.entity_id, ObligationType.VAT, base.period, filing_rule)
    obligation = _build_vat_obligation(base, threshold_rule)
    return VatResult(threshold=check, deadline=deadline, obligation=obligation)
