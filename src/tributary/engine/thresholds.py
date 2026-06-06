"""
Module: thresholds
Layer: engine
Purpose: Rule-driven threshold checks that emit ThresholdResult — VAT registration, the German
    Zinsschranke interest barrier, and the service-PE day count. Country-agnostic: every limit
    comes from the rule pack / treaty pack.
Dependencies: decimal, tributary.common, tributary.rules, engine.aggregator
Used by: engine.runner, engine tests
"""
from __future__ import annotations

from decimal import Decimal

from tributary.common.models import JurisdictionCode, ThresholdResult
from tributary.engine.aggregator import EntityBase
from tributary.rules.models import Rule


def vat_threshold_check(base: EntityBase, rule: Rule) -> ThresholdResult:
    """Check third-party turnover against the VAT registration threshold."""
    threshold = rule.parameters.threshold_hkd or Decimal("0")
    actual = base.third_party_income_hkd
    return ThresholdResult(
        entity_id=base.entity_id,
        jurisdiction=base.jurisdiction,
        rule_id=rule.id,
        threshold_name="vat_registration",
        threshold_value_hkd=threshold,
        actual_value_hkd=actual,
        breached=actual > threshold,
        as_of_date=rule.as_of_date,
        source_citation=rule.source_citation,
    )


def zinsschranke_check(base: EntityBase, rule: Rule) -> ThresholdResult:
    """Check net interest expense against the cap_fraction × EBITDA-proxy interest barrier."""
    cap_fraction = rule.parameters.cap_fraction or Decimal("0")
    non_interest_deductible = base.deductible_expense_hkd - base.interest_expense_hkd
    ebitda_proxy = base.third_party_income_hkd + base.ic_income_taxable_hkd - non_interest_deductible
    # Clamp to 0: a negative EBITDA yields a negative cap, falsely flagging any positive interest.
    # Under German law, zero/negative EBITDA means no interest is deductible (cap = 0, not negative).
    ebitda_proxy = max(ebitda_proxy, Decimal("0"))
    cap = cap_fraction * ebitda_proxy
    return ThresholdResult(
        entity_id=base.entity_id,
        jurisdiction=base.jurisdiction,
        rule_id=rule.id,
        threshold_name="zinsschranke_interest_barrier",
        threshold_value_hkd=cap,
        actual_value_hkd=base.interest_expense_hkd,
        breached=base.interest_expense_hkd > cap,
        as_of_date=rule.as_of_date,
        source_citation=rule.source_citation,
    )


def pe_days_check(
    entity_id: str,
    pe_jurisdiction: JurisdictionCode,
    total_days: int,
    rule: Rule,
) -> ThresholdResult:
    """Check accumulated presence days against the treaty service-PE day threshold.

    Note:
        threshold_value_hkd / actual_value_hkd carry the day counts (the model only exposes
        ``_hkd`` numeric slots); threshold_name flags that these are days, not currency.
    """
    day_count = rule.parameters.day_count or 0
    return ThresholdResult(
        entity_id=entity_id,
        jurisdiction=pe_jurisdiction,
        rule_id=rule.id,
        threshold_name="service_pe_days",
        threshold_value_hkd=Decimal(day_count),
        actual_value_hkd=Decimal(total_days),
        breached=total_days > day_count,
        as_of_date=rule.as_of_date,
        source_citation=rule.source_citation,
    )
