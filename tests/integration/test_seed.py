"""
Integration tests for golden data seed.

Skipped automatically if Neo4j is not running. To run these tests:
  docker-compose up -d
  pytest tests/integration/test_seed.py -v
"""
from __future__ import annotations

import pytest


def _neo4j_available() -> bool:
    """Check if Neo4j is reachable.

    Returns:
        True if Neo4j responds to a connectivity check, False otherwise.
    """
    try:
        from neo4j import GraphDatabase
        from tributary.config.settings import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER

        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False


neo4j_required = pytest.mark.skipif(
    not _neo4j_available(),
    reason="Neo4j not running — start with docker-compose up -d",
)


@neo4j_required
def test_seed_entity_count() -> None:
    """After seeding, exactly 4 Entity nodes exist (HK, DE, FR, US)."""
    from neo4j import GraphDatabase
    from tributary.config.settings import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
    from tributary.ingestion.seed import run_seed

    run_seed()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        result = session.run("MATCH (e:Entity) RETURN count(e) AS n")
        assert result.single()["n"] == 4
    driver.close()


@neo4j_required
def test_seed_presence_record() -> None:
    """The 185-day PE trigger presence record exists after seeding."""
    from neo4j import GraphDatabase
    from tributary.config.settings import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
    from tributary.ingestion.seed import run_seed

    run_seed()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        result = session.run(
            "MATCH (p:PresenceRecord {presence_id: $pid}) RETURN p.total_days_present AS days",
            pid="PRES-DE-FR-2025",
        )
        record = result.single()
        assert record is not None
        assert record["days"] == 185
    driver.close()


@neo4j_required
def test_seed_transaction_count() -> None:
    """After seeding, exactly 11 Transaction nodes exist (T001–T009 + T010/T011 US)."""
    from neo4j import GraphDatabase
    from tributary.config.settings import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
    from tributary.ingestion.seed import run_seed

    run_seed()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        result = session.run("MATCH (t:Transaction) RETURN count(t) AS n")
        assert result.single()["n"] == 11
    driver.close()


@neo4j_required
def test_seed_idempotent() -> None:
    """Running seed twice does not create duplicate nodes."""
    from neo4j import GraphDatabase
    from tributary.config.settings import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
    from tributary.ingestion.seed import run_seed

    run_seed()
    run_seed()  # second run — must not duplicate
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        result = session.run("MATCH (e:Entity) RETURN count(e) AS n")
        assert result.single()["n"] == 4
    driver.close()


@neo4j_required
def test_seed_ownership_relationships() -> None:
    """Three OWNS relationships exist after seeding (HK→DE, DE→FR, HK→US)."""
    from neo4j import GraphDatabase
    from tributary.config.settings import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
    from tributary.ingestion.seed import run_seed

    run_seed()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        result = session.run("MATCH ()-[r:OWNS]->() RETURN count(r) AS n")
        assert result.single()["n"] == 3
    driver.close()


@neo4j_required
def test_seed_prior_loss() -> None:
    """LOSS-DE-2024 prior period loss node exists after seeding."""
    from neo4j import GraphDatabase
    from tributary.config.settings import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
    from tributary.ingestion.seed import run_seed

    run_seed()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        result = session.run(
            "MATCH (l:PriorPeriodLoss {loss_id: $lid}) RETURN l.remaining_loss_hkd AS amt",
            lid="LOSS-DE-2024",
        )
        record = result.single()
        assert record is not None
        assert abs(record["amt"] - 1_600_000.0) < 0.01
    driver.close()
