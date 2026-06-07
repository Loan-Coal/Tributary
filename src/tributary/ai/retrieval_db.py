"""
Module: retrieval_db
Layer: ai
Purpose: SQLite-backed rules database with FTS for RAG retrieval. Typed Pydantic I/O;
    logs all sqlite3 failures — no silent swallowing.
Dependencies: sqlite3, pathlib, pydantic, tributary.rules.models, tributary.common.logging
Used by: ai.rag_retriever
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel

from tributary.common.logging import get_logger
from tributary.rules.models import Rule

logger = get_logger(__name__)


class RuleSearchResult(BaseModel):
    """One row returned from the retrieval DB query."""

    rule_id: str
    summary: str
    full_text: str
    as_of_date: str
    source_citation: str


def init_db(db_path: str | Path) -> None:
    """Initialise the SQLite rules DB and FTS5 virtual table.

    Args:
        db_path: File path for the SQLite database (created if absent).
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS rules (
            rule_id TEXT PRIMARY KEY,
            jurisdiction TEXT,
            summary TEXT,
            full_text TEXT,
            as_of_date TEXT,
            source_citation TEXT
        )
        """
    )
    try:
        cur.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS rules_fts "
            "USING fts5(rule_id, summary, full_text, content='')"
        )
    except sqlite3.OperationalError as exc:
        logger.warning("FTS5 not available — falling back to LIKE search", extra={"error": str(exc)})
    con.commit()
    con.close()


def ingest_rules(db_path: str | Path, rules: Iterable[Rule]) -> None:
    """Ingest typed Rule objects into the SQLite rules DB.

    Args:
        db_path: File path for the SQLite database.
        rules: Iterable of Rule Pydantic objects.
    """
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    for rule in rules:
        summary = f"{rule.category.value}: {rule.id}"
        full_text = rule.source_citation
        cur.execute(
            "REPLACE INTO rules "
            "(rule_id, jurisdiction, summary, full_text, as_of_date, source_citation) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                rule.id,
                rule.jurisdiction,
                summary,
                full_text,
                str(rule.as_of_date),
                rule.source_citation,
            ),
        )
        try:
            cur.execute(
                "REPLACE INTO rules_fts (rule_id, summary, full_text) VALUES (?, ?, ?)",
                (rule.id, summary, full_text),
            )
        except sqlite3.OperationalError as exc:
            logger.warning(
                "FTS insert skipped — FTS5 unavailable",
                extra={"rule_id": rule.id, "error": str(exc)},
            )
    con.commit()
    con.close()


def query_rules(
    db_path: str | Path,
    query: str | None = None,
    jurisdictions: Iterable[str] | None = None,
    limit: int = 5,
) -> list[RuleSearchResult]:
    """Query the rules DB by jurisdiction and/or text.

    Args:
        db_path: File path for the SQLite database.
        query: Optional FTS query string; falls back to LIKE search.
        jurisdictions: Optional iterable of ISO jurisdiction codes to filter by.
        limit: Maximum number of results.
    Returns:
        List of RuleSearchResult (may be empty).
    """
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    jur_list = list(jurisdictions) if jurisdictions is not None else []

    if query:
        try:
            cur.execute(
                "SELECT rule_id, summary, full_text, as_of_date, source_citation "
                "FROM rules_fts WHERE rules_fts MATCH ? LIMIT ?",
                (query, limit),
            )
            rows = cur.fetchall()
            if rows:
                con.close()
                return [_row_to_result(r) for r in rows[:limit]]
        except sqlite3.OperationalError as exc:
            logger.warning(
                "FTS search failed — falling back to LIKE",
                extra={"query": query, "error": str(exc)},
            )

    params: list[object] = []
    where_clauses: list[str] = []
    if jur_list:
        placeholders = ",".join(["?" for _ in jur_list])
        where_clauses.append(f"jurisdiction IN ({placeholders})")
        params.extend(jur_list)
    if query:
        where_clauses.append("(summary LIKE ? OR full_text LIKE ?)")
        params.extend([f"%{query}%", f"%{query}%"])

    sql = "SELECT rule_id, summary, full_text, as_of_date, source_citation FROM rules"
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += " LIMIT ?"
    params.append(limit)

    cur.execute(sql, params)
    rows = cur.fetchall()
    con.close()
    return [_row_to_result(r) for r in rows]


def _row_to_result(row: tuple) -> RuleSearchResult:
    return RuleSearchResult(
        rule_id=row[0] or "",
        summary=row[1] or "",
        full_text=row[2] or "",
        as_of_date=row[3] or "",
        source_citation=row[4] or "",
    )
