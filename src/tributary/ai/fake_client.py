"""
Module: fake_client
Layer: ai
Purpose: Local fake AI client for runnable tests and demos.
Dependencies: tributary.ai.models
Used by: examples, tests
"""
from tributary.ai.models import AILayerOutput, RuleCitation


class FakeClaudeClient:
    def generate(self, prompt: str, max_tokens: int = 800) -> AILayerOutput:
        """Return a deterministic AILayerOutput without invoking an external API."""
        return AILayerOutput(
            transaction_id="demo-transaction",
            flow_classification="REVENUE",
            candidate_jurisdictions=["US", "SG"],
            retrieved_rules=[
                RuleCitation(
                    rule_id="TR-001",
                    source_citation="Tax Act §12",
                    as_of_date="2026-01-01",
                    confidence=0.9,
                    reasoning="The transaction appears to meet revenue recognition criteria under the provided rules.",
                )
            ],
            evidence_requests=[
                "Confirm whether the counterparty is a related party and whether contractual terms support revenue recognition."
            ],
            narrative_template=(
                "Revenue is recognized for {{engine:amount}} under the applicable service contract. "
                "Use {{engine:invoice_date}} for date-based revenue recognition."
            ),
            needs_human_review=False,
            abstain=False,
        )
