from datetime import date
from pathlib import Path
from typing import Any

from common.models import (
    Entity, Ownership, Account, Counterparty, Transaction
)


def _parse_date(val: Any) -> date:
    if isinstance(val, date):
        return val
    if not val:
        return date.today()
    s = str(val)
    try:
        # expect ISO-like date strings
        return date.fromisoformat(s)
    except Exception:
        # fallback: try year-only
        try:
            return date(int(s), 1, 1)
        except Exception:
            return date.today()


def normalize_entity(r: dict) -> Entity:
    return Entity(
        id=r.get('id'),
        name=r.get('name'),
        type=r.get('type'),
        jurisdiction_id=r.get('jurisdiction_id')
    )


def normalize_ownership(r: dict) -> Ownership:
    return Ownership(
        owner_id=r.get('owner_id') or r.get('owner'),
        owned_id=r.get('owned_id') or r.get('owned'),
        pct=float(r.get('pct', 100) or 100)
    )


def normalize_account(r: dict) -> Account:
    return Account(
        id=r.get('id'),
        entity_id=r.get('entity_id'),
        currency=r.get('currency') or r.get('currency_original') or 'USD',
        bank_name=r.get('bank_name') or ''
    )


def normalize_counterparty(r: dict) -> Counterparty:
    return Counterparty(
        id=r.get('id'),
        name=r.get('name'),
        location=r.get('location') or '',
        jurisdiction_id=r.get('jurisdiction_id')
    )


def normalize_transaction(r: dict) -> Transaction:
    # Accept both pipeline-normalized rows and legacy ingestion shapes
    amt = r.get('amount') or r.get('amount_original') or r.get('amount_original') or 0
    try:
        amt_f = float(amt)
    except Exception:
        amt_f = 0.0

    currency = r.get('currency') or r.get('currency_original') or 'USD'

    tx_date = _parse_date(r.get('date') or r.get('tx_date') or r.get('time_period'))
    fx_date = _parse_date(r.get('fx_date') or r.get('date'))

    return Transaction(
        id=r.get('id'),
        account_id=r.get('account_id'),
        counterparty_id=r.get('counterparty_id'),
        amount_original=amt_f,
        currency_original=currency,
        amount_base=amt_f,
        currency_base='USD',
        fx_rate=float(r.get('fx_rate') or 1.0),
        fx_date=fx_date,
        date=tx_date,
        description=r.get('description') or r.get('desc') or '',
        flow_type=r.get('flow_direction') or r.get('flow_type'),
        gl_code=r.get('gl_code'),
        data_source=r.get('data_source'),
        record_type=r.get('record_type')
    )
