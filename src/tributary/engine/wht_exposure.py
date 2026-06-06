"""
Module: wht_exposure
Layer: engine
Purpose: Scan completed WHT ObligationResults against treaty entitlement and emit
    ConflictFlag(WHT_OVER_WITHHELD) when the domestic rate was applied despite a lower
    treaty rate being available. Country-agnostic — treaty data comes from rule packs.
Dependencies: decimal, tributary.common, tributary.rules, engine.wht_engine, engine.aggregator,
    engine.money
Used by: engine.runner
"""
from __future__ import annotations

from decimal import Decimal

from tributary.common.logging import get_logger
from tributary.common.models import (
    ConflictFlag,
    ConflictType,
    FiscalPeriod,
    GraphReader,
    ObligationResult,
    ObligationType,
    ReliefMechanism,
)
from tributary.engine.aggregator import OutboundPayment
from tributary.engine.money import round_hkd
from tributary.engine.wht_engine import get_treaty_rate
from tributary.rules.models import Rule, RulePackLoader

logger = get_logger(__name__)


def scan_wht_exposure(
    wht_obligations: list[ObligationResult],
    payments: list[OutboundPayment],
    loader: RulePackLoader,
    reader: GraphReader,
    period: FiscalPeriod,
) -> list[ConflictFlag]:
    """Check WHT obligations against treaty entitlement; flag over-withheld cases.

    Args:
        wht_obligations: All WHT-type ObligationResults for one entity.
        payments: The outbound payments that generated those obligations (order-independent).
        loader: Rule-pack loader for treaty lookup.
        reader: Graph reader for ownership condition checks.
        period: The entity's fiscal period (end date tests holding conditions).
    Returns:
        One ConflictFlag per over-withheld payment (empty list if all correct).
    """
    payment_map: dict[str, OutboundPayment] = {p.flow_id: p for p in payments}
    flags: list[ConflictFlag] = []
    for obligation in wht_obligations:
        flag = _check_obligation(obligation, payment_map, loader, reader, period)
        if flag is not None:
            flags.append(flag)
    return flags


def _check_obligation(
    obligation: ObligationResult,
    payment_map: dict[str, OutboundPayment],
    loader: RulePackLoader,
    reader: GraphReader,
    period: FiscalPeriod,
) -> ConflictFlag | None:
    """Return a ConflictFlag if this obligation is over-withheld, else None."""
    if obligation.obligation_type is not ObligationType.WHT:
        return None
    if obligation.treaty_citation is not None:
        return None  # treaty was already applied — nothing to flag
    if not obligation.source_flow_ids:
        return None
    payment = payment_map.get(obligation.source_flow_ids[0])
    if payment is None:
        logger.warning(
            "WHT obligation flow_id not in payment map",
            extra={"flow_id": obligation.source_flow_ids[0]},
        )
        return None
    treaty = get_treaty_rate(reader, loader, payment, period.end_date)
    if treaty is None:
        return None  # no treaty benefit exists — domestic rate is correct
    treaty_rate, treaty_rule = treaty
    if obligation.rate <= treaty_rate:
        return None  # rate already at or below treaty entitlement
    return _build_flag(obligation, payment, treaty_rate, treaty_rule)


def _build_flag(
    obligation: ObligationResult,
    payment: OutboundPayment,
    treaty_rate: Decimal,
    treaty_rule: Rule,
) -> ConflictFlag:
    """Build a WHT_OVER_WITHHELD ConflictFlag for one over-withheld payment.

    Field mapping (WHT semantics):
        residence_jurisdiction → payer jurisdiction (applying the withholding)
        pe_jurisdiction        → payee jurisdiction (receiving less than entitled)
        pe_tax_hkd             → actual WHT applied
        residence_tax_before_relief_hkd → treaty-entitled WHT (lower rate × base)
        relieved_amount_hkd    → over-withheld amount (actual − treaty)
    """
    treaty_wht = round_hkd(payment.gross_hkd * treaty_rate)
    actual_wht = obligation.net_amount_hkd
    over_withheld = actual_wht - treaty_wht
    return ConflictFlag(
        conflict_id=f"WHT-{obligation.source_flow_ids[0]}",
        conflict_type=ConflictType.WHT_OVER_WITHHELD,
        trigger_flow_ids=obligation.source_flow_ids,
        entities=[payment.payer_entity_id, payment.payee_entity_id],
        jurisdictions=[payment.payer_jurisdiction, payment.payee_jurisdiction],
        attributed_base_hkd=payment.gross_hkd,
        residence_jurisdiction=payment.payer_jurisdiction,
        pe_jurisdiction=payment.payee_jurisdiction,
        pe_tax_hkd=actual_wht,
        residence_tax_before_relief_hkd=treaty_wht,
        relief_mechanism=ReliefMechanism.CREDIT,
        relieved_amount_hkd=over_withheld,
        residual_double_tax_hkd=Decimal("0"),
        treaty_rule_id=treaty_rule.id,
        treaty_as_of_date=treaty_rule.as_of_date,
        treaty_source_citation=treaty_rule.source_citation,
        credit_method_note=(
            f"Applied: {obligation.rate * 100:.1f}%. "
            f"Treaty entitlement: {treaty_rate * 100:.1f}%. "
            f"Over-withheld: HKD {over_withheld}. "
            f"Reclaim via treaty procedure ({treaty_rule.source_citation})."
        ),
        needs_review=True,
    )
