"""
Package: tributary.rules
Layer: rules
Purpose: Rule-pack loader interface and country pack readers (no AI calls, no graph access).
Public surface: Rule, RulePack, TreatyPack, RuleType, RuleCategory, RuleParameters,
    RulePackLoader, JSONRulePackLoader.
"""
from __future__ import annotations

from .loader import JSONRulePackLoader
from .models import (
    Rule,
    RuleCategory,
    RulePack,
    RulePackLoader,
    RuleParameters,
    RuleType,
    TreatyPack,
)

__all__ = [
    "JSONRulePackLoader",
    "Rule",
    "RuleCategory",
    "RulePack",
    "RulePackLoader",
    "RuleParameters",
    "RuleType",
    "TreatyPack",
]
