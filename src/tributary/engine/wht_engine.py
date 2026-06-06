"""
Module: wht_engine
Layer: engine
Purpose: Withholding-tax computation for one cross-border outbound payment. Applies the payer
    jurisdiction's domestic rate, then a treaty / EU-directive reduced rate when its conditions
    (EU membership, minimum holding, holding period) are satisfied. Country-agnostic.
Dependencies: datetime, decimal, uuid, tributary.common, tributary.rules, engine.aggregator,
    engine.money
Used by: engine.runner, engine tests
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from tributary.common.errors import EngineError
from tributary.common.models import (
    ActivityType,
    ComputationStep,
    FiscalPeriod,
    GraphReader,
    ObligationResult,
    ObligationType,
    RuleCitation,
)
from tributary.engine.aggregator import OutboundPayment
from tributary.engine.money import round_hkd
from tributary.rules.models import Rule, RuleCategory, RulePackLoader

# EU member states — reference data (would live in a reference table in production).
EU_MEMBER_JURISDICTIONS: frozenset[str] = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU",
    "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
})

_DOMESTIC_CATEGORY: dict[ActivityType, RuleCategory] = {
    ActivityType.DIVIDEND: RuleCategory.WHT_DIVIDEND,
    ActivityType.INTEREST: RuleCategory.WHT_INTEREST,
    ActivityType.ROYALTY: RuleCategory.WHT_ROYALTY,
    ActivityType.MANAGEMENT_FEE: RuleCategory.WHT_MANAGEMENT_FEE,
}
_TREATY_CATEGORY: dict[ActivityType, RuleCategory] = {
    ActivityType.DIVIDEND: RuleCategory.TREATY_DIVIDEND,
    ActivityType.INTEREST: RuleCategory.TREATY_INTEREST,
    ActivityType.ROYALTY: RuleCategory.TREATY_ROYALTY,
}


def _months_between(start: date, end: date) -> int:
    """Whole months from start to end."""
    return (end.year - start.year) * 12 + (end.month - start.month)


def _holding_qualifies(
    reader: GraphReader, payer_id: str, payee_id: str, rule: Rule, as_of: date
) -> bool:
    """Check the treaty rule's holding percentage and duration between payer and payee."""
    min_pct = rule.parameters.min_holding_pct
    if min_pct is None:
        return True
    min_months = rule.parameters.min_holding_months or 0
    candidates = reader.get_entity_ownership(payee_id) + reader.get_entity_ownership(payer_id)
    for edge in candidates:
        pair = {edge.owner_entity_id, edge.owned_entity_id}
        if pair == {payer_id, payee_id} and edge.ownership_pct >= min_pct:
            if _months_between(edge.effective_from, as_of) >= min_months:
                return True
    return False


def _treaty_rate(
    reader: GraphReader,
    loader: RulePackLoader,
    payment: OutboundPayment,
    as_of: date,
) -> tuple[Decimal, Rule] | None:
    """Return the applicable treaty/directive rate and rule, or None if no benefit applies."""
    category = _TREATY_CATEGORY.get(payment.activity)
    if category is None:
        return None
    for rule in loader.get_treaty_rules(payment.payer_jurisdiction, payment.payee_jurisdiction):
        if rule.category != category:
            continue
        if rule.parameters.requires_eu and not _both_eu(payment):
            continue
        if not _holding_qualifies(reader, payment.payer_entity_id, payment.payee_entity_id, rule, as_of):
            continue
        return rule.parameters.treaty_rate or Decimal("0"), rule
    return None


def _both_eu(payment: OutboundPayment) -> bool:
    return (
        payment.payer_jurisdiction in EU_MEMBER_JURISDICTIONS
        and payment.payee_jurisdiction in EU_MEMBER_JURISDICTIONS
    )


def compute_wht(
    reader: GraphReader,
    loader: RulePackLoader,
    payment: OutboundPayment,
    period: FiscalPeriod,
    needs_review: bool,
) -> ObligationResult:
    """Compute the WHT obligation for one outbound payment.

    Args:
        reader: Graph reader (ownership lookups for treaty conditions).
        loader: Rule-pack loader (domestic + treaty rates).
        payment: The outbound payment.
        period: The payer's fiscal period (its end date tests holding conditions).
        needs_review: Whether a contributing attribution was low-confidence.
    Returns:
        The WHT ObligationResult (gross at domestic rate, net after treaty relief).
    Raises:
        EngineError: If no domestic WHT rule exists for the payer jurisdiction + activity.
    """
    domestic_rules = loader.get_rules(payment.payer_jurisdiction, _DOMESTIC_CATEGORY[payment.activity])
    if not domestic_rules:
        raise EngineError(
            f"No domestic WHT rule for {payment.payer_jurisdiction} {payment.activity.value}"
        )
    domestic = domestic_rules[0]
    domestic_rate = domestic.parameters.domestic_rate or Decimal("0")
    treaty = _treaty_rate(reader, loader, payment, period.end_date)
    applicable_rate = treaty[0] if treaty is not None else domestic_rate
    treaty_citation = _citation(treaty[1]) if treaty is not None else None
    gross = round_hkd(payment.gross_hkd * domestic_rate)
    net = round_hkd(payment.gross_hkd * applicable_rate)
    return _build_obligation(
        payment, period, domestic, applicable_rate, gross, net, treaty_citation, needs_review
    )


def _citation(rule: Rule) -> RuleCitation:
    return RuleCitation(
        rule_id=rule.id,
        jurisdiction=rule.jurisdiction,
        as_of_date=rule.as_of_date,
        source_citation=rule.source_citation,
    )


def _build_obligation(
    payment: OutboundPayment,
    period: FiscalPeriod,
    domestic: Rule,
    applicable_rate: Decimal,
    gross: Decimal,
    net: Decimal,
    treaty_citation: RuleCitation | None,
    needs_review: bool,
) -> ObligationResult:
    """Assemble the WHT ObligationResult with a two-step (domestic → treaty) trace."""
    trace = [
        ComputationStep(
            step_name="apply_domestic_rate",
            input_value_hkd=payment.gross_hkd,
            rule_id=domestic.id,
            rule_as_of_date=domestic.as_of_date,
            result_value_hkd=gross,
            note="WHT at domestic rate (before treaty relief)",
        ),
        ComputationStep(
            step_name="apply_treaty_relief",
            input_value_hkd=gross,
            rule_id=treaty_citation.rule_id if treaty_citation else domestic.id,
            rule_as_of_date=treaty_citation.as_of_date if treaty_citation else domestic.as_of_date,
            result_value_hkd=net,
            note="WHT after treaty / directive relief",
        ),
    ]
    return ObligationResult(
        obligation_id=str(uuid.uuid4()),
        entity_id=payment.payer_entity_id,
        jurisdiction=payment.payer_jurisdiction,
        obligation_type=ObligationType.WHT,
        fiscal_period=period,
        taxable_base_hkd=payment.gross_hkd,
        rate=applicable_rate,
        gross_amount_hkd=gross,
        treaty_relief_hkd=gross - net,
        net_amount_hkd=net,
        rule_id=domestic.id,
        as_of_date=domestic.as_of_date,
        source_citation=domestic.source_citation,
        treaty_citation=treaty_citation,
        source_flow_ids=[payment.flow_id],
        computation_trace=trace,
        needs_review=needs_review,
    )
