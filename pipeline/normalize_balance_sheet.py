"""
Module: normalize_balance_sheet
Layer: ingestion (pipeline)
Purpose: Normalize Lenovo per-country balance-sheet CSVs into graph-ready models
         (jurisdictions, listing entities, and per-period financial line items).
Dependencies: common.models
Used by: seed.seed
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from common.models import Entity, FinancialLineItem, Jurisdiction

REPORTING_CURRENCY = "USD"
STATEMENT_TYPE = "balance_sheet"
RAW_DIR = Path("data/raw")


class Listing(NamedTuple):
    """Static metadata describing one country listing of the same company."""
    file_name: str
    ticker: str
    entity_id: str
    entity_name: str
    jurisdiction_id: str
    jurisdiction_name: str
    tax_regime_notes: str


# Same company (Lenovo Group), three country listings. The balance sheets are
# numerically identical (one consolidated statement); the jurisdiction differs.
LISTINGS = [
    Listing("lenovo_consolidated_hong_kong_0992HK.csv", "0992.HK",
            "lenovo_hk", "Lenovo Group Limited (HK listing 0992.HK)",
            "HK", "Hong Kong",
            "Territorial; profits tax on HK-sourced income; no VAT."),
    Listing("lenovo_consolidated_united_states_LNVGY.csv", "LNVGY",
            "lenovo_us", "Lenovo Group Limited (US ADR LNVGY)",
            "US", "United States",
            "Worldwide taxation; federal + state; no federal VAT."),
    Listing("lenovo_consolidated_germany_LHL_F.csv", "LHL.F",
            "lenovo_de", "Lenovo Group Limited (DE listing LHL.F)",
            "DE", "Germany",
            "Worldwide-ish; VAT regime; dense treaty network."),
]


def _slug(text: str) -> str:
    """Build a lowercase, underscore-delimited id fragment from a label.

    Args:
        text: Arbitrary human label, e.g. "Total Debt".
    Returns:
        Sanitized fragment, e.g. "total_debt".
    """
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def jurisdictions() -> list[Jurisdiction]:
    """Distinct jurisdictions referenced by the configured listings.

    Returns:
        One Jurisdiction per unique jurisdiction id.
    """
    seen: dict[str, Jurisdiction] = {}
    for listing in LISTINGS:
        seen.setdefault(listing.jurisdiction_id, Jurisdiction(
            id=listing.jurisdiction_id,
            name=listing.jurisdiction_name,
            tax_regime_notes=listing.tax_regime_notes,
        ))
    return list(seen.values())


def entities() -> list[Entity]:
    """One holding-company Entity per country listing.

    Returns:
        Entity records resident in their respective jurisdictions.
    """
    return [
        Entity(id=l.entity_id, name=l.entity_name,
               type="holdco", jurisdiction_id=l.jurisdiction_id)
        for l in LISTINGS
    ]


def _line_items_for(listing: Listing, raw_dir: Path) -> list[FinancialLineItem]:
    """Parse one listing's CSV into per-period FinancialLineItem records.

    Args:
        listing: The listing metadata to parse.
        raw_dir: Directory containing the raw CSV.
    Returns:
        One FinancialLineItem per (line item, period) cell that has a value.
    """
    df = pd.read_csv(raw_dir / listing.file_name, index_col=0)
    items: list[FinancialLineItem] = []
    for line_item, row in df.iterrows():
        for period, amount in row.items():
            if pd.isna(amount):
                continue
            items.append(FinancialLineItem(
                id=f"fli_{listing.entity_id}_{period}_{_slug(str(line_item))}",
                entity_id=listing.entity_id,
                period=str(period),
                line_item=str(line_item),
                amount=float(amount),
                currency=REPORTING_CURRENCY,
                statement_type=STATEMENT_TYPE,
                source=listing.ticker,
            ))
    return items


def line_items(raw_dir: Path = RAW_DIR) -> list[FinancialLineItem]:
    """All balance-sheet line items across every configured listing present on disk.

    Args:
        raw_dir: Directory containing the raw balance-sheet CSVs.
    Returns:
        Flattened list of FinancialLineItem records; listings whose CSV is
        missing are skipped.
    """
    out: list[FinancialLineItem] = []
    for listing in LISTINGS:
        if (raw_dir / listing.file_name).exists():
            out.extend(_line_items_for(listing, raw_dir))
    return out
