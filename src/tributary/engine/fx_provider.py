"""
Module: fx_provider
Layer: engine
Purpose: FX rate providers — static file and live frankfurter.app (ECB-sourced).
Dependencies: json, datetime, decimal, pathlib; httpx (optional, only for live provider)
Used by: engine.cli (_load_fx_map)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

_FRANKFURTER_URL = "https://api.frankfurter.app/latest"


class FXRateProvider(Protocol):
    """Return HKD per one unit of each requested foreign currency."""

    def get_rates(self, currencies: list[str]) -> dict[str, Decimal]:
        """Fetch or load rates for the given currency codes.

        Args:
            currencies: ISO 4217 codes (e.g. ["EUR", "USD"]).
        Returns:
            Dict of {currency: HKD_per_unit}. Missing currencies are omitted.
        """
        ...

    def rate_source_label(self) -> str:
        """Human-readable label for the rate source, used in brief headers."""
        ...


class FileFXRateProvider:
    """Load FX rates from the static golden-scenario JSON file."""

    def __init__(self, path: Path) -> None:
        """Args:
            path: Path to fx_rates.json containing [{from_currency, to_currency, rate, rate_date, source}].
        """
        self._path = path

    def get_rates(self, currencies: list[str]) -> dict[str, Decimal]:
        """Read rates from the file, returning only HKD-target pairs.

        Args:
            currencies: Currency codes to filter for.
        Returns:
            Dict mapping foreign currency code → Decimal HKD rate.
        """
        if not self._path.exists():
            logger.warning("FX rates file not found", extra={"path": str(self._path)})
            return {}
        rows = json.loads(self._path.read_text(encoding="utf-8"))
        result: dict[str, Decimal] = {}
        for row in rows:
            if row.get("to_currency") == "HKD" and row.get("from_currency") in currencies:
                result[row["from_currency"]] = Decimal(str(row["rate"]))
        return result

    def rate_source_label(self) -> str:
        """Return source description including the rate date from the file."""
        if not self._path.exists():
            return "static file (not found)"
        rows = json.loads(self._path.read_text(encoding="utf-8"))
        if rows:
            return f"ECB/HKMA reference, {rows[0].get('rate_date', 'n/a')}"
        return "static file"


@dataclass
class _RateCache:
    """Simple in-memory cache for live FX results."""

    rates: dict[str, Decimal] = field(default_factory=dict)
    fetched_date: date | None = None
    fetched_at: datetime | None = None
    cache_minutes: int = 60

    def is_stale(self) -> bool:
        """True if the cache is empty, from a prior day, or older than cache_minutes."""
        if not self.rates or self.fetched_at is None or self.fetched_date is None:
            return True
        if self.fetched_date != date.today():
            return True
        age = datetime.now(tz=timezone.utc) - self.fetched_at
        return age > timedelta(minutes=self.cache_minutes)


class FrankfurterFXRateProvider:
    """Fetch ECB reference rates live from frankfurter.app with in-memory caching.

    Uses a single API call: GET /latest?from=HKD&to=EUR,USD,...
    Returns HKD-denominated rates for all requested currencies.
    Falls back gracefully (returns empty dict) on any network or parse failure.
    """

    def __init__(self, timeout_s: int = 5, cache_minutes: int = 60) -> None:
        """Args:
            timeout_s: HTTP request timeout in seconds.
            cache_minutes: How long to reuse a fetched result before refetching.
        """
        self._timeout_s = timeout_s
        self._cache = _RateCache(cache_minutes=cache_minutes)
        self._last_date_str: str = ""

    def get_rates(self, currencies: list[str]) -> dict[str, Decimal]:
        """Return live ECB rates for the requested currencies, in HKD per unit.

        Args:
            currencies: ISO 4217 codes, e.g. ["EUR", "USD"].
        Returns:
            Dict mapping currency → HKD_per_unit. Empty on failure.
        """
        foreign = [c for c in currencies if c != "HKD"]
        if not foreign:
            return {}

        if not self._cache.is_stale():
            return {c: v for c, v in self._cache.rates.items() if c in foreign}

        rates = self._fetch(foreign)
        if rates:
            self._cache.rates = rates
            self._cache.fetched_at = datetime.now(tz=timezone.utc)
            self._cache.fetched_date = date.today()
        return {c: v for c, v in rates.items() if c in foreign}

    def _fetch(self, currencies: list[str]) -> dict[str, Decimal]:
        """Make the actual HTTP request to frankfurter.app.

        Args:
            currencies: Foreign currency codes to fetch against HKD base.
        Returns:
            Dict of {currency: HKD_per_unit} on success, empty dict on any error.
        """
        try:
            import httpx  # noqa: PLC0415 — optional dep, only imported when live provider used
        except ImportError:
            logger.error("httpx is required for live FX rates — run: pip install httpx>=0.27")
            return {}

        params = {"from": "HKD", "to": ",".join(currencies)}
        try:
            response = httpx.get(_FRANKFURTER_URL, params=params, timeout=self._timeout_s)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.warning("Live FX fetch failed", extra={"error": str(exc)})
            return {}

        # Response: {"base":"HKD","date":"...","rates":{"EUR":0.1176,"USD":0.1285,...}}
        # rates[currency] = HKD per unit inverted: EUR/HKD = 1 / rates["EUR"]
        raw_rates: dict[str, float] = data.get("rates", {})
        self._last_date_str = data.get("date", "")
        result: dict[str, Decimal] = {}
        for ccy, hkd_per_unit_inv in raw_rates.items():
            if hkd_per_unit_inv and hkd_per_unit_inv != 0:
                result[ccy] = (Decimal("1") / Decimal(str(hkd_per_unit_inv))).quantize(
                    Decimal("0.0001")
                )
        return result

    def rate_source_label(self) -> str:
        """Return source label including the ECB date from the last fetch."""
        date_str = self._last_date_str or str(date.today())
        return f"frankfurter.app (ECB) {date_str}"
