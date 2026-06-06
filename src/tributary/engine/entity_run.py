"""
Module: entity_run
Layer: engine
Purpose: Assemble all obligations, threshold checks, deadlines, and loss records for one entity
    (CIT, trade tax, WHT, VAT). Sub-engines are activated by the presence of the relevant rule
    category in the pack — never by jurisdiction name (DEC-006, DEC-009). PE threshold and the
    conflict flag are added by the runner (cross-entity concerns).
Dependencies: decimal, tributary.common, tributary.rules, engine sub-engines
Used by: engine.runner
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from tributary.common.errors import EngineError
from tributary.common.models import (
    DeadlineResult,
    FiscalPeriod,
    GraphReader,
    JurisdictionCode,
    LossCarryforwardRecord,
    ObligationResult,
    ObligationType,
    ThresholdResult,
)
from tributary.engine.aggregator import EntityBase
from tributary.engine.cit_engine import CitResult, compute_cit
from tributary.engine.deadlines import compute_deadline
from tributary.engine.flow_context import FlowJudgement, jurisdiction_needs_review
from tributary.engine.thresholds import zinsschranke_check
from tributary.engine.trade_tax_engine import compute_trade_tax
from tributary.engine.vat_engine import compute_vat
from tributary.engine.wht_engine import compute_wht
from tributary.rules.models import Rule, RuleCategory, RulePackLoader


class EntityArtifacts(BaseModel):
    """All engine outputs for one entity before PE threshold / conflict are attached."""

    entity_id: str
    jurisdiction: JurisdictionCode
    period: FiscalPeriod
    obligations: list[ObligationResult]
    threshold_checks: list[ThresholdResult]
    deadlines: list[DeadlineResult]
    loss_records: list[LossCarryforwardRecord]
    cit_review: bool


def _first(rules: list[Rule]) -> Rule | None:
    return rules[0] if rules else None


def build_entity_result(
    reader: GraphReader,
    loader: RulePackLoader,
    base: EntityBase,
    pe_adjustment_hkd: Decimal,
    judgements: dict[str, FlowJudgement],
) -> EntityArtifacts:
    """Build CIT / trade tax / WHT / VAT outputs for one entity.

    Args:
        reader: Graph reader (losses, ownership for WHT conditions).
        loader: Rule-pack loader.
        base: The entity's aggregated base.
        pe_adjustment_hkd: Signed PE adjustment to the CIT base.
        judgements: AI judgements for review flags.
    Returns:
        EntityArtifacts (PE threshold + conflict added later by the runner).
    Raises:
        EngineError: If the jurisdiction has no CIT rate rule.
    """
    jur = base.jurisdiction
    cit, cit_review = _run_cit(reader, loader, base, pe_adjustment_hkd, judgements)
    obligations: list[ObligationResult] = [cit.obligation]
    deadlines = _deadlines(loader, base, jur)
    thresholds = _thresholds(loader, base)
    post_loss = cit.loss_offset.post_loss_base_hkd
    obligations += _trade_tax(loader, base, post_loss, cit_review)
    obligations += _wht(reader, loader, base, cit_review, judgements)
    thresholds += _vat(loader, base, deadlines)
    return EntityArtifacts(
        entity_id=base.entity_id,
        jurisdiction=jur,
        period=base.period,
        obligations=obligations,
        threshold_checks=thresholds,
        deadlines=deadlines,
        loss_records=cit.loss_offset.records,
        cit_review=cit_review,
    )


def _run_cit(
    reader: GraphReader,
    loader: RulePackLoader,
    base: EntityBase,
    pe_adjustment_hkd: Decimal,
    judgements: dict[str, FlowJudgement],
) -> tuple[CitResult, bool]:
    """Validate and run the CIT sub-engine; return result + review flag."""
    jur = base.jurisdiction
    cit_rules = loader.get_rules(jur, RuleCategory.CIT_RATE)
    if not cit_rules:
        raise EngineError(f"No CIT rate rule for jurisdiction {jur}")
    cit_review = jurisdiction_needs_review(
        judgements, base.income_flow_ids + base.expense_flow_ids, jur
    )
    return compute_cit(
        base,
        pe_adjustment_hkd,
        cit_rules[0],
        _first(loader.get_rules(jur, RuleCategory.LOSS_RELIEF)),
        reader.get_prior_period_losses(base.entity_id, jur),
        cit_review,
    ), cit_review


def _deadlines(loader: RulePackLoader, base: EntityBase, jur: JurisdictionCode) -> list[DeadlineResult]:
    """Build CIT and trade-tax filing deadlines where rules exist."""
    out: list[DeadlineResult] = []
    cit_deadline = _first(loader.get_rules(jur, RuleCategory.CIT_DEADLINE))
    if cit_deadline is not None:
        out.append(compute_deadline(base.entity_id, ObligationType.CIT, base.period, cit_deadline))
    tt_deadline = _first(loader.get_rules(jur, RuleCategory.TRADE_TAX_DEADLINE))
    if tt_deadline is not None:
        out.append(compute_deadline(base.entity_id, ObligationType.TRADE_TAX, base.period, tt_deadline))
    return out


def _thresholds(loader: RulePackLoader, base: EntityBase) -> list[ThresholdResult]:
    """Build the interest-barrier (Zinsschranke) check where a rule exists and interest was paid."""
    barrier = _first(loader.get_rules(base.jurisdiction, RuleCategory.INTEREST_BARRIER))
    if barrier is not None and base.interest_expense_hkd > 0:
        return [zinsschranke_check(base, barrier)]
    return []


def _trade_tax(
    loader: RulePackLoader, base: EntityBase, post_loss_base: Decimal, review: bool
) -> list[ObligationResult]:
    """Build the trade-tax obligation where a trade-tax rate rule exists."""
    rule = _first(loader.get_rules(base.jurisdiction, RuleCategory.TRADE_TAX_RATE))
    if rule is None:
        return []
    return [compute_trade_tax(base, post_loss_base, rule, review)]


def _wht(
    reader,
    loader: RulePackLoader,
    base: EntityBase,
    cit_review: bool,
    judgements: dict[str, FlowJudgement],
) -> list[ObligationResult]:
    """Build a WHT obligation for each cross-border outbound payment."""
    out: list[ObligationResult] = []
    for payment in base.outbound_payments:
        review = jurisdiction_needs_review(judgements, [payment.flow_id], base.jurisdiction)
        out.append(compute_wht(reader, loader, payment, base.period, review))
    return out


def _vat(loader: RulePackLoader, base: EntityBase, deadlines: list[DeadlineResult]) -> list[ThresholdResult]:
    """Build the VAT threshold check (and append its filing deadline) where a rule exists."""
    threshold_rule = _first(loader.get_rules(base.jurisdiction, RuleCategory.VAT_THRESHOLD))
    if threshold_rule is None:
        return []
    result = compute_vat(base, threshold_rule, _first(loader.get_rules(base.jurisdiction, RuleCategory.VAT_FILING)))
    if result.deadline is not None:
        deadlines.append(result.deadline)
    return [result.threshold]
