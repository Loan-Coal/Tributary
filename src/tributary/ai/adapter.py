"""
Module: adapter
Layer: ai
Purpose: Adapts AILayerService (colleague's implementation) to the AILayerProtocol the
    engine expects. Bridges FlowContext ↔ TransactionContext and maps AILayerOutput to
    the three separate protocol return types.
Dependencies: tributary.common, tributary.rules.models, tributary.ai.service, tributary.ai.models
Used by: engine (injected as AILayerProtocol implementation), tests
"""
from __future__ import annotations

from datetime import date

from tributary.ai.models import AILayerOutput, RuleSummary, TransactionContext
from tributary.ai.service import AILayerService
from tributary.common.errors import AILayerError
from tributary.common.logging import get_logger
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
from tributary.rules.models import RuleCategory, RulePackLoader

logger = get_logger(__name__)

# Normalise AILayerOutput.flow_classification (uppercase) → FlowNature (lowercase enum)
_NATURE_MAP: dict[str, FlowNature] = {
    "REVENUE": FlowNature.REVENUE,
    "EXPENSE": FlowNature.EXPENSE,
    "INTERCOMPANY": FlowNature.INTERCOMPANY,
    "CAPITAL": FlowNature.CAPITAL,
    "LOAN": FlowNature.LOAN,
    "UNCLASSIFIED": FlowNature.OTHER,
}

# Rule categories surfaced to the LLM as context (subset is enough for prompt grounding)
_SUMMARY_CATEGORIES: tuple[RuleCategory, ...] = (
    RuleCategory.CIT_RATE,
    RuleCategory.WHT_DIVIDEND,
    RuleCategory.VAT_THRESHOLD,
    RuleCategory.PE_THRESHOLD,
)


class _FlowContextGraphReader:
    """Adapts a FlowContext to the GraphReaderProtocol that AILayerService expects."""

    def __init__(self, context: FlowContext) -> None:
        self._context = context

    def get_transaction_context(self, transaction_id: str) -> TransactionContext:
        """Return a TransactionContext built from the cached FlowContext."""
        return TransactionContext(
            transaction_text=self._context.description,
            candidate_jurisdictions=list(self._context.available_jurisdictions),
        )


class _RuleLoaderBridge:
    """Adapts the canonical RulePackLoader to RulePackLoaderProtocol for AILayerService."""

    def __init__(self, loader: RulePackLoader) -> None:
        self._loader = loader

    def get_rule_summaries(self, jurisdictions: list[str]) -> list[RuleSummary]:
        """Fetch high-level rule summaries for prompt injection.

        Args:
            jurisdictions: ISO country code strings.
        Returns:
            RuleSummary list (one entry per rule found across key categories).
        """
        summaries: list[RuleSummary] = []
        for jur_str in jurisdictions:
            if not isinstance(jur_str, str) or len(jur_str) != 2:
                continue
            jur: JurisdictionCode = jur_str.upper()
            for category in _SUMMARY_CATEGORIES:
                for rule in self._loader.get_rules(jur, category):
                    summaries.append(RuleSummary(
                        id=rule.id,
                        summary=f"{rule.category.value}: {rule.id}",
                        as_of_date=str(rule.as_of_date),
                        source_citation=rule.source_citation,
                    ))
        return summaries


def _confidence(output: AILayerOutput) -> ConfidenceLevel:
    """Map abstain/review flags to ConfidenceLevel."""
    if output.abstain or output.needs_human_review:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.HIGH


def _map_citation(
    raw: object, fallback_jurisdiction: JurisdictionCode
) -> RuleCitation:
    """Convert an ai.models.RuleCitation to the canonical RuleCitation."""
    return RuleCitation(
        rule_id=raw.rule_id,
        jurisdiction=fallback_jurisdiction,
        as_of_date=date.fromisoformat(raw.as_of_date),
        source_citation=raw.source_citation,
    )


def _to_classification(
    flow_id: str, output: AILayerOutput, fallback_jur: JurisdictionCode
) -> FlowClassification:
    """Map AILayerOutput → FlowClassification."""
    nature = _NATURE_MAP.get(output.flow_classification, FlowNature.OTHER)
    citations = [_map_citation(r, fallback_jur) for r in output.retrieved_rules]
    return FlowClassification(
        flow_id=flow_id,
        nature=nature,
        confidence=_confidence(output),
        rule_citations=citations,
        abstain_reason="AI abstained" if output.abstain else None,
    )


def _to_attribution(
    flow_id: str, output: AILayerOutput, fallback_jur: JurisdictionCode
) -> FlowAttribution:
    """Map AILayerOutput → FlowAttribution."""
    claims: list[JurisdictionClaim] = []
    confidence = _confidence(output)
    citation = RuleCitation(
        rule_id="adapter-placeholder",
        jurisdiction=fallback_jur,
        as_of_date=date.today(),
        source_citation="Derived from AI output; confirm against rule pack.",
    )
    for jur_str in output.candidate_jurisdictions:
        if not isinstance(jur_str, str) or len(jur_str) != 2:
            logger.warning("Invalid jurisdiction code from AI output", extra={"code": jur_str})
            continue
        jur: JurisdictionCode = jur_str.upper()
        claims.append(JurisdictionClaim(
            jurisdiction=jur,
            confidence=confidence,
            claim_basis="AI jurisdiction attribution",
            rationale_citation=citation,
        ))
    return FlowAttribution(
        flow_id=flow_id,
        primary_jurisdiction=claims[0].jurisdiction if claims else None,
        claims=claims,
        abstain=output.abstain,
        abstain_reason="AI abstained" if output.abstain else None,
    )


def _to_rule_retrieval(
    flow_id: str,
    jurisdiction: JurisdictionCode,
    output: AILayerOutput,
) -> RuleRetrievalResult:
    """Map AILayerOutput → RuleRetrievalResult for one jurisdiction."""
    rules: list[ApplicableRule] = []
    for raw in output.retrieved_rules:
        rules.append(ApplicableRule(
            rule_id=raw.rule_id,
            jurisdiction=jurisdiction,
            rule_type="unknown",
            as_of_date=date.fromisoformat(raw.as_of_date),
            source_citation=raw.source_citation,
            relevance_note=getattr(raw, "reasoning", None),
        ))
    return RuleRetrievalResult(
        flow_id=flow_id,
        jurisdiction=jurisdiction,
        applicable_rules=rules,
        abstain=output.abstain,
        abstain_reason="AI abstained" if output.abstain else None,
    )


class AILayerAdapter:
    """Implements AILayerProtocol by wrapping AILayerService.

    The engine calls the three-method protocol; this adapter translates each call
    to AILayerService.classify_transaction() and maps the combined AILayerOutput
    to the appropriate return type. Results are cached per flow_id so the LLM is
    called only once per flow regardless of how many protocol methods are invoked.
    """

    def __init__(self, llm_client: object, rule_loader: RulePackLoader) -> None:
        self._llm_client = llm_client
        self._rule_loader = rule_loader
        self._cache: dict[str, AILayerOutput] = {}

    def _get_output(self, context: FlowContext) -> AILayerOutput:
        """Return cached AILayerOutput, calling the LLM on first access."""
        if context.flow_id not in self._cache:
            service = AILayerService(
                graph_reader=_FlowContextGraphReader(context),
                rule_loader=_RuleLoaderBridge(self._rule_loader),
                llm_client=self._llm_client,
            )
            self._cache[context.flow_id] = service.classify_transaction(context.flow_id)
        return self._cache[context.flow_id]

    def _fallback_jur(self, context: FlowContext) -> JurisdictionCode:
        """Return best-guess jurisdiction for citation fallback."""
        if context.source_jurisdiction is not None:
            return context.source_jurisdiction
        if context.available_jurisdictions:
            return context.available_jurisdictions[0]
        raise AILayerError("Cannot determine fallback jurisdiction for flow context")

    def classify_flow(self, context: FlowContext) -> FlowClassification:
        """Classify flow nature by delegating to AILayerService."""
        output = self._get_output(context)
        return _to_classification(context.flow_id, output, self._fallback_jur(context))

    def attribute_flow(
        self, context: FlowContext, classification: FlowClassification
    ) -> FlowAttribution:
        """Attribute jurisdictions by delegating to AILayerService (cached)."""
        output = self._get_output(context)
        return _to_attribution(context.flow_id, output, self._fallback_jur(context))

    def retrieve_applicable_rules(
        self,
        flow_id: str,
        jurisdiction: JurisdictionCode,
        nature: FlowNature,
    ) -> RuleRetrievalResult:
        """Return rule retrieval result from cached output, or abstain if not cached."""
        output = self._cache.get(flow_id)
        if output is None:
            return RuleRetrievalResult(
                flow_id=flow_id,
                jurisdiction=jurisdiction,
                applicable_rules=[],
                abstain=True,
                abstain_reason="classify_flow must be called before retrieve_applicable_rules",
            )
        return _to_rule_retrieval(flow_id, jurisdiction, output)
