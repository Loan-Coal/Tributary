"""
Module: periods
Layer: engine
Purpose: Derive a concrete FiscalPeriod for a jurisdiction from its FiscalCalendar and a
    reference fiscal-year start year. Country-agnostic — the calendar comes from the rule pack.
Dependencies: datetime, tributary.common.models
Used by: engine.runner
"""
from __future__ import annotations

from datetime import date, timedelta

from tributary.common.models import FiscalCalendar, FiscalPeriod


def compute_period(calendar: FiscalCalendar, start_year: int) -> FiscalPeriod:
    """Build the fiscal period that begins in ``start_year`` for a jurisdiction.

    Args:
        calendar: The jurisdiction's fiscal-year anchor (month/day).
        start_year: Calendar year in which the fiscal year begins.
    Returns:
        A FiscalPeriod running from the anchor for one year minus one day
        (e.g. HK Apr 1 2025 → Mar 31 2026; DE Jan 1 2025 → Dec 31 2025).
    """
    start = date(start_year, calendar.period_start_month, calendar.period_start_day)
    next_year_start = date(start_year + 1, calendar.period_start_month, calendar.period_start_day)
    end = next_year_start - timedelta(days=1)
    return FiscalPeriod(jurisdiction=calendar.jurisdiction, start_date=start, end_date=end)
