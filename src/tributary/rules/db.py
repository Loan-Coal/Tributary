"""
SQLite-backed rules database with simple full-text search (FTS) for RAG retrieval.
Provides utilities to initialize the DB and ingest/search rule records.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, List, Dict, Any


def init_db(db_path: str | Path) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    # Create tables
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
    # FTS virtual table for searching summaries and full_text
    try:
        cur.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS rules_fts USING fts5(rule_id, summary, full_text, content='')"
        )
    except sqlite3.OperationalError:
        # FTS5 might not be available; fall back to no FTS
        pass
    con.commit()
    con.close()


def ingest_rules(db_path: str | Path, rules: Iterable[Dict[str, Any]]) -> None:
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    for r in rules:
        cur.execute(
            "REPLACE INTO rules (rule_id, jurisdiction, summary, full_text, as_of_date, source_citation) VALUES (?, ?, ?, ?, ?, ?)",
            (
                r.get("id") or r.get("rule_id"),
                r.get("jurisdiction"),
                r.get("summary") or r.get("full_text", ""),
                r.get("full_text", r.get("summary", "")),
                r.get("as_of_date"),
                r.get("source_citation"),
            ),
        )
        # Insert into FTS table if present
        try:
            cur.execute(
                "REPLACE INTO rules_fts (rule_id, summary, full_text) VALUES (?, ?, ?)",
                (r.get("id") or r.get("rule_id"), r.get("summary", ""), r.get("full_text", r.get("summary", ""))),
            )
        except sqlite3.OperationalError:
            pass
    con.commit()
    con.close()


def query_rules(db_path: str | Path, query: str | None = None, jurisdictions: Iterable[str] | None = None, limit: int = 5) -> List[Dict[str, Any]]:
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    params: List[Any] = []
    where_clauses: List[str] = []
    if jurisdictions:
        placeholders = ",".join(["?" for _ in jurisdictions])
        where_clauses.append(f"jurisdiction IN ({placeholders})")
        params.extend(list(jurisdictions))
    # Prefer FTS search when available
    if query:
        try:
            cur.execute("SELECT rule_id, summary, full_text, as_of_date, source_citation FROM rules_fts WHERE rules_fts MATCH ? LIMIT ?", (query, limit))
            rows = cur.fetchall()
            results = [
                {"rule_id": r[0], "summary": r[1], "full_text": r[2], "as_of_date": r[3], "source_citation": r[4]}
                for r in rows
            ]
            if results:
                con.close()
                return results[:limit]
        except sqlite3.OperationalError:
            # FTS not available; fall back to LIKE search
            pass

    # Build fallback SQL
    sql = "SELECT rule_id, summary, full_text, as_of_date, source_citation FROM rules"
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    if query:
        sql += (" AND " if where_clauses else " WHERE ") + "(summary LIKE ? OR full_text LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%"])
    sql += " LIMIT ?"
    params.append(limit)
    cur.execute(sql, params)
    rows = cur.fetchall()
    con.close()
    return [
        {"rule_id": r[0], "summary": r[1], "full_text": r[2], "as_of_date": r[3], "source_citation": r[4]} for r in rows
    ]
