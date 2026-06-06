"""
Module: service
Layer: ai
Purpose: Orchestrate AI layer classification using Graph context, rule summaries, and a Claude client.
Dependencies: typing, tributary.common.errors, tributary.common.logging, tributary.prompts.loader, tributary.ai.models, tributary.ai.protocols
Used by: examples, tests
"""
from __future__ import annotations

from typing import Any, Dict, List

from tributary.common.errors import AIClientError, AILayerServiceError
from tributary.common.logging import get_logger
from tributary.prompts.loader import load_ai_classification_prompt
from tributary.ai.models import AILayerOutput, RuleSummary, TransactionContext
from tributary.ai.protocols import GraphReaderProtocol, RulePackLoaderProtocol

logger = get_logger(__name__)


class AILayerService:
    def __init__(
        self,
        graph_reader: GraphReaderProtocol,
        rule_loader: RulePackLoaderProtocol,
        llm_client: object,
    ) -> None:
        self.graph_reader = graph_reader
        self.rule_loader = rule_loader
        self.llm_client = llm_client

    def classify_transaction(self, transaction_id: str) -> AILayerOutput:
        """Classify a transaction and return validated AI output."""
        try:
            transaction_context = self.graph_reader.get_transaction_context(transaction_id)
            jurisdictions = self._extract_jurisdictions(transaction_context)
            rule_summaries = self.rule_loader.get_rule_summaries(jurisdictions)
            prompt_data = load_ai_classification_prompt()
            prompt = self._build_prompt(transaction_id, transaction_context, rule_summaries, prompt_data)
            output = self.llm_client.generate(prompt=prompt)
            if output.transaction_id != transaction_id:
                output.transaction_id = transaction_id
            return output
        except AIClientError as exc:
            logger.error("AI classification failed", exc_info=exc, extra={"transaction_id": transaction_id})
            return self._abstain_output(transaction_id)
        except Exception as exc:
            logger.error("Unexpected AI service error", exc_info=exc, extra={"transaction_id": transaction_id})
            raise AILayerServiceError("AI service encountered an unexpected error") from exc

    def _extract_jurisdictions(self, context: TransactionContext) -> List[str]:
        jurisdictions = context.candidate_jurisdictions
        return [str(item) for item in jurisdictions if item is not None]

    def _build_prompt(
        self,
        transaction_id: str,
        transaction_context: TransactionContext,
        rule_summaries: List[RuleSummary],
        prompt_data: Dict[str, str],
    ) -> str:
        sanitized_context = self._serialize_context(transaction_context)
        serialized_rules = self._serialize_rule_summaries(rule_summaries)
        prompt = prompt_data["system_prompt"]
        prompt = prompt.replace("{{transaction_id}}", transaction_id)
        prompt = prompt.replace("{{transaction_context}}", sanitized_context)
        prompt = prompt.replace("{{rule_summaries}}", serialized_rules)
        return prompt

    def _serialize_context(self, context: TransactionContext) -> str:
        context_data = context.model_dump()
        items: List[str] = []
        for key, value in sorted(context_data.items()):
            if key == "candidate_jurisdictions":
                continue
            if isinstance(value, (int, float)):
                continue
            items.append(f"- {key}: {value}")
        if not items:
            return "- no transaction context available"
        return "\n".join(items)

    def _serialize_rule_summaries(self, rule_summaries: List[RuleSummary]) -> str:
        if not rule_summaries:
            return "- no rule summaries available"
        lines: List[str] = []
        for rule in rule_summaries:
            lines.append(
                f"- id: {rule.id}; as_of_date: {rule.as_of_date}; "
                f"source_citation: {rule.source_citation}; summary: {rule.summary}"
            )
        return "\n".join(lines)

    def _abstain_output(self, transaction_id: str) -> AILayerOutput:
        return AILayerOutput(
            transaction_id=transaction_id,
            flow_classification="UNCLASSIFIED",
            candidate_jurisdictions=[],
            retrieved_rules=[],
            evidence_requests=[
                "Please review the transaction and provide necessary facts to complete classification."
            ],
            narrative_template=(
                "Unable to determine classification with the available information. "
                "Refer to the CPA for additional context and confirm rule applicability."
            ),
            needs_human_review=True,
            abstain=True,
        )
