"""
Module: models_engine
Layer: common
Purpose: Engine output data models: obligations, thresholds, deadlines, loss carryforward,
    and the top-level EngineRunResult.
Dependencies: pydantic, decimal, datetime, models_entity
Used by: models (re-export), engine, brief, api
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel

from .models_entity import (
    FiscalPeriod,
    JurisdictionCode,
    ObligationType,
)

# ---------------------------------------------------------------------------
# Conflict enums
# ---------------------------------------------------------------------------


class ConflictType(StrEnum):
    """Category of cross-border conflict detected on engine output (Wave 6)."""

    SERVICE_PE_DOUBLE_TAX = "service_pe_double_tax"
    WHT_OVER_WITHHELD = "wht_over_withheld"


class ReliefMechanism(StrEnum):
    """Treaty mechanism that resolves a double-taxation conflict."""

    EXEMPTION = "exemption"
    CREDIT = "credit"


class GroupReliefMechanism(StrEnum):
    """Mechanism by which group-level profit redistribution can occur (W6b)."""

    GROUP_RELIEF = "group_relief"
    ORGANSCHAFT = "organschaft"
    INTEGRATION_FISCALE = "integration_fiscale"
    TRANSFER_PRICING_NOTE = "transfer_pricing_note"

# ---------------------------------------------------------------------------
# Shared citation model (used by engine and AI layers)
# ---------------------------------------------------------------------------


class RuleCitation(BaseModel):
    """Reference to the rule that produced a result, with traceability fields (DEC-004)."""

    rule_id: str
    jurisdiction: JurisdictionCode
    as_of_date: date
    source_citation: str


# ---------------------------------------------------------------------------
# Engine output models
# ---------------------------------------------------------------------------


class ComputationStep(BaseModel):
    """Single auditable step in an engine computation trace."""

    step_name: str
    input_value_hkd: Decimal
    rule_id: str
    rule_as_of_date: date
    result_value_hkd: Decimal
    note: str | None


class ObligationResult(BaseModel):
    """Computed tax obligation for one entity, jurisdiction, and obligation type."""

    obligation_id: str
    entity_id: str
    jurisdiction: JurisdictionCode
    obligation_type: ObligationType
    fiscal_period: FiscalPeriod
    taxable_base_hkd: Decimal
    rate: Decimal
    gross_amount_hkd: Decimal
    treaty_relief_hkd: Decimal
    net_amount_hkd: Decimal
    rule_id: str
    as_of_date: date
    source_citation: str
    treaty_citation: RuleCitation | None
    source_flow_ids: list[str]
    computation_trace: list[ComputationStep]
    needs_review: bool


class ThresholdResult(BaseModel):
    """Result of a threshold check (e.g. Zinsschranke, VAT registration threshold)."""

    entity_id: str
    jurisdiction: JurisdictionCode
    rule_id: str
    threshold_name: str
    threshold_value_hkd: Decimal
    actual_value_hkd: Decimal
    breached: bool
    as_of_date: date
    source_citation: str


class DeadlineResult(BaseModel):
    """Filing and payment deadlines for a given obligation and fiscal period."""

    entity_id: str
    jurisdiction: JurisdictionCode
    obligation_type: ObligationType
    filing_deadline: date
    payment_deadline: date
    rule_id: str
    as_of_date: date
    source_citation: str
    fiscal_period: FiscalPeriod


class LossCarryforwardRecord(BaseModel):
    """Record of loss carryforward applied in the current engine run (DEC-008)."""

    entity_id: str
    jurisdiction: JurisdictionCode
    loss_period: FiscalPeriod
    original_loss_hkd: Decimal
    used_this_period_hkd: Decimal
    remaining_loss_hkd: Decimal
    limitation_applied: bool
    limitation_rule_id: str | None


class ConflictFlag(BaseModel):
    """A detected cross-border conflict and its treaty resolution (DEC-017).

    Models a base claimed by two jurisdictions. For the PE Triangle the residence
    state (Germany) relieves the double tax by EXEMPTION (DE-FR DTA Art.23), so
    ``residual_double_tax_hkd`` is 0 and ``relief_mechanism`` is EXEMPTION. The
    ``credit_method_note`` carries the informational "what a credit method would
    yield" figure without it being an applied liability.
    """

    conflict_id: str
    conflict_type: ConflictType
    trigger_flow_ids: list[str]
    entities: list[str]
    jurisdictions: list[JurisdictionCode]
    attributed_base_hkd: Decimal
    residence_jurisdiction: JurisdictionCode
    pe_jurisdiction: JurisdictionCode
    pe_tax_hkd: Decimal
    residence_tax_before_relief_hkd: Decimal
    relief_mechanism: ReliefMechanism
    relieved_amount_hkd: Decimal
    residual_double_tax_hkd: Decimal
    treaty_rule_id: str
    treaty_as_of_date: date
    treaty_source_citation: str
    credit_method_note: str | None
    needs_review: bool


class GroupReliefOpportunity(BaseModel):
    """A detected opportunity to redistribute pre-tax profit across group members (W6b).

    The engine flags the opportunity and cites the applicable rule; it never recommends
    a transfer amount (DEC-002, DEC-020). The professional reviews and quantifies.
    ``needs_review`` is always True — sign-off is mandatory before acting.
    """

    opportunity_id: str
    income_entity_id: str
    loss_entity_id: str
    income_jurisdiction: JurisdictionCode
    loss_jurisdiction: JurisdictionCode
    available_income_hkd: Decimal
    unused_loss_hkd: Decimal
    relief_mechanism: GroupReliefMechanism
    applicable_rule_id: str
    as_of_date: date
    source_citation: str
    conditions_summary: str
    needs_review: bool = True


class EngineRunResult(BaseModel):
    """Top-level result of one engine run for an entity and fiscal period."""

    run_id: str
    entity_id: str
    fiscal_period: FiscalPeriod
    base_currency: str
    obligations: list[ObligationResult]
    threshold_checks: list[ThresholdResult]
    deadlines: list[DeadlineResult]
    loss_carryforward_applied: list[LossCarryforwardRecord]
    conflicts: list[ConflictFlag]
    group_relief_opportunities: list[GroupReliefOpportunity] = []
    has_unresolved_items: bool
