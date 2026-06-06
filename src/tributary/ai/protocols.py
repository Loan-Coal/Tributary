"""
Module: protocols
Layer: ai
Purpose: Protocol interfaces for AI layer to interact with Graph and Rules.
Dependencies: typing
Used by: ai.service, tests
"""
from typing import Protocol, List

from tributary.ai.models import TransactionContext, RuleSummary


class GraphReaderProtocol(Protocol):
    def get_transaction_context(self, transaction_id: str) -> TransactionContext:
        """Fetch transaction text and graph facts WITHOUT amounts."""


class RulePackLoaderProtocol(Protocol):
    def get_rule_summaries(self, jurisdictions: List[str]) -> List[RuleSummary]:
        """Fetch rule summaries for prompt injection (id, summary, as_of_date, source_citation)."""
