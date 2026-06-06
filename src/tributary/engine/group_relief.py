"""
Module: group_relief
Layer: engine
Purpose: Cross-entity scanner that detects opportunities to redistribute pre-tax profit
    within the group to offset losses in another member. Emits GroupReliefOpportunity
    flags citing the applicable statute. The engine never recommends a transfer amount —
    it flags the opportunity and leaves quantification to the professional (DEC-020).
Dependencies: decimal, uuid, tributary.common, tributary.rules, engine.aggregator
Used by: engine.runner
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from itertools import permutations

from tributary.common.logging import get_logger
from tributary.common.models_engine import GroupReliefMechanism, GroupReliefOpportunity
from tributary.common.models_entity import EntityRecord
from tributary.rules.models import RuleCategory, RulePackLoader
from .aggregator import EntityBase

logger = get_logger(__name__)

_MECHANISM_BY_RULE_ID: dict[str, GroupReliefMechanism] = {
    "organschaft": GroupReliefMechanism.ORGANSCHAFT,
    "integration_fiscale": GroupReliefMechanism.INTEGRATION_FISCALE,
    "group_relief": GroupReliefMechanism.GROUP_RELIEF,
}
_DEFAULT_MECHANISM = GroupReliefMechanism.GROUP_RELIEF


def _find_group_relief_rule(
    loader: RulePackLoader,
    jurisdiction_a: str,
    jurisdiction_b: str,
) -> object | None:
    """Return the first GROUP_RELIEF rule applicable to an (A income, B loss) pair.

    Checks A's jurisdiction pack first (income entity), then B's.

    Args:
        loader: Rule-pack loader.
        jurisdiction_a: Jurisdiction of the income entity.
        jurisdiction_b: Jurisdiction of the loss entity.
    Returns:
        The first matching Rule, or None if no GROUP_RELIEF rule exists.
    """
    for jur in (jurisdiction_a, jurisdiction_b):
        rules = loader.get_rules(jur, RuleCategory.GROUP_RELIEF)
        if rules:
            return rules[0]
    return None


def _resolve_mechanism(rule_id: str) -> GroupReliefMechanism:
    """Derive GroupReliefMechanism from the rule_id string.

    Args:
        rule_id: Rule identifier from the pack.
    Returns:
        Matching GroupReliefMechanism, defaulting to GROUP_RELIEF.
    """
    lower = rule_id.lower()
    for fragment, mechanism in _MECHANISM_BY_RULE_ID.items():
        if fragment in lower:
            return mechanism
    return _DEFAULT_MECHANISM


def _build_opportunity(
    base_a: EntityBase,
    base_b: EntityBase,
    rule: object,
) -> GroupReliefOpportunity:
    """Build a GroupReliefOpportunity for a (income, loss) entity pair.

    Args:
        base_a: Aggregated base for the income entity.
        base_b: Aggregated base for the loss entity (net_income_hkd < 0).
        rule: The GROUP_RELIEF rule (Rule model from rules.models).
    Returns:
        GroupReliefOpportunity citing the rule.
    """
    mechanism_hint = rule.parameters.relief_mechanism or ""
    mechanism = _resolve_mechanism(mechanism_hint or rule.id)
    return GroupReliefOpportunity(
        opportunity_id=str(uuid.uuid4()),
        income_entity_id=base_a.entity_id,
        loss_entity_id=base_b.entity_id,
        income_jurisdiction=base_a.jurisdiction,
        loss_jurisdiction=base_b.jurisdiction,
        available_income_hkd=base_a.net_income_hkd,
        unused_loss_hkd=abs(base_b.net_income_hkd),
        relief_mechanism=mechanism,
        applicable_rule_id=rule.id,
        as_of_date=rule.as_of_date,
        source_citation=rule.source_citation,
        conditions_summary="See rule pack for full eligibility conditions. Professional review required.",
        needs_review=True,
    )


def scan_group_relief(
    bases: dict[str, EntityBase],
    entities: list[EntityRecord],
    loader: RulePackLoader,
) -> list[GroupReliefOpportunity]:
    """Scan all entity pairs for group-level profit redistribution opportunities.

    For each ordered pair (A with net income, B with current-period loss): checks if a
    GROUP_RELIEF rule exists for the pair's jurisdictions. If so, emits one
    GroupReliefOpportunity. For the golden scenario (HK/DE/FR) no bilateral GROUP_RELIEF
    rule exists, so zero opportunities are emitted — that is itself the verified result.

    Args:
        bases: Aggregated entity bases keyed by entity_id.
        entities: All entity records (for relatedness check).
        loader: Rule-pack loader to check for GROUP_RELIEF rules.
    Returns:
        List of GroupReliefOpportunity flags (empty for HK/DE/FR golden scenario).
    """
    entity_ids = [e.entity_id for e in entities]
    opportunities: list[GroupReliefOpportunity] = []

    for id_a, id_b in permutations(entity_ids, 2):
        base_a = bases.get(id_a)
        base_b = bases.get(id_b)
        if base_a is None or base_b is None:
            continue
        if base_a.net_income_hkd <= Decimal("0"):
            continue
        if base_b.net_income_hkd >= Decimal("0"):
            continue
        rule = _find_group_relief_rule(loader, base_a.jurisdiction, base_b.jurisdiction)
        if rule is None:
            logger.debug(
                "No GROUP_RELIEF rule for pair",
                extra={"income": base_a.jurisdiction, "loss": base_b.jurisdiction},
            )
            continue
        opportunity = _build_opportunity(base_a, base_b, rule)
        opportunities.append(opportunity)
        logger.info(
            "Group relief opportunity detected",
            extra={
                "income_entity": id_a,
                "loss_entity": id_b,
                "rule_id": rule.id,
            },
        )

    return opportunities
