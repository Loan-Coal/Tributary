"""
Module: test_service
Layer: tests
Purpose: Unit tests for the Tributary AI layer service.
Dependencies: tributary.ai.models, tributary.ai.service, tributary.ai.fake_client, tributary.common.errors
Used by: test runner
"""

from tributary.ai.models import AILayerOutput, RuleSummary, TransactionContext
from tributary.ai.service import AILayerService
from tributary.ai.fake_client import FakeClaudeClient
from tributary.common.errors import AIClientError


class DummyGraphReader:
    def get_transaction_context(self, transaction_id: str):
        return TransactionContext.model_validate(
            {
                "transaction_text": "Sale of consulting services to related entity.",
                "candidate_jurisdictions": ["US", "SG"],
            }
        )


class DummyRuleLoader:
    def get_rule_summaries(self, jurisdictions):
        return [
            RuleSummary.model_validate(
                {
                    "id": "TR-001",
                    "summary": "Revenue recognition rule for cross-border services.",
                    "as_of_date": "2026-01-01",
                    "source_citation": "Tax Act §12",
                }
            )
        ]


class ErrorClaudeClient:
    def generate(self, prompt: str, max_tokens: int = 800):
        raise AIClientError("Simulated failure")


def test_classify_transaction_returns_llm_output():
    service = AILayerService(DummyGraphReader(), DummyRuleLoader(), FakeClaudeClient())

    result = service.classify_transaction("txn-123")

    assert result.transaction_id == "txn-123"
    assert result.flow_classification == "REVENUE"
    assert result.candidate_jurisdictions == ["US", "SG"]
    assert result.abstain is False
    assert "{{engine:amount}}" in result.narrative_template


def test_classify_transaction_abstains_on_client_failure():
    service = AILayerService(DummyGraphReader(), DummyRuleLoader(), ErrorClaudeClient())

    result = service.classify_transaction("txn-999")

    assert result.transaction_id == "txn-999"
    assert result.flow_classification == "UNCLASSIFIED"
    assert result.abstain is True
    assert result.needs_human_review is True
