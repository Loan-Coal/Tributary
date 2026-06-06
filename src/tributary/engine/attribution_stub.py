"""
Module: attribution_stub
Layer: engine
Purpose: AttributionStub implements AILayerProtocol by loading data/golden/attributions_stub.json.
    It is the deterministic stand-in for the AI layer until the real Claude adapter (Wave 5)
    replaces it. Emits no figures (DEC-002, DEC-010).
Dependencies: json, pathlib, tributary.common
Used by: engine.runner (injected as AILayerProtocol), engine tests
"""
from __future__ import annotations

import json
from pathlib import Path

from tributary.common.errors import AIValidationError
from tributary.common.models import (
    ApplicableRule,
    ConfidenceLevel,
    FlowAttribution,
    FlowClassification,
    FlowContext,
    FlowNature,
    JurisdictionClaim,
    JurisdictionCode,
    RuleCitation,
    RuleRetrievalResult,
)
from tributary.config.settings import DATA_DIR

_STUB_RELATIVE = "golden/attributions_stub.json"


class AttributionStub:
    """File-backed AILayerProtocol implementation for the golden scenario."""

    def __init__(self, stub_path: Path | None = None) -> None:
        """Load and cache the attribution stub mapping.

        Args:
            stub_path: Path to attributions_stub.json. Defaults to the golden fixture.
        Raises:
            AIValidationError: If the stub file is missing or malformed.
        """
        path = stub_path if stub_path is not None else Path(DATA_DIR) / _STUB_RELATIVE
        if not path.exists():
            raise AIValidationError(f"Attribution stub not found: {path}")
        try:
            self._flows: dict = json.loads(path.read_text(encoding="utf-8"))["flows"]
        except (json.JSONDecodeError, KeyError) as exc:
            raise AIValidationError(f"Invalid attribution stub {path}: {exc}") from exc

    def _flow(self, flow_id: str) -> dict:
        """Return the stub entry for a flow or raise."""
        if flow_id not in self._flows:
            raise AIValidationError(f"No stub attribution for flow {flow_id}")
        return self._flows[flow_id]

    def classify_flow(self, context: FlowContext) -> FlowClassification:
        """Return the stubbed classification for a flow."""
        entry = self._flow(context.flow_id)
        return FlowClassification(
            flow_id=context.flow_id,
            nature=FlowNature(entry["nature"]),
            confidence=ConfidenceLevel(entry["confidence"]),
            rule_citations=[RuleCitation.model_validate(c) for c in entry["rule_citations"]],
            abstain_reason=entry.get("abstain_reason"),
        )

    def attribute_flow(
        self, context: FlowContext, classification: FlowClassification
    ) -> FlowAttribution:
        """Return the stubbed jurisdiction attribution for a flow."""
        attribution = self._flow(context.flow_id)["attribution"]
        claims = [
            JurisdictionClaim(
                jurisdiction=claim["jurisdiction"],
                confidence=ConfidenceLevel(claim["confidence"]),
                claim_basis=claim["claim_basis"],
                rationale_citation=RuleCitation.model_validate(claim["rationale_citation"]),
            )
            for claim in attribution["claims"]
        ]
        return FlowAttribution(
            flow_id=context.flow_id,
            primary_jurisdiction=attribution.get("primary_jurisdiction"),
            claims=claims,
            abstain=attribution["abstain"],
            abstain_reason=attribution.get("abstain_reason"),
        )

    def retrieve_applicable_rules(
        self, flow_id: str, jurisdiction: JurisdictionCode, nature: FlowNature
    ) -> RuleRetrievalResult:
        """Return the stubbed applicable rules for a flow + jurisdiction."""
        by_jurisdiction = self._flow(flow_id).get("applicable_rules", {})
        rules = [
            ApplicableRule.model_validate(rule)
            for rule in by_jurisdiction.get(jurisdiction, [])
        ]
        return RuleRetrievalResult(
            flow_id=flow_id,
            jurisdiction=jurisdiction,
            applicable_rules=rules,
            abstain=not rules,
            abstain_reason=None if rules else "No applicable rules in stub for this jurisdiction.",
        )
