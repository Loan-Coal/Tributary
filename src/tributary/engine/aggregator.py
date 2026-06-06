"""
Module: aggregator
Layer: engine
Purpose: Assemble one entity's CIT income/expense base and its outbound-payment list from the
    transactions it is involved in. Income vs expense is derived from the DEC-016 direction
    convention (payer vs payee) + activity_type; income exemptions come from the rule pack.
    Pure deterministic — no AI calls.
Dependencies: decimal, tributary.common, tributary.rules
Used by: engine.runner, engine tests
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from tributary.common.models import (
    ActivityType,
    FiscalPeriod,
    GraphReader,
    JurisdictionCode,
    TransactionRecord,
)
from tributary.rules.models import Rule, RuleCategory, RulePackLoader

# Generic accounting classification (not jurisdiction-specific — DEC-006 compatible).
DEDUCTIBLE_EXPENSE_ACTIVITIES: frozenset[ActivityType] = frozenset(
    {ActivityType.ROYALTY, ActivityType.INTEREST, ActivityType.MANAGEMENT_FEE}
)
WHT_BEARING_ACTIVITIES: frozenset[ActivityType] = frozenset(
    {ActivityType.ROYALTY, ActivityType.INTEREST, ActivityType.MANAGEMENT_FEE, ActivityType.DIVIDEND}
)
THIRD_PARTY_INCOME_ACTIVITIES: frozenset[ActivityType] = frozenset(
    {ActivityType.REVENUE, ActivityType.GOODS_SALE, ActivityType.SERVICE_DELIVERY}
)
_EXEMPTION_CATEGORIES = (RuleCategory.PARTICIPATION_EXEMPTION, RuleCategory.INCOME_EXEMPTION)


class OutboundPayment(BaseModel):
    """One cross-border payment made by the entity — a potential WHT obligation."""

    flow_id: str
    activity: ActivityType
    gross_hkd: Decimal
    payer_entity_id: str
    payer_jurisdiction: JurisdictionCode
    payee_entity_id: str
    payee_jurisdiction: JurisdictionCode


class EntityBase(BaseModel):
    """Aggregated CIT inputs for one entity and period (pre loss offset, pre PE adjustment)."""

    entity_id: str
    jurisdiction: JurisdictionCode
    period: FiscalPeriod
    third_party_income_hkd: Decimal
    ic_income_taxable_hkd: Decimal
    deductible_expense_hkd: Decimal
    interest_expense_hkd: Decimal
    net_income_hkd: Decimal
    income_flow_ids: list[str]
    expense_flow_ids: list[str]
    outbound_payments: list[OutboundPayment]


def exemption_for(
    loader: RulePackLoader, jurisdiction: JurisdictionCode, activity: ActivityType
) -> tuple[Decimal, Rule | None]:
    """Return the income-exemption fraction for an activity in a jurisdiction.

    Args:
        loader: Rule-pack loader.
        jurisdiction: The taxing jurisdiction.
        activity: The income activity type.
    Returns:
        (exempt_fraction, rule) — (0, None) if no exemption applies.
    """
    for category in _EXEMPTION_CATEGORIES:
        for rule in loader.get_rules(jurisdiction, category):
            if rule.parameters.applies_to_activity == activity:
                return rule.parameters.exempt_fraction or Decimal("0"), rule
    return Decimal("0"), None


def _is_payee(entity_id: str, txn: TransactionRecord) -> bool:
    return txn.counterparty_entity_id == entity_id


def _is_third_party_revenue(entity_id: str, txn: TransactionRecord) -> bool:
    return (
        txn.source_entity_id == entity_id
        and txn.counterparty_entity_id is None
        and txn.activity_type in THIRD_PARTY_INCOME_ACTIVITIES
    )


def aggregate_entity(
    reader: GraphReader,
    loader: RulePackLoader,
    entity_id: str,
    jurisdiction: JurisdictionCode,
    period: FiscalPeriod,
) -> EntityBase:
    """Aggregate one entity's CIT base inputs and outbound payments for a period.

    Args:
        reader: Graph reader (returns the entity's involved transactions).
        loader: Rule-pack loader (income exemptions).
        entity_id: The entity to aggregate.
        jurisdiction: The entity's residence (taxing) jurisdiction.
        period: The fiscal period.
    Returns:
        The aggregated EntityBase (net income is pre-loss, pre-PE).
    """
    transactions = reader.get_transactions_involving_entity(
        entity_id, period.start_date, period.end_date
    )
    acc = _Accumulator(loader, entity_id, jurisdiction)
    for txn in transactions:
        if txn.days_present is not None:
            continue  # presence marker — handled by the PE engine, not the tax base
        acc.add(txn)
    net = acc.third_party_income + acc.ic_income_taxable - acc.deductible_expense
    return EntityBase(
        entity_id=entity_id,
        jurisdiction=jurisdiction,
        period=period,
        third_party_income_hkd=acc.third_party_income,
        ic_income_taxable_hkd=acc.ic_income_taxable,
        deductible_expense_hkd=acc.deductible_expense,
        interest_expense_hkd=acc.interest_expense,
        net_income_hkd=net,
        income_flow_ids=acc.income_flow_ids,
        expense_flow_ids=acc.expense_flow_ids,
        outbound_payments=acc.outbound_payments,
    )


class _Accumulator:
    """Mutable per-entity tally used only inside aggregate_entity (keeps it under 40 lines)."""

    def __init__(self, loader: RulePackLoader, entity_id: str, jurisdiction: JurisdictionCode) -> None:
        self._loader = loader
        self._entity_id = entity_id
        self._jurisdiction = jurisdiction
        self.third_party_income = Decimal("0")
        self.ic_income_taxable = Decimal("0")
        self.deductible_expense = Decimal("0")
        self.interest_expense = Decimal("0")
        self.income_flow_ids: list[str] = []
        self.expense_flow_ids: list[str] = []
        self.outbound_payments: list[OutboundPayment] = []

    def add(self, txn: TransactionRecord) -> None:
        """Route one transaction into income, expense, or outbound-payment tallies."""
        if _is_third_party_revenue(self._entity_id, txn):
            self.third_party_income += txn.amount_hkd
            self.income_flow_ids.append(txn.transaction_id)
        elif _is_payee(self._entity_id, txn):
            self._add_ic_income(txn)
        elif txn.source_entity_id == self._entity_id:
            self._add_outflow(txn)

    def _add_ic_income(self, txn: TransactionRecord) -> None:
        fraction, _ = exemption_for(self._loader, self._jurisdiction, txn.activity_type)
        self.ic_income_taxable += txn.amount_hkd * (Decimal("1") - fraction)
        self.income_flow_ids.append(txn.transaction_id)

    def _add_outflow(self, txn: TransactionRecord) -> None:
        if txn.activity_type in DEDUCTIBLE_EXPENSE_ACTIVITIES:
            self.deductible_expense += txn.amount_hkd
            self.expense_flow_ids.append(txn.transaction_id)
            if txn.activity_type is ActivityType.INTEREST:
                self.interest_expense += txn.amount_hkd
        if txn.activity_type in WHT_BEARING_ACTIVITIES and txn.counterparty_entity_id is not None:
            self._add_outbound_payment(txn)

    def _add_outbound_payment(self, txn: TransactionRecord) -> None:
        if txn.counterparty_jurisdiction is None or txn.counterparty_jurisdiction == self._jurisdiction:
            return
        self.outbound_payments.append(
            OutboundPayment(
                flow_id=txn.transaction_id,
                activity=txn.activity_type,
                gross_hkd=txn.amount_hkd,
                payer_entity_id=self._entity_id,
                payer_jurisdiction=self._jurisdiction,
                payee_entity_id=txn.counterparty_entity_id,
                payee_jurisdiction=txn.counterparty_jurisdiction,
            )
        )
