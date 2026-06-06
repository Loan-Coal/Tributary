"""
Module: snapshot
Layer: graph
Purpose: Export the current Neo4j graph (all nodes + relationships) to a JSON file
         saved in the graph/ folder.
Dependencies: neo4j
Used by: seed.seed
"""
from __future__ import annotations

import json
from pathlib import Path

from neo4j import Session

DEFAULT_SNAPSHOT_PATH = Path("graph/graph_snapshot.json")


def _collect_nodes(session: Session) -> list[dict]:
    """Return every node as {labels, properties}."""
    result = session.run(
        "MATCH (n) RETURN labels(n) AS labels, properties(n) AS props"
    )
    return [{"labels": r["labels"], "properties": r["props"]} for r in result]


def _collect_relationships(session: Session) -> list[dict]:
    """Return every relationship as {type, source, target, properties}."""
    result = session.run(
        """
        MATCH (a)-[r]->(b)
        RETURN type(r) AS type, a.id AS source, b.id AS target,
               properties(r) AS props
        """
    )
    return [
        {"type": r["type"], "source": r["source"],
         "target": r["target"], "properties": r["props"]}
        for r in result
    ]


def export_graph_snapshot(session: Session,
                          out_path: Path = DEFAULT_SNAPSHOT_PATH) -> Path:
    """Write the full graph to a JSON snapshot file.

    Args:
        session: Active Neo4j session.
        out_path: Destination JSON path (defaults under Graph/).
    Returns:
        The path written.
    """
    snapshot = {
        "nodes": _collect_nodes(session),
        "relationships": _collect_relationships(session),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2, default=str))
    return out_path
