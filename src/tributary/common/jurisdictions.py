"""
Module: jurisdictions
Layer: common
Purpose: Reference data for jurisdiction membership sets and currency mappings used across the
    engine, brief, and rule layers. Centralises EU member-state list and jurisdiction→local-currency
    mapping so no engine or brief module carries hardcoded jurisdiction literals (DEC-006).
Dependencies: none
Used by: engine.wht_engine, brief.renderer, engine.cli
"""
from __future__ import annotations

# ISO 3166-1 alpha-2 codes for EU member states as of 2024.
# Sourced from: https://european-union.europa.eu/principles-countries-history/country-profiles_en
# Keeping this constant in common/ ensures the engine layer stays country-agnostic (DEC-006).
EU_MEMBER_JURISDICTIONS: frozenset[str] = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU",
    "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
})

# Jurisdiction → ISO 4217 local currency code.
# HKD is the internal base currency (all engine amounts are stored in HKD).
# Briefs for non-HKD jurisdictions display amounts converted via fx_rates.json.
# Extend this mapping when adding new jurisdictions (Wave 7d+).
JURISDICTION_CURRENCY: dict[str, str] = {
    "HK": "HKD",
    "DE": "EUR",
    "FR": "EUR",
    "US": "USD",
    "GB": "GBP",
    "SG": "SGD",
}
