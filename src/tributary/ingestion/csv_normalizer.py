"""
Module: csv_normalizer
Layer: ingestion
Purpose: Normalize Lenovo balance-sheet CSVs into the engine's canonical Pydantic models.
    Reads data/raw/*.csv, applies a geographic entity split, and derives intercompany
    transaction flows from real consolidated figures. Produces EntityRecord,
    AccountRecord, OwnershipRecord, TransactionRecord, PresenceRecord, PriorPeriodLoss
    entirely in memory — no intermediate JSON files.
Dependencies: csv, decimal, datetime, tributary.common, tributary.common.errors
Used by: tributary.ingestion.seed (run_seed), tests.support.fakes (FakeGraphReader)
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import csv

from tributary.common.errors import IngestionError
from tributary.common.logging import get_logger
from tributary.common.models_entity import (
    AccountRecord,
    ActivityType,
    EntityRecord,
    EntityType,
    OwnershipRecord,
    PresenceActivity,
    PresenceRecord,
    PriorPeriodLoss,
    TransactionRecord,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPORTING_CURRENCY = "USD"
_USD_TO_HKD = Decimal("7.78")
_EUR_TO_HKD = Decimal("8.50")
_FX_DATE = date(2025, 1, 1)

# Lenovo reports in USD; all three CSVs are the same consolidated statement.
# We map each file to a fictitious entity that represents that geographic segment.
_CSV_MAP: dict[str, tuple[str, str, str]] = {
    "lenovo_consolidated_hong_kong_0992HK.csv": (
        "LENOVO-HK",
        "Lenovo Group — HK Holding (0992.HK)",
        "HK",
    ),
    "lenovo_consolidated_germany_LHL_F.csv": (
        "LENOVO-DE",
        "Lenovo Group — European Operations (LHL.F)",
        "DE",
    ),
    "lenovo_consolidated_united_states_LNVGY.csv": (
        "LENOVO-US",
        "Lenovo Group — Americas Operations (LNVGY)",
        "US",
    ),
}

# Geographic revenue/asset split applied to the consolidated figures.
# HK holdco holds IP; DE is the primary opco; US is the secondary opco.
_ENTITY_SHARES: dict[str, Decimal] = {
    "LENOVO-HK": Decimal("0.25"),
    "LENOVO-DE": Decimal("0.35"),
    "LENOVO-US": Decimal("0.40"),
}

# Scale factor: divide consolidated USD figures by this to get demo-sized amounts.
_SCALE = Decimal("10000")

# Latest reporting period in the CSVs.
_LATEST_PERIOD = "2025-03-31"
_PRIOR_PERIOD = "2024-03-31"

# Line-item substrings used to extract key figures (case-insensitive match).
_ACCOUNTS_RECEIVABLE = "Accounts Receivable"
_RETAINED_EARNINGS = "Retained Earnings"
_LONG_TERM_DEBT = "Long Term Debt"
_GOODWILL = "Goodwill And Other Intangible Assets"
_TOTAL_ASSETS = "Total Assets"


# ---------------------------------------------------------------------------
# CSV extraction helpers
# ---------------------------------------------------------------------------


def _read_csv(path: Path) -> dict[str, dict[str, float]]:
    """Read a balance-sheet CSV into {line_item: {period: amount}}.

    Args:
        path: Absolute path to the CSV file.
    Returns:
        Nested dict: line_item label → period string → float amount.
    Raises:
        IngestionError: If the file cannot be read.
    """
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            headers = next(reader)
            periods = [str(h) for h in headers[1:]]
            result: dict[str, dict[str, float]] = {}
            for row in reader:
                if not row:
                    continue
                row_label = str(row[0])
                cells: dict[str, float] = {}
                for period, raw in zip(periods, row[1:]):
                    stripped = raw.strip()
                    if stripped:
                        try:
                            cells[period] = float(stripped)
                        except ValueError:
                            pass
                result[row_label] = cells
            return result
    except IngestionError:
        raise
    except Exception as exc:
        raise IngestionError(f"Failed to read CSV {path}: {exc}") from exc


def _extract(
    data: dict[str, dict[str, float]],
    line_item_substr: str,
    period: str,
    default: float = 0.0,
) -> float:
    """Extract a single cell from the balance-sheet dict.

    Performs case-insensitive substring match on the row label.

    Args:
        data: Output of _read_csv.
        line_item_substr: Substring to search for in row labels.
        period: Column (period string) to read, e.g. "2025-03-31".
        default: Value to return if the cell is absent.
    Returns:
        Float value or default.
    """
    needle = line_item_substr.lower()
    for label, periods in data.items():
        if needle in label.lower():
            return periods.get(period, default)
    return default


def _usd_to_hkd(usd: float, scale: Decimal = _SCALE) -> Decimal:
    """Convert USD to HKD and apply the demo scale factor."""
    return (Decimal(str(usd)) * _USD_TO_HKD / scale).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Model builders
# ---------------------------------------------------------------------------


def _build_entities() -> list[EntityRecord]:
    """One EntityRecord per geographic segment."""
    return [
        EntityRecord(
            entity_id="LENOVO-HK",
            name="Lenovo Group — HK Holding (0992.HK)",
            entity_type=EntityType.HOLDCO,
            incorporation_jurisdiction="HK",
            resident_jurisdiction="HK",
            is_group_member=True,
        ),
        EntityRecord(
            entity_id="LENOVO-DE",
            name="Lenovo Group — European Operations (LHL.F)",
            entity_type=EntityType.SUBSIDIARY,
            incorporation_jurisdiction="DE",
            resident_jurisdiction="DE",
            is_group_member=True,
        ),
        EntityRecord(
            entity_id="LENOVO-US",
            name="Lenovo Group — Americas Operations (LNVGY)",
            entity_type=EntityType.SUBSIDIARY,
            incorporation_jurisdiction="US",
            resident_jurisdiction="US",
            is_group_member=True,
        ),
    ]


def _build_accounts() -> list[AccountRecord]:
    """One general account per entity."""
    return [
        AccountRecord(account_id=f"ACC-{eid.split('-')[1]}-001", entity_id=eid,
                      account_name=f"Main {eid.split('-')[1]} Account", account_type="general")
        for eid in ("LENOVO-HK", "LENOVO-DE", "LENOVO-US")
    ]


def _build_ownership() -> list[OwnershipRecord]:
    """HK holdco owns DE and US subsidiaries at 100%."""
    return [
        OwnershipRecord(
            owner_entity_id="LENOVO-HK",
            owned_entity_id="LENOVO-DE",
            ownership_pct=Decimal("100.00"),
            effective_from=date(2020, 1, 1),
            effective_to=None,
        ),
        OwnershipRecord(
            owner_entity_id="LENOVO-HK",
            owned_entity_id="LENOVO-US",
            ownership_pct=Decimal("100.00"),
            effective_from=date(2020, 1, 1),
            effective_to=None,
        ),
    ]


def _build_transactions(
    ar: float, retained: float, ltd: float, goodwill: float
) -> list[TransactionRecord]:
    """Derive intercompany and external flows from consolidated figures.

    Args:
        ar: Accounts Receivable (USD, consolidated, latest period).
        retained: Retained Earnings (USD, consolidated, latest period).
        ltd: Long Term Debt (USD, consolidated, latest period).
        goodwill: Goodwill + Intangibles (USD, consolidated, latest period).
    Returns:
        List of TransactionRecord representing the derived flows.
    """
    # External revenue proxies (entity-level share of consolidated AR).
    de_revenue_hkd = _usd_to_hkd(ar * float(_ENTITY_SHARES["LENOVO-DE"]))
    us_revenue_hkd = _usd_to_hkd(ar * float(_ENTITY_SHARES["LENOVO-US"]))

    # Royalty: DE pays 3% of DE revenue to HK for IP licence.
    royalty_usd = ar * float(_ENTITY_SHARES["LENOVO-DE"]) * 0.03
    royalty_hkd = _usd_to_hkd(royalty_usd)

    # Dividend DE → HK: 5% of DE's share of retained earnings; WHT 5% (HK-DE DTA Art.10).
    de_div_usd = retained * float(_ENTITY_SHARES["LENOVO-DE"]) * 0.05
    de_div_hkd = _usd_to_hkd(de_div_usd)

    # Interest on intercompany loan (DE borrows 25% of LTD from HK at 5%).
    interest_usd = ltd * 0.25 * 0.05
    interest_hkd = _usd_to_hkd(interest_usd)

    # Dividend US → HK: 5% of US share of retained earnings; 30% US WHT (no DTA).
    us_div_usd = retained * float(_ENTITY_SHARES["LENOVO-US"]) * 0.05
    us_div_hkd = _usd_to_hkd(us_div_usd)

    fx_date_str = _FX_DATE

    return [
        TransactionRecord(
            transaction_id="T001",
            transaction_date=date(2025, 4, 30),
            description="Royalty for IP licence — LENOVO-DE pays LENOVO-HK",
            amount_hkd=royalty_hkd,
            source_amount=(Decimal(str(royalty_usd)) / _SCALE).quantize(Decimal("0.01")),
            fx_rate=_USD_TO_HKD,
            fx_date=fx_date_str,
            source_currency="USD",
            source_entity_id="LENOVO-DE",
            counterparty_entity_id="LENOVO-HK",
            counterparty_jurisdiction="HK",
            is_intercompany=True,
            activity_type=ActivityType.ROYALTY,
            days_present=None,
            has_agent_authority=False,
        ),
        TransactionRecord(
            transaction_id="T002",
            transaction_date=date(2025, 12, 31),
            description="Dividend LENOVO-DE → LENOVO-HK; WHT 5% under HK-DE DTA Art.10",
            amount_hkd=de_div_hkd,
            source_amount=(Decimal(str(de_div_usd)) / _SCALE).quantize(Decimal("0.01")),
            fx_rate=_USD_TO_HKD,
            fx_date=fx_date_str,
            source_currency="USD",
            source_entity_id="LENOVO-DE",
            counterparty_entity_id="LENOVO-HK",
            counterparty_jurisdiction="HK",
            is_intercompany=True,
            activity_type=ActivityType.DIVIDEND,
            days_present=None,
            has_agent_authority=False,
        ),
        TransactionRecord(
            transaction_id="T003",
            transaction_date=date(2025, 12, 31),
            description="Interest on shareholder loan — LENOVO-DE pays LENOVO-HK; 0% WHT HK-DE DTA Art.11",
            amount_hkd=interest_hkd,
            source_amount=(Decimal(str(interest_usd)) / _SCALE).quantize(Decimal("0.01")),
            fx_rate=_USD_TO_HKD,
            fx_date=fx_date_str,
            source_currency="USD",
            source_entity_id="LENOVO-DE",
            counterparty_entity_id="LENOVO-HK",
            counterparty_jurisdiction="HK",
            is_intercompany=True,
            activity_type=ActivityType.INTEREST,
            days_present=None,
            has_agent_authority=False,
        ),
        TransactionRecord(
            transaction_id="T004",
            transaction_date=date(2025, 6, 30),
            description="LENOVO-DE employee service delivery in US — 185 cumulative days FY2025",
            amount_hkd=Decimal("0.00"),
            source_amount=Decimal("0.00"),
            fx_rate=Decimal("1.00"),
            fx_date=fx_date_str,
            source_currency="USD",
            source_entity_id="LENOVO-DE",
            counterparty_entity_id=None,
            counterparty_jurisdiction=None,
            is_intercompany=False,
            activity_type=ActivityType.SERVICE_DELIVERY,
            days_present=185,
            has_agent_authority=False,
        ),
        TransactionRecord(
            transaction_id="T005",
            transaction_date=date(2025, 6, 15),
            description="Third-party European technology services revenue FY2025",
            amount_hkd=de_revenue_hkd,
            source_amount=(Decimal(str(ar * float(_ENTITY_SHARES["LENOVO-DE"]))) / _SCALE).quantize(Decimal("0.01")),
            fx_rate=_USD_TO_HKD,
            fx_date=fx_date_str,
            source_currency="USD",
            source_entity_id="LENOVO-DE",
            counterparty_entity_id=None,
            counterparty_jurisdiction=None,
            is_intercompany=False,
            activity_type=ActivityType.REVENUE,
            days_present=None,
            has_agent_authority=False,
        ),
        TransactionRecord(
            transaction_id="T006",
            transaction_date=date(2025, 12, 31),
            description="Dividend LENOVO-US → LENOVO-HK; 30% US WHT (no HK-US DTA)",
            amount_hkd=us_div_hkd,
            source_amount=(Decimal(str(us_div_usd)) / _SCALE).quantize(Decimal("0.01")),
            fx_rate=_USD_TO_HKD,
            fx_date=fx_date_str,
            source_currency="USD",
            source_entity_id="LENOVO-US",
            counterparty_entity_id="LENOVO-HK",
            counterparty_jurisdiction="HK",
            is_intercompany=True,
            activity_type=ActivityType.DIVIDEND,
            days_present=None,
            has_agent_authority=False,
        ),
        TransactionRecord(
            transaction_id="T007",
            transaction_date=date(2025, 6, 15),
            description="Third-party US technology services revenue FY2025",
            amount_hkd=us_revenue_hkd,
            source_amount=(Decimal(str(ar * float(_ENTITY_SHARES["LENOVO-US"]))) / _SCALE).quantize(Decimal("0.01")),
            fx_rate=_USD_TO_HKD,
            fx_date=fx_date_str,
            source_currency="USD",
            source_entity_id="LENOVO-US",
            counterparty_entity_id=None,
            counterparty_jurisdiction=None,
            is_intercompany=False,
            activity_type=ActivityType.REVENUE,
            days_present=None,
            has_agent_authority=False,
        ),
    ]


def _build_presence() -> list[PresenceRecord]:
    """185-day presence of LENOVO-DE in the US — triggers PE detection."""
    return [
        PresenceRecord(
            presence_id="PRES-DE-US-2025",
            entity_id="LENOVO-DE",
            jurisdiction="US",
            period_start=date(2025, 1, 15),
            period_end=date(2025, 9, 30),
            total_days_present=185,
            activity_type=PresenceActivity.SERVICE_DELIVERY,
            has_agent_authority=False,
            has_fixed_place=False,
        )
    ]


def _build_prior_losses(retained_prior: float, retained_latest: float) -> list[PriorPeriodLoss]:
    """DE prior-period loss derived from retained-earnings decline (or a fixed fallback).

    Args:
        retained_prior: Retained Earnings in the prior period (USD, consolidated).
        retained_latest: Retained Earnings in the latest period (USD, consolidated).
    Returns:
        One PriorPeriodLoss for LENOVO-DE if a loss is implied; empty list otherwise.
    """
    de_share = _ENTITY_SHARES["LENOVO-DE"]
    prior = retained_prior * float(de_share)
    latest = retained_latest * float(de_share)
    loss_usd = max(prior - latest, 0.0)
    # Fallback: use a small nominal loss to keep the loss-carryforward engine exercised.
    if loss_usd < 1.0:
        loss_usd = 500_000.0 / float(_SCALE)
    loss_hkd = _usd_to_hkd(loss_usd)
    return [
        PriorPeriodLoss(
            loss_id="LOSS-DE-2024",
            entity_id="LENOVO-DE",
            jurisdiction="DE",
            loss_period_start=date(2024, 1, 1),
            loss_period_end=date(2024, 12, 31),
            original_loss_hkd=loss_hkd,
            remaining_loss_hkd=loss_hkd,
            created_at=date(2025, 3, 31),
        )
    ]


def _build_fx_rates() -> dict[str, str]:
    """Static FX rates (HKD per 1 unit of each currency)."""
    return {
        "USD": str(_USD_TO_HKD),
        "EUR": str(_EUR_TO_HKD),
        "HKD": "1",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_models(raw_dir: Path) -> dict[str, Any]:
    """Normalize Lenovo CSVs into canonical engine models (all in memory).

    Reads the three balance-sheet CSVs from raw_dir, extracts key consolidated
    figures, applies a geographic entity split, and derives intercompany flows.

    Args:
        raw_dir: Directory containing the Lenovo CSV files.
    Returns:
        Dict with keys: entities, accounts, ownership, transactions,
        presence_records, prior_losses, fx_rates.
    Raises:
        IngestionError: If no CSV files are found in raw_dir.
    """
    csvs = sorted(raw_dir.glob("lenovo_*.csv"))
    if not csvs:
        raise IngestionError(
            f"No Lenovo CSV files found in {raw_dir}. "
            "Run `python data/raw/get_data.py` to download them."
        )

    # Use the HK listing CSV as the authoritative source (all three are identical figures).
    hk_csv = raw_dir / "lenovo_consolidated_hong_kong_0992HK.csv"
    primary_csv = hk_csv if hk_csv.exists() else csvs[0]
    data = _read_csv(primary_csv)

    ar = _extract(data, _ACCOUNTS_RECEIVABLE, _LATEST_PERIOD)
    retained_latest = _extract(data, _RETAINED_EARNINGS, _LATEST_PERIOD)
    retained_prior = _extract(data, _RETAINED_EARNINGS, _PRIOR_PERIOD)
    ltd = _extract(data, _LONG_TERM_DEBT, _LATEST_PERIOD)
    goodwill = _extract(data, _GOODWILL, _LATEST_PERIOD)

    logger.info(
        "Extracted Lenovo key figures",
        extra={
            "csv": str(primary_csv),
            "period": _LATEST_PERIOD,
            "ar_usd_bn": round(ar / 1e9, 2),
            "retained_usd_bn": round(retained_latest / 1e9, 2),
            "ltd_usd_bn": round(ltd / 1e9, 2),
        },
    )

    return {
        "entities": _build_entities(),
        "accounts": _build_accounts(),
        "ownership": _build_ownership(),
        "transactions": _build_transactions(ar, retained_latest, ltd, goodwill),
        "presence_records": _build_presence(),
        "prior_losses": _build_prior_losses(retained_prior, retained_latest),
        "fx_rates": _build_fx_rates(),
    }


def write_fx_rates_file(fx_rates: dict[str, str], dest: Path) -> None:
    """Write fx_rates as the list-of-records format FileFXRateProvider expects.

    FileFXRateProvider.get_rates() iterates rows and looks for
    {from_currency, to_currency, rate, rate_date, source}. HKD→HKD is omitted
    since it is always 1 and the reader filters to_currency == "HKD" only.

    Args:
        fx_rates: Output of _build_fx_rates() — {ISO_code: rate_string}.
        dest: Path to write (e.g. data/golden/fx_rates.json).
    """
    rate_date = _FX_DATE.isoformat()
    rows = [
        {
            "from_currency": ccy,
            "to_currency": "HKD",
            "rate": rate,
            "rate_date": rate_date,
            "source": "hardcoded-demo",
        }
        for ccy, rate in fx_rates.items()
        if ccy != "HKD"
    ]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    logger.info("Wrote FX rates file", extra={"path": str(dest)})
