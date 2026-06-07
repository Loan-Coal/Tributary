"""
Module: money
Layer: engine
Purpose: Shared monetary helpers for the deterministic engine — base-currency rounding and
    effective-rate derivation. All engine amounts are stored in HKD (DEC-025); this module
    rounds to the nearest whole unit of the base currency. Centralised so every sub-engine
    rounds identically (auditable, no drift).
Dependencies: decimal
Used by: all engine computation modules
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_UNIT_QUANTUM = Decimal("1")


def round_amount(amount: Decimal) -> Decimal:
    """Round a base-currency amount to the nearest whole unit (round-half-up).

    Args:
        amount: The unrounded amount in the internal base currency (HKD, DEC-025).
    Returns:
        The amount rounded to an integer number of base-currency units.
    """
    return amount.quantize(_UNIT_QUANTUM, rounding=ROUND_HALF_UP)


def effective_rate(base_rate: Decimal, surcharge_rate: Decimal | None) -> Decimal:
    """Combine a base tax rate with an optional surcharge (e.g. DE 15% × 1.055 = 15.825%).

    Args:
        base_rate: The statutory rate as a fraction.
        surcharge_rate: Optional surcharge as a fraction of the base tax (None = no surcharge).
    Returns:
        The effective rate as a fraction.
    """
    if surcharge_rate is None:
        return base_rate
    return base_rate * (Decimal("1") + surcharge_rate)
