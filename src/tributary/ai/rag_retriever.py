"""
RAG retriever adapter that queries the local rules DB to return `RuleSummary` objects.
Implements the `get_rule_summaries(jurisdictions)` interface expected by the service.
"""
from __future__ import annotations

from typing import List, Iterable
from pathlib import Path

from tributary.rules import db as rules_db
from tributary.ai.models import RuleSummary


class RAGRetriever:
    def __init__(self, db_path: str | Path, top_k: int = 5) -> None:
        self.db_path = Path(db_path)
        self.top_k = int(top_k)

    def get_rule_summaries(self, jurisdictions: Iterable[str], query_text: str | None = None) -> List[RuleSummary]:
        # Query the local rules DB; prefer text-matching if we have transaction text
        results = rules_db.query_rules(self.db_path, query=query_text, jurisdictions=jurisdictions, limit=self.top_k)
        summaries: List[RuleSummary] = []
        for r in results:
            summaries.append(
                RuleSummary.model_validate(
                    {
                        "id": r.get("rule_id"),
                        "summary": r.get("summary", ""),
                        "as_of_date": r.get("as_of_date", ""),
                        "source_citation": r.get("source_citation", ""),
                    }
                )
            )
        return summaries
