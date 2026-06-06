"""
Module: models
Layer: rules
Purpose: Rule-pack data models and the RulePackLoader protocol. A Rule carries a typed
    parameter block and a country-agnostic `category` semantic key so the engine looks up
    rules by meaning (e.g. CIT_RATE) without ever hardcoding a jurisdiction or rule id
    (DEC-006, DEC-019).
Dependencies: pydantic, datetime, decimal, enum, tributary.common.models
Used by: rules.loader, engine (depends on RulePackLoader protocol + Rule/RulePack models)
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, model_validator

from tributary.common.models import ActivityType, FiscalCalendar, JurisdictionCode


class RuleType(str, Enum):
    """Structural kind of a rule (mirrors the rule-pack contract `type` field)."""

    RATE = "rate"
    THRESHOLD = "threshold"
    OBLIGATION_TRIGGER = "obligation_trigger"
    DEADLINE = "deadline"
    TREATY = "treaty"
    SOURCE_RULE = "source_rule"
    EXEMPTION = "exemption"
    LOSS_RELIEF = "loss_relief"


class RuleCategory(str, Enum):
    """Country-agnostic semantic key the engine uses to find a rule by meaning.

    The engine asks ``get_rules(jurisdiction, category)`` — never by jurisdiction-specific
    id — so a new country is a new JSON pack with the same categories (DEC-006).
    """

    CIT_RATE = "cit_rate"
    TRADE_TAX_RATE = "trade_tax_rate"
    WHT_DIVIDEND = "wht_dividend"
    WHT_INTEREST = "wht_interest"
    WHT_ROYALTY = "wht_royalty"
    WHT_MANAGEMENT_FEE = "wht_management_fee"
    PARTICIPATION_EXEMPTION = "participation_exemption"
    LOSS_RELIEF = "loss_relief"
    VAT_THRESHOLD = "vat_threshold"
    PE_THRESHOLD = "pe_threshold"
    INTEREST_BARRIER = "interest_barrier"
    CIT_DEADLINE = "cit_deadline"
    TRADE_TAX_DEADLINE = "trade_tax_deadline"
    VAT_FILING = "vat_filing"
    INCOME_EXEMPTION = "income_exemption"
    TREATY_DIVIDEND = "treaty_dividend"
    TREATY_INTEREST = "treaty_interest"
    TREATY_ROYALTY = "treaty_royalty"
    TREATY_PE = "treaty_pe"
    TREATY_ELIMINATION = "treaty_elimination"


class RuleParameters(BaseModel):
    """Typed parameter block for a rule. All fields optional; a rule populates the subset
    relevant to its category. Modelled (not raw dict) to honour the no-dict-at-boundary rule.
    """

    rate: Decimal | None = None
    surcharge_rate: Decimal | None = None
    domestic_rate: Decimal | None = None
    treaty_rate: Decimal | None = None
    threshold_hkd: Decimal | None = None
    exempt_fraction: Decimal | None = None
    deemed_expense_fraction: Decimal | None = None
    applies_to_activity: ActivityType | None = None
    min_holding_pct: Decimal | None = None
    min_holding_months: int | None = None
    requires_eu: bool | None = None
    day_count: int | None = None
    period_months: int | None = None
    attribution_pct: Decimal | None = None
    cap_fraction: Decimal | None = None
    de_minimis_hkd: Decimal | None = None
    filing_month: int | None = None
    filing_day: int | None = None
    payment_offset_days: int | None = None
    filing_frequency: str | None = None
    unlimited: bool | None = None
    relief_mechanism: str | None = None  # "exemption" | "credit" (treaty_elimination rules)


class Rule(BaseModel):
    """One rule-pack entry (the load-bearing contract record)."""

    id: str
    jurisdiction: JurisdictionCode
    type: RuleType
    category: RuleCategory
    parameters: RuleParameters
    as_of_date: date
    source_citation: str

    @model_validator(mode="after")
    def _require_params_for_category(self) -> "Rule":
        """Fail fast if a rule omits the parameter its category requires."""
        required: dict[RuleCategory, str] = {
            RuleCategory.CIT_RATE: "rate",
            RuleCategory.TRADE_TAX_RATE: "rate",
            RuleCategory.VAT_THRESHOLD: "threshold_hkd",
            RuleCategory.PE_THRESHOLD: "day_count",
            RuleCategory.TREATY_PE: "day_count",
            RuleCategory.INTEREST_BARRIER: "cap_fraction",
            RuleCategory.LOSS_RELIEF: "cap_fraction",
            RuleCategory.PARTICIPATION_EXEMPTION: "exempt_fraction",
            RuleCategory.INCOME_EXEMPTION: "exempt_fraction",
        }
        field_name = required.get(self.category)
        if field_name is not None and getattr(self.parameters, field_name) is None:
            raise ValueError(
                f"Rule {self.id} ({self.category.value}) requires parameter '{field_name}'"
            )
        return self


class RulePack(BaseModel):
    """A jurisdiction's full rule set plus its fiscal calendar."""

    jurisdiction: JurisdictionCode
    fiscal_calendar: FiscalCalendar
    rules: list[Rule]


class TreatyPack(BaseModel):
    """A bilateral treaty rule set between two jurisdictions."""

    jurisdiction_a: JurisdictionCode
    jurisdiction_b: JurisdictionCode
    rules: list[Rule]


@runtime_checkable
class RulePackLoader(Protocol):
    """Source-agnostic loader the engine depends on. Demo packs and licensed feeds both
    implement this — production swaps the source, not the engine (DEC-001)."""

    def get_rules(
        self, jurisdiction: JurisdictionCode, category: RuleCategory
    ) -> list[Rule]:
        """Return all rules for a jurisdiction matching a semantic category.

        Args:
            jurisdiction: ISO-3166 alpha-2 code.
            category: The country-agnostic semantic key.
        Returns:
            Matching rules (empty if none — the engine treats absence as "not applicable").
        Raises:
            RulePackError: If the jurisdiction pack is missing or malformed.
        """
        ...

    def get_rule(self, jurisdiction: JurisdictionCode, rule_id: str) -> Rule:
        """Return one rule by id.

        Raises:
            RulePackError: If the rule or pack is not found.
        """
        ...

    def get_treaty_rules(
        self, jurisdiction_a: JurisdictionCode, jurisdiction_b: JurisdictionCode
    ) -> list[Rule]:
        """Return treaty rules between two jurisdictions (order-independent).

        Returns:
            Treaty rules, or empty list if no treaty pack exists.
        """
        ...

    def get_fiscal_calendar(self, jurisdiction: JurisdictionCode) -> FiscalCalendar:
        """Return the fiscal calendar for a jurisdiction.

        Raises:
            RulePackError: If the jurisdiction pack is missing.
        """
        ...
