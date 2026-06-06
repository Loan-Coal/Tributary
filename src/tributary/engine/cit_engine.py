"""
Module: cit_engine
Layer: engine
Purpose: Corporate income tax computation for one entity — applies PE adjustment, loss
    carryforward, and the (surcharge-adjusted) CIT rate to the aggregated base. Country-agnostic:
    the rate, surcharge, and loss limits all come from the rule pack.
Dependencies: decimal, uuid, tributary.common, tributary.rules, engine.aggregator,
    engine.loss_ledger, engine.money
Used by: engine.runner, engine tests
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel

from tributary.common.models import (
    ComputationStep,
    ObligationResult,
    ObligationType,
    PriorPeriodLoss,
)
from tributary.engine.aggregator import EntityBase
from tributary.engine.loss_ledger import LossOffsetResult, apply_loss_offset
from tributary.engine.money import effective_rate, round_hkd
from tributary.rules.models import Rule


class CitResult(BaseModel):
    """CIT obligation plus the loss offset that fed it (for the run summary)."""

    obligation: ObligationResult
    loss_offset: LossOffsetResult
    pre_loss_base_hkd: Decimal


def compute_cit(
    base: EntityBase,
    pe_adjustment_hkd: Decimal,
    cit_rule: Rule,
    loss_rule: Rule | None,
    losses: list[PriorPeriodLoss],
    needs_review: bool,
) -> CitResult:
    """Compute the CIT obligation for one entity.

    Args:
        base: Aggregated income/expense for the entity.
        pe_adjustment_hkd: Signed PE adjustment (negative = exempted PE profits removed from a
            residence-state base; positive = PE-attributed profits added in the PE state).
        cit_rule: The CIT rate rule (carries rate and optional surcharge).
        loss_rule: The loss-relief rule (None = no carryforward limit rule).
        losses: Prior-period losses (oldest first).
        needs_review: Whether a contributing attribution was low-confidence.
    Returns:
        CitResult with the obligation, loss offset, and pre-loss base.
    """
    pre_loss_base = base.net_income_hkd + pe_adjustment_hkd
    offset = apply_loss_offset(pre_loss_base, losses, loss_rule, base.jurisdiction)
    post_loss_base = offset.post_loss_base_hkd
    if cit_rule.parameters.rate is None:
        from tributary.common.errors import EngineError
        raise EngineError(f"CIT rate not found in rule pack for rule {cit_rule.id}")
    rate = effective_rate(cit_rule.parameters.rate, cit_rule.parameters.surcharge_rate)
    gross = round_hkd(post_loss_base * rate)
    trace = _build_trace(base, pe_adjustment_hkd, pre_loss_base, offset, post_loss_base, gross, cit_rule)
    obligation = ObligationResult(
        obligation_id=str(uuid.uuid4()),
        entity_id=base.entity_id,
        jurisdiction=base.jurisdiction,
        obligation_type=ObligationType.CIT,
        fiscal_period=base.period,
        taxable_base_hkd=post_loss_base,
        rate=rate,
        gross_amount_hkd=gross,
        treaty_relief_hkd=Decimal("0"),
        net_amount_hkd=gross,
        rule_id=cit_rule.id,
        as_of_date=cit_rule.as_of_date,
        source_citation=cit_rule.source_citation,
        treaty_citation=None,
        source_flow_ids=base.income_flow_ids + base.expense_flow_ids,
        computation_trace=trace,
        needs_review=needs_review,
    )
    return CitResult(obligation=obligation, loss_offset=offset, pre_loss_base_hkd=pre_loss_base)


def _build_trace(
    base: EntityBase,
    pe_adjustment_hkd: Decimal,
    pre_loss_base: Decimal,
    offset: LossOffsetResult,
    post_loss_base: Decimal,
    gross: Decimal,
    cit_rule: Rule,
) -> list[ComputationStep]:
    """Build the audit trail for a CIT computation."""
    steps = [
        ComputationStep(
            step_name="aggregate_base",
            input_value_hkd=base.net_income_hkd,
            rule_id=cit_rule.id,
            rule_as_of_date=cit_rule.as_of_date,
            result_value_hkd=base.net_income_hkd,
            note="third_party + IC taxable income - deductible expense",
        )
    ]
    if pe_adjustment_hkd != 0:
        steps.append(
            ComputationStep(
                step_name="pe_adjustment",
                input_value_hkd=base.net_income_hkd,
                rule_id=cit_rule.id,
                rule_as_of_date=cit_rule.as_of_date,
                result_value_hkd=pre_loss_base,
                note="PE-attributed profits exempted (residence) or added (PE state)",
            )
        )
    if offset.total_offset_hkd != 0:
        steps.append(
            ComputationStep(
                step_name="apply_loss_offset",
                input_value_hkd=pre_loss_base,
                rule_id=cit_rule.id,
                rule_as_of_date=cit_rule.as_of_date,
                result_value_hkd=post_loss_base,
                note=f"loss offset {offset.total_offset_hkd} applied",
            )
        )
    steps.append(
        ComputationStep(
            step_name="apply_rate",
            input_value_hkd=post_loss_base,
            rule_id=cit_rule.id,
            rule_as_of_date=cit_rule.as_of_date,
            result_value_hkd=gross,
            note=f"effective rate applied to base",
        )
    )
    return steps
