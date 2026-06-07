"""
Module: graph_data
Layer: api
Purpose: Query Neo4j and serialize entity/transaction graph to vis.js-compatible JSON.
    Produces {nodes, edges} dicts suitable for the demo network visualization.
Dependencies: neo4j, tributary.config, tributary.common.errors
Used by: tributary.api.routes (/api/demo/graph endpoint)
"""
from __future__ import annotations

from typing import Any

from tributary.common.errors import EngineError
from tributary.common.logging import get_logger
from tributary.config import settings

logger = get_logger(__name__)

_JURISDICTION_COLORS: dict[str, str] = {
    "HK": "#e63946",
    "DE": "#2a9d8f",
    "FR": "#e9c46a",
    "US": "#457b9d",
}

_ENTITY_GROUP_COLOR = "#264653"


def _build_driver() -> Any:
    """Create and verify a Neo4j driver from settings.

    Returns:
        Connected neo4j.GraphDatabase.Driver instance.
    Raises:
        EngineError: If Neo4j is unreachable.
    """
    try:
        import neo4j  # noqa: PLC0415
    except ImportError as exc:
        raise EngineError("neo4j package not installed") from exc

    driver = neo4j.GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        notifications_min_severity="OFF",
    )
    try:
        driver.verify_connectivity()
    except Exception as exc:
        raise EngineError("Neo4j unreachable — run docker-compose up -d first") from exc
    return driver


def get_graph_data() -> dict[str, list[dict[str, Any]]]:
    """Query Neo4j and return entity + transaction graph in vis.js format.

    Returns:
        Dict with 'nodes' (entity nodes) and 'edges' (ownership + transaction flows).
    Raises:
        EngineError: If Neo4j is unreachable or graph is empty.
    """
    driver = _build_driver()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    with driver.session() as session:
        _add_entity_nodes(session, nodes)
        _add_ownership_edges(session, edges)
        _add_transaction_edges(session, edges)

    driver.close()

    if not nodes:
        raise EngineError("Graph is empty — run 'make ingest' first")

    logger.info("Graph data built", extra={"nodes": len(nodes), "edges": len(edges)})
    return {"nodes": nodes, "edges": edges}


def _add_entity_nodes(session: Any, nodes: list[dict[str, Any]]) -> None:
    """Append entity nodes to the nodes list.

    Args:
        session: Active Neo4j session.
        nodes: List to append node dicts into.
    """
    result = session.run("MATCH (e:Entity) RETURN e ORDER BY e.entity_id")
    for record in result:
        props = dict(record["e"])
        jur = props.get("resident_jurisdiction", "??")
        color = _JURISDICTION_COLORS.get(jur, "#888888")
        nodes.append({
            "id": props["entity_id"],
            "label": props["name"],
            "title": f"{props['entity_type']} · {jur}",
            "color": {"background": color, "border": "#1a1a2e"},
            "font": {"color": "#ffffff", "size": 13},
            "shape": "box",
            "jurisdiction": jur,
            "entity_type": props.get("entity_type", ""),
        })


def _add_ownership_edges(session: Any, edges: list[dict[str, Any]]) -> None:
    """Append ownership edges to the edges list.

    Args:
        session: Active Neo4j session.
        edges: List to append edge dicts into.
    """
    result = session.run(
        """
        MATCH (owner:Entity)-[r:OWNS]->(owned:Entity)
        RETURN owner.entity_id AS from_id, owned.entity_id AS to_id,
               r.ownership_pct AS pct
        """
    )
    for rec in result:
        pct = rec["pct"]
        label = f"{int(pct * 100)}%" if pct is not None else "OWNS"
        edges.append({
            "from": rec["from_id"],
            "to": rec["to_id"],
            "label": label,
            "type": "ownership",
            "color": {"color": "#aaaaaa", "opacity": 0.8},
            "dashes": False,
            "arrows": "to",
            "width": 2,
        })


def _add_transaction_edges(session: Any, edges: list[dict[str, Any]]) -> None:
    """Append transaction flow edges (intercompany only) to the edges list.

    Args:
        session: Active Neo4j session.
        edges: List to append edge dicts into.
    """
    result = session.run(
        """
        MATCH (t:Transaction)
        WHERE t.is_intercompany = true
          AND t.counterparty_entity_id IS NOT NULL
        RETURN t.transaction_id AS tid,
               t.source_entity_id AS from_id,
               t.counterparty_entity_id AS to_id,
               t.activity_type AS activity,
               t.amount_hkd AS amount_hkd
        ORDER BY t.transaction_id
        """
    )
    for rec in result:
        amount = rec["amount_hkd"]
        amount_label = f"HKD {amount:,.0f}" if amount is not None else ""
        activity = rec["activity"] or "flow"
        edges.append({
            "from": rec["from_id"],
            "to": rec["to_id"],
            "label": f"{activity}\n{amount_label}",
            "type": "transaction",
            "transaction_id": rec["tid"],
            "color": {"color": "#f4a261", "opacity": 0.7},
            "dashes": True,
            "arrows": "to",
            "width": 1,
        })
