"""
Module: money
Layer: engine
Purpose: Shared monetary helpers for the deterministic engine — HKD rounding and effective-rate
    derivation. Centralised so every sub-engine rounds identically (auditable, no drift).
Dependencies: decimal
Used by: all engine computation modules
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_HKD_QUANTUM = Decimal("1")


def round_hkd(amount: Decimal) -> Decimal:
    """Round an HKD amount to the nearest whole dollar (round-half-up).

    Args:
        amount: The unrounded amount.
    Returns:
        The amount rounded to an integer number of HKD.
    """
    return amount.quantize(_HKD_QUANTUM, rounding=ROUND_HALF_UP)


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
