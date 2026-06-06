"""
Module: rag_retriever
Layer: ai
Purpose: RAG retriever adapter that queries the local rules DB to return RuleSummary objects.
Dependencies: tributary.rules.db (via ai.retrieval_db after W6c.9), tributary.ai.models
Used by: ai.adapter, tests
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from tributary.ai.models import RuleSummary
from tributary.ai.retrieval_db import query_rules


class RAGRetriever:
    def __init__(self, db_path: str | Path, top_k: int = 5) -> None:
        self.db_path = Path(db_path)
        self.top_k = int(top_k)

    def get_rule_summaries(self, jurisdictions: Iterable[str], query_text: str | None = None) -> list[RuleSummary]:
        # Query the local rules DB; prefer text-matching if we have transaction text
        results = query_rules(self.db_path, query=query_text, jurisdictions=jurisdictions, limit=self.top_k)
        summaries: list[RuleSummary] = []
        for r in results:
            summaries.append(
                RuleSummary(
                    id=r.rule_id,
                    summary=r.summary,
                    as_of_date=r.as_of_date,
                    source_citation=r.source_citation,
                )
            )
        return summaries
