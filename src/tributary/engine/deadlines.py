"""
Module: deadlines
Layer: engine
Purpose: Compute filing/payment deadlines for an obligation from the jurisdiction's deadline rule
    (filing month/day after the fiscal period) and fiscal period. Country-agnostic.
Dependencies: datetime, tributary.common, tributary.rules
Used by: engine.runner, engine tests
"""
from __future__ import annotations

from datetime import date, timedelta

from tributary.common.errors import EngineError
from tributary.common.models import (
    DeadlineResult,
    FiscalPeriod,
    ObligationType,
)
from tributary.rules.models import Rule


def compute_deadline(
    entity_id: str,
    obligation_type: ObligationType,
    period: FiscalPeriod,
    rule: Rule,
) -> DeadlineResult:
    """Compute the filing and payment deadline for an obligation.

    The filing deadline is the rule's month/day in the first year in which it falls strictly
    after the period end — the same year when the period ends earlier in the year (HK: ends
    Mar 31 2026, files Apr 30 2026), otherwise the next year (DE: ends Dec 31 2025, files
    Jul 31 2026).

    Args:
        entity_id: The entity.
        obligation_type: The obligation the deadline applies to.
        period: The fiscal period.
        rule: The deadline rule (filing_month, filing_day, optional payment_offset_days).
    Returns:
        The DeadlineResult.
    """
    if rule.parameters.filing_month is None:
        raise EngineError(f"Deadline rule {rule.id} is missing filing_month")
    filing_deadline, payment_deadline = _calculate_deadline_dates(rule, period.end_date)
    return DeadlineResult(
        entity_id=entity_id,
        jurisdiction=period.jurisdiction,
        obligation_type=obligation_type,
        filing_deadline=filing_deadline,
        payment_deadline=payment_deadline,
        rule_id=rule.id,
        as_of_date=rule.as_of_date,
        source_citation=rule.source_citation,
        fiscal_period=period,
    )


def _calculate_deadline_dates(rule: Rule, end: date) -> tuple[date, date]:
    """Compute (filing_deadline, payment_deadline) from the deadline rule and period end."""
    filing_month = rule.parameters.filing_month
    filing_day = rule.parameters.filing_day or 1
    same_year = (filing_month, filing_day) > (end.month, end.day)
    year = end.year if same_year else end.year + 1
    filing_deadline = date(year, filing_month, filing_day)
    offset = rule.parameters.payment_offset_days or 0
    return filing_deadline, filing_deadline + timedelta(days=offset)
