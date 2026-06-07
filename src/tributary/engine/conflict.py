"""
Module: conflict
Layer: engine
Purpose: Build the cross-border ConflictFlag for a detected PE. The same attributed base is
    claimed by the residence state (worldwide, pre-relief) and the PE state. The treaty's
    elimination method decides the outcome — for DE-FR PE business profits this is EXEMPTION, so
    Germany gives up its claim and there is no residual double tax (the credit figure is shown
    for information only). Country-agnostic; mechanism comes from the treaty pack (DEC-017).
Dependencies: decimal, tributary.common, tributary.rules, engine.pe, engine.money
Used by: engine.runner, engine tests
"""
from __future__ import annotations

from decimal import Decimal

from tributary.common.models import (
    ConflictFlag,
    ConflictType,
    ReliefMechanism,
)
from tributary.engine.money import effective_rate, round_amount
from tributary.engine.pe import PeAttribution
from tributary.rules.models import Rule


def build_pe_conflict(
    pe: PeAttribution,
    residence_cit_rule: Rule,
    pe_cit_rule: Rule,
    elimination_rule: Rule,
    pe_entity_id: str,
    conflict_year: int,
) -> ConflictFlag:
    """Build a PE double-taxation conflict flag and its treaty resolution.

    Args:
        pe: The detected PE attribution.
        residence_cit_rule: CIT rate rule of the residence state (Germany).
        pe_cit_rule: CIT rate rule of the PE state (France).
        elimination_rule: The treaty elimination rule (carries relief_mechanism).
        pe_entity_id: The entity resident in the PE jurisdiction (France).
        conflict_year: Fiscal-year label for the conflict id.
    Returns:
        The populated ConflictFlag.
    """
    pe_tax, residence_tax = _compute_taxes(pe, pe_cit_rule, residence_cit_rule)
    mechanism = ReliefMechanism(elimination_rule.parameters.relief_mechanism or "exemption")
    relieved, residual = _resolve(mechanism, pe_tax, residence_tax)
    unrelieved_under_credit = max(pe_tax - residence_tax, Decimal("0"))
    return ConflictFlag(
        conflict_id=f"PE-{pe.entity_id}-{pe.residence_jurisdiction}-{conflict_year}",
        conflict_type=ConflictType.SERVICE_PE_DOUBLE_TAX,
        trigger_flow_ids=pe.trigger_presence_ids,
        entities=[pe.entity_id, pe_entity_id],
        jurisdictions=[pe.residence_jurisdiction, pe.pe_jurisdiction],
        attributed_base_hkd=pe.attributed_income_hkd,
        residence_jurisdiction=pe.residence_jurisdiction,
        pe_jurisdiction=pe.pe_jurisdiction,
        pe_tax_hkd=pe_tax,
        residence_tax_before_relief_hkd=residence_tax,
        relief_mechanism=mechanism,
        relieved_amount_hkd=relieved,
        residual_double_tax_hkd=residual,
        treaty_rule_id=elimination_rule.id,
        treaty_as_of_date=elimination_rule.as_of_date,
        treaty_source_citation=elimination_rule.source_citation,
        credit_method_note=(
            f"Credit method (not applied) would cap relief at HKD {residence_tax}, "
            f"leaving HKD {unrelieved_under_credit} unrelieved."
        ),
        needs_review=True,
    )


def _compute_taxes(
    pe: PeAttribution,
    pe_cit_rule: Rule,
    residence_cit_rule: Rule,
) -> tuple[Decimal, Decimal]:
    """Return (pe_tax, residence_tax) on the PE-attributed income."""
    pe_rate = effective_rate(pe_cit_rule.parameters.rate or Decimal("0"), pe_cit_rule.parameters.surcharge_rate)
    res_rate = effective_rate(
        residence_cit_rule.parameters.rate or Decimal("0"), residence_cit_rule.parameters.surcharge_rate
    )
    return round_amount(pe.attributed_income_hkd * pe_rate), round_amount(pe.attributed_income_hkd * res_rate)


def _resolve(
    mechanism: ReliefMechanism, pe_tax: Decimal, residence_tax: Decimal
) -> tuple[Decimal, Decimal]:
    """Return (relieved_amount, residual_double_tax) for the elimination mechanism."""
    if mechanism is ReliefMechanism.EXEMPTION:
        # Residence state exempts the PE profits entirely — no residual double tax.
        return residence_tax, Decimal("0")
    # Credit method: relief capped at the residence-state tax on the same income.
    relieved = min(pe_tax, residence_tax)
    return relieved, pe_tax - relieved
