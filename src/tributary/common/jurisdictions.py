"""
Module: jurisdictions
Layer: common
Purpose: Reference data for jurisdiction membership sets used across the engine and rule packs.
    Centralises the EU member-state list so no engine module carries hardcoded jurisdiction
    literals (DEC-006 — country-agnostic engine).
Dependencies: none
Used by: engine.wht_engine
"""
from __future__ import annotations

# ISO 3166-1 alpha-2 codes for EU member states as of 2024.
# Sourced from: https://european-union.europa.eu/principles-countries-history/country-profiles_en
# Keeping this constant in common/ ensures the engine layer stays country-agnostic (DEC-006).
EU_MEMBER_JURISDICTIONS: frozenset[str] = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU",
    "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
})
