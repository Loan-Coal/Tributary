"""
Module: loader
Layer: rules
Purpose: JSON-file implementation of the RulePackLoader protocol. Loads and validates
    per-jurisdiction packs (data/rules/<jur>.json) and bilateral treaty packs
    (data/rules/treaties/<a>_<b>.json), failing fast on missing or malformed files.
Dependencies: json, pathlib, tributary.rules.models, tributary.common, tributary.config
Used by: engine (injected as RulePackLoader), rule-pack tests
"""
from __future__ import annotations

import json
from pathlib import Path

from tributary.common.errors import RulePackError
from tributary.common.logging import get_logger
from tributary.common.models import FiscalCalendar, JurisdictionCode
from tributary.config.settings import DATA_DIR
from tributary.rules.models import (
    Rule,
    RuleCategory,
    RulePack,
    TreatyPack,
)

logger = get_logger(__name__)

_RULES_SUBDIR = "rules"
_TREATIES_SUBDIR = "treaties"


class JSONRulePackLoader:
    """Loads rule packs from JSON files on disk. Packs are validated and cached on first use."""

    def __init__(self, rules_dir: Path | None = None) -> None:
        """Initialise the loader.

        Args:
            rules_dir: Directory holding <jur>.json packs and a treaties/ subdir.
                Defaults to ``<DATA_DIR>/rules``.
        """
        self._rules_dir = rules_dir if rules_dir is not None else Path(DATA_DIR) / _RULES_SUBDIR
        self._packs: dict[str, RulePack] = {}
        self._treaties: dict[tuple[str, str], TreatyPack] = {}

    def _load_pack(self, jurisdiction: str) -> RulePack:
        """Load and cache one jurisdiction pack, validating against the schema.

        Raises:
            RulePackError: On missing file, invalid JSON, or schema mismatch.
        """
        if jurisdiction in self._packs:
            return self._packs[jurisdiction]
        path = self._rules_dir / f"{jurisdiction.lower()}.json"
        if not path.exists():
            raise RulePackError(f"Rule pack not found for jurisdiction {jurisdiction}: {path}")
        try:
            pack = RulePack.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RulePackError(f"Invalid rule pack {path}: {exc}") from exc
        self._packs[jurisdiction] = pack
        return pack

    def _load_treaty(self, jur_a: str, jur_b: str) -> TreatyPack | None:
        """Load and cache a bilateral treaty pack if it exists (order-independent)."""
        key = tuple(sorted((jur_a, jur_b)))
        if key in self._treaties:
            return self._treaties[key]
        path = self._rules_dir / _TREATIES_SUBDIR / f"{key[0].lower()}_{key[1].lower()}.json"
        if not path.exists():
            return None
        try:
            treaty = TreatyPack.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RulePackError(f"Invalid treaty pack {path}: {exc}") from exc
        self._treaties[key] = treaty
        return treaty

    def get_rules(
        self, jurisdiction: JurisdictionCode, category: RuleCategory
    ) -> list[Rule]:
        """Return all rules for a jurisdiction matching a semantic category."""
        pack = self._load_pack(jurisdiction)
        return [rule for rule in pack.rules if rule.category == category]

    def get_rule(self, jurisdiction: JurisdictionCode, rule_id: str) -> Rule:
        """Return one rule by id.

        Raises:
            RulePackError: If the rule is not found in the jurisdiction pack.
        """
        pack = self._load_pack(jurisdiction)
        for rule in pack.rules:
            if rule.id == rule_id:
                return rule
        raise RulePackError(f"Rule {rule_id} not found in {jurisdiction} pack")

    def get_treaty_rules(
        self, jurisdiction_a: JurisdictionCode, jurisdiction_b: JurisdictionCode
    ) -> list[Rule]:
        """Return treaty rules between two jurisdictions (empty if no treaty)."""
        treaty = self._load_treaty(jurisdiction_a, jurisdiction_b)
        return list(treaty.rules) if treaty is not None else []

    def get_fiscal_calendar(self, jurisdiction: JurisdictionCode) -> FiscalCalendar:
        """Return the fiscal calendar for a jurisdiction."""
        return self._load_pack(jurisdiction).fiscal_calendar
