# common/models.py
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel
from datetime import date


class Jurisdiction(BaseModel):
    id: str                        # "HK" | "DE" | "US" | "SG"
    name: str
    tax_regime_notes: str


class Entity(BaseModel):
    id: str
    name: str
    type: Literal["holdco", "subsidiary", "branch"]
    jurisdiction_id: str


class Ownership(BaseModel):
    owner_id: str
    owned_id: str
    pct: float                     # 0.0–1.0, e.g. 0.80 = 80%


class Account(BaseModel):
    id: str
    entity_id: str
    currency: str                  # ISO 4217, e.g. "HKD"
    bank_name: str


class Counterparty(BaseModel):
    id: str
    name: str
    location: str
    jurisdiction_id: str


class Transaction(BaseModel):
    id: str
    account_id: str
    counterparty_id: str
    amount_original: float
    currency_original: str
    amount_base: float             # always converted to USD
    currency_base: str             # always "USD"
    fx_rate: float                 # rate used for conversion
    fx_date: date                  # the specific rate date — tax law cares about this
    date: date                     # transaction date
    description: str
    flow_type: Optional[str] = None  # None until AI sets it in Phase 4


class FinancialLineItem(BaseModel):
    """A single balance-sheet line item for one entity in one reporting period.

    Balance-sheet data is not a transaction (it has no account/counterparty), so
    it is modelled as its own node type linked to the reporting Entity.
    """
    id: str                        # f"fli_{entity_id}_{period}_{line_item_slug}"
    entity_id: str
    period: str                    # reporting date, e.g. "2025-03-31"
    line_item: str                 # e.g. "Total Debt"
    amount: float
    currency: str                  # ISO 4217, e.g. "USD"
    statement_type: str = "balance_sheet"
    source: str                    # provenance, e.g. ticker "0992.HK"


# ── Derived — written by the engine (Phase 3+), never by ingestion ──────────

class Obligation(BaseModel):
    id: str
    entity_id: str
    jurisdiction_id: str
    period: str                    # e.g. "FY2024"
    obligation_type: str           # e.g. "profits_tax_filing"
    confidence: float              # 0–1, from AI in Phase 4
    source_rule_ids: list[str]     # rule pack IDs that triggered this