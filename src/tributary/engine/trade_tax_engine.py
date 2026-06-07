"""
Module: trade_tax_engine
Layer: engine
Purpose: Local business / trade tax (e.g. German Gewerbesteuer) on the same post-loss base as
    CIT. Activated only when the jurisdiction's rule pack contains a trade-tax rate rule — never
    by jurisdiction name (DEC-006, DEC-009).
Dependencies: decimal, uuid, tributary.common, tributary.rules, engine.aggregator, engine.money
Used by: engine.runner, engine tests
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from tributary.common.models import (
    ComputationStep,
    ObligationResult,
    ObligationType,
)
from tributary.engine.aggregator import EntityBase
from tributary.engine.money import round_amount
from tributary.rules.models import Rule


def compute_trade_tax(
    base: EntityBase,
    post_loss_base_hkd: Decimal,
    trade_tax_rule: Rule,
    needs_review: bool,
) -> ObligationResult:
    """Compute the trade-tax obligation on the post-loss base.

    Args:
        base: Aggregated entity base (for entity/period/flow ids).
        post_loss_base_hkd: The same taxable base used for CIT after loss offset.
        trade_tax_rule: The trade-tax rate rule from the pack.
        needs_review: Whether a contributing attribution was low-confidence.
    Returns:
        The trade-tax ObligationResult.
    """
    rate = trade_tax_rule.parameters.rate or Decimal("0")
    gross = round_amount(post_loss_base_hkd * rate)
    step = ComputationStep(
        step_name="apply_rate",
        input_value_hkd=post_loss_base_hkd,
        rule_id=trade_tax_rule.id,
        rule_as_of_date=trade_tax_rule.as_of_date,
        result_value_hkd=gross,
        note="trade-tax rate applied to post-loss CIT base",
    )
    return _make_obligation(base, post_loss_base_hkd, rate, gross, trade_tax_rule, step, needs_review)


def _make_obligation(
    base: EntityBase,
    post_loss_base_hkd: Decimal,
    rate: Decimal,
    gross: Decimal,
    rule: Rule,
    step: ComputationStep,
    needs_review: bool,
) -> ObligationResult:
    """Construct the trade-tax ObligationResult from computed values."""
    return ObligationResult(
        obligation_id=str(uuid.uuid4()),
        entity_id=base.entity_id,
        jurisdiction=base.jurisdiction,
        obligation_type=ObligationType.TRADE_TAX,
        fiscal_period=base.period,
        taxable_base_hkd=post_loss_base_hkd,
        rate=rate,
        gross_amount_hkd=gross,
        treaty_relief_hkd=Decimal("0"),
        net_amount_hkd=gross,
        rule_id=rule.id,
        as_of_date=rule.as_of_date,
        source_citation=rule.source_citation,
        treaty_citation=None,
        source_flow_ids=base.income_flow_ids + base.expense_flow_ids,
        computation_trace=[step],
        needs_review=needs_review,
    )
