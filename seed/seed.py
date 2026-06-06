"""
Module: seed
Layer: ingestion (orchestrator)
Purpose: Build the Tributary graph in Neo4j from the Lenovo per-country balance
         sheets, then export a JSON snapshot into the Graph/ folder.
Dependencies: graph.writer, graph.snapshot, pipeline.normalize_balance_sheet
Used by: `make ingest` (python -m seed.seed)
"""
from __future__ import annotations

import os
from pathlib import Path

from neo4j import GraphDatabase

from graph.snapshot import export_graph_snapshot
from graph.writer import (
    write_entity,
    write_financial_line_item,
    write_jurisdiction,
)
from pipeline.normalize_balance_sheet import entities, jurisdictions, line_items

# Credentials come from the environment (see .env.example). No real secret is
# committed; export NEO4J_PASSWORD to match your Neo4j container before seeding.
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")
CONSTRAINTS_PATH = Path("graph/constraints.cypher")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def reset_graph(session) -> None:
    """Delete all existing nodes and relationships for a clean rebuild."""
    session.run("MATCH (n) DETACH DELETE n")
    print("  Graph cleared.")


def apply_constraints(session) -> None:
    """Apply uniqueness constraints and indexes from the cypher file."""
    cypher = CONSTRAINTS_PATH.read_text()
    for stmt in cypher.split(";"):
        stmt = stmt.strip()
        if stmt:
            session.run(stmt)
    print("  Constraints applied.")


def _seed_balance_sheets(session) -> None:
    """Write jurisdictions, listing entities, and balance-sheet line items."""
    jurs = jurisdictions()
    for j in jurs:
        write_jurisdiction(session, j)
    print(f"  {len(jurs)} jurisdictions written.")

    ents = entities()
    for e in ents:
        write_entity(session, e)
    print(f"  {len(ents)} entities written.")

    items = line_items()
    for item in items:
        write_financial_line_item(session, item)
    print(f"  {len(items)} financial line items written.")


def seed() -> None:
    """Seed the graph and export a snapshot to the Graph/ folder."""
    print("=== Tributary — seeding graph from Lenovo balance sheets ===\n")

    with driver.session() as session:
        reset_graph(session)
        apply_constraints(session)
        _seed_balance_sheets(session)
        out = export_graph_snapshot(session)
        print(f"  Graph snapshot saved to {out}")

    driver.close()
    print("\n=== Done. Open http://localhost:7474 to explore the graph. ===")


if __name__ == "__main__":
    seed()
