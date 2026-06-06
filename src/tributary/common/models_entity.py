"""
Module: models_entity
Layer: common
Purpose: Entity, ownership, account, transaction, presence, and period data models.
Dependencies: pydantic, decimal, datetime
Used by: models (re-export), graph, engine, ingestion, api — all layers
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Scalar type alias
# ---------------------------------------------------------------------------

JurisdictionCode = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
"""Two-letter uppercase ISO country code, e.g. 'HK', 'DE', 'FR'."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ConfidenceLevel(str, Enum):
    """AI confidence level for classification and attribution outputs."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    ABSTAIN = "ABSTAIN"


class FlowNature(str, Enum):
    """Semantic nature of a transaction flow as classified by the AI layer.

    This is the AI's *classification output* vocabulary. The raw GL hint that
    rides on a transaction is ``ActivityType`` (see below); the two vocabularies
    are related but distinct (DEC-015).
    """

    REVENUE = "revenue"
    EXPENSE = "expense"
    INTERCOMPANY = "intercompany"
    CAPITAL = "capital"
    LOAN = "loan"
    ROYALTY = "royalty"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    MANAGEMENT_FEE = "management_fee"
    OTHER = "other"


class ActivityType(str, Enum):
    """Raw activity hint carried by a transaction from the GL/bank export.

    This is the deterministic engine's *dispatch* vocabulary — the engine routes
    a flow to a tax-type sub-engine by ``ActivityType`` + the entity's role
    (payer vs payee). Typed to fail fast on typos/case errors (DEC-015).
    """

    REVENUE = "revenue"
    GOODS_SALE = "goods_sale"
    SERVICE_DELIVERY = "service_delivery"
    ROYALTY = "royalty"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    MANAGEMENT_FEE = "management_fee"
    LOAN_PRINCIPAL = "loan_principal"
    OTHER = "other"


class PresenceActivity(str, Enum):
    """Kind of activity an entity's employees/agents perform while present."""

    SERVICE_DELIVERY = "service_delivery"
    SALES = "sales"
    MANAGEMENT = "management"
    CONSTRUCTION = "construction"


class ObligationType(str, Enum):
    """Type of tax obligation computed by the deterministic engine."""

    CIT = "cit"
    VAT = "vat"
    WHT = "wht"
    TRADE_TAX = "trade_tax"
    STAMP_DUTY = "stamp_duty"


class EntityType(str, Enum):
    """Legal form of a Tributary entity node."""

    HOLDCO = "holdco"
    SUBSIDIARY = "subsidiary"
    BRANCH = "branch"
    PE = "pe"


# ---------------------------------------------------------------------------
# Entity / structure models
# ---------------------------------------------------------------------------


class EntityRecord(BaseModel):
    """Canonical representation of a group entity stored in the graph."""

    entity_id: str
    name: str
    entity_type: EntityType
    incorporation_jurisdiction: JurisdictionCode
    resident_jurisdiction: JurisdictionCode
    is_group_member: bool


class OwnershipRecord(BaseModel):
    """Direct ownership relationship between two entities."""

    owner_entity_id: str
    owned_entity_id: str
    ownership_pct: Decimal
    effective_from: date
    effective_to: date | None


class AccountRecord(BaseModel):
    """General-ledger account linked to an entity."""

    account_id: str
    entity_id: str
    account_name: str
    account_type: str


class TransactionRecord(BaseModel):
    """Normalised GL/bank transaction after ingestion and FX conversion.

    Canonical direction convention (DEC-016):
        - Intercompany flow: ``source_entity_id`` is the PAYER, ``counterparty_entity_id``
          is the PAYEE.
        - Third-party inbound revenue: ``source_entity_id`` is the receiving group
          entity and ``counterparty_entity_id`` is None.
    The engine derives income vs expense from this convention plus ``activity_type``.
    """

    transaction_id: str
    transaction_date: date
    description: str
    amount_hkd: Decimal
    source_amount: Decimal
    fx_rate: Decimal
    fx_date: date
    source_currency: str
    source_entity_id: str
    counterparty_entity_id: str | None
    counterparty_jurisdiction: JurisdictionCode | None
    is_intercompany: bool
    activity_type: ActivityType | None
    days_present: int | None
    has_agent_authority: bool


class PresenceRecord(BaseModel):
    """Physical or economic presence of an entity in a jurisdiction (PE analysis)."""

    presence_id: str
    entity_id: str
    jurisdiction: JurisdictionCode
    period_start: date
    period_end: date
    total_days_present: int
    activity_type: PresenceActivity
    has_agent_authority: bool
    has_fixed_place: bool


class PriorPeriodLoss(BaseModel):
    """Loss carryforward balance for a prior fiscal period (DEC-008)."""

    loss_id: str
    entity_id: str
    jurisdiction: JurisdictionCode
    loss_period_start: date
    loss_period_end: date
    original_loss_hkd: Decimal
    remaining_loss_hkd: Decimal
    created_at: date


class CounterpartyRecord(BaseModel):
    """External or related-party counterparty referenced in transactions."""

    counterparty_id: str
    name: str
    jurisdiction: JurisdictionCode | None
    is_related_party: bool


# ---------------------------------------------------------------------------
# Period models
# ---------------------------------------------------------------------------


class FiscalPeriod(BaseModel):
    """Start and end dates of a fiscal period for a given jurisdiction."""

    jurisdiction: JurisdictionCode
    start_date: date
    end_date: date


class FiscalCalendar(BaseModel):
    """Day/month anchor that defines the fiscal year start for a jurisdiction."""

    jurisdiction: JurisdictionCode
    period_start_month: Annotated[int, Field(ge=1, le=12)]
    period_start_day: Annotated[int, Field(ge=1, le=31)]
