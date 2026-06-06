from neo4j import Session
from common.models import (
    Jurisdiction, Entity, Ownership,
    Account, Counterparty, Transaction, Obligation
)


def write_jurisdiction(session: Session, j: Jurisdiction) -> None:
    session.run(
        """
        MERGE (n:Jurisdiction {id: $id})
        SET n.name             = $name,
            n.tax_regime_notes = $notes
        """,
        id=j.id, name=j.name, notes=j.tax_regime_notes
    )


def write_entity(session: Session, e: Entity) -> None:
    session.run(
        """
        MERGE (en:Entity {id: $id})
        SET en.name = $name,
            en.type = $type
        WITH en
        MATCH (j:Jurisdiction {id: $jid})
        MERGE (en)-[:RESIDENT_IN]->(j)
        """,
        id=e.id, name=e.name, type=e.type, jid=e.jurisdiction_id
    )


def write_ownership(session: Session, o: Ownership) -> None:
    session.run(
        """
        MATCH (owner:Entity {id: $owner_id}),
              (owned:Entity {id: $owned_id})
        MERGE (owner)-[r:OWNS]->(owned)
        SET r.pct = $pct
        """,
        owner_id=o.owner_id, owned_id=o.owned_id, pct=o.pct
    )


def write_account(session: Session, a: Account) -> None:
    session.run(
        """
        MERGE (acc:Account {id: $id})
        SET acc.currency  = $currency,
            acc.bank_name = $bank_name
        WITH acc
        MATCH (e:Entity {id: $eid})
        MERGE (e)-[:HOLDS]->(acc)
        """,
        id=a.id, currency=a.currency,
        bank_name=a.bank_name, eid=a.entity_id
    )


def write_counterparty(session: Session, cp: Counterparty) -> None:
    session.run(
        """
        MERGE (c:Counterparty {id: $id})
        SET c.name     = $name,
            c.location = $location
        WITH c
        MATCH (j:Jurisdiction {id: $jid})
        MERGE (c)-[:BASED_IN]->(j)
        """,
        id=cp.id, name=cp.name,
        location=cp.location, jid=cp.jurisdiction_id
    )


def write_transaction(session: Session, tx: Transaction) -> None:
    # 1. Upsert the Transaction node with all FX provenance fields
    session.run(
        """
        MERGE (t:Transaction {id: $id})
        SET t.amount_original    = $amount_original,
            t.currency_original  = $currency_original,
            t.amount_base        = $amount_base,
            t.currency_base      = $currency_base,
            t.fx_rate            = $fx_rate,
            t.fx_date            = $fx_date,
            t.date               = $date,
            t.description        = $description,
            t.flow_type          = $flow_type
        """,
        id=tx.id,
        amount_original=tx.amount_original,
        currency_original=tx.currency_original,
        amount_base=tx.amount_base,
        currency_base=tx.currency_base,
        fx_rate=tx.fx_rate,
        fx_date=str(tx.fx_date),
        date=str(tx.date),
        description=tx.description,
        flow_type=tx.flow_type
    )
    # 2. Account -[:RECORDS]-> Transaction
    session.run(
        """
        MATCH (a:Account {id: $aid}), (t:Transaction {id: $tid})
        MERGE (a)-[:RECORDS]->(t)
        """,
        aid=tx.account_id, tid=tx.id
    )
    # 3. Transaction -[:WITH]-> Counterparty
    session.run(
        """
        MATCH (t:Transaction {id: $tid}), (c:Counterparty {id: $cid})
        MERGE (t)-[:WITH]->(c)
        """,
        tid=tx.id, cid=tx.counterparty_id
    )


def write_obligation(session: Session, o: Obligation) -> None:
    """Called by the deterministic engine in Phase 3 — not by ingestion."""
    session.run(
        """
        MERGE (obl:Obligation {id: $id})
        SET obl.period          = $period,
            obl.obligation_type = $obligation_type,
            obl.confidence      = $confidence,
            obl.source_rule_ids = $source_rule_ids
        WITH obl
        MATCH (e:Entity       {id: $eid}),
              (j:Jurisdiction {id: $jid})
        MERGE (e)-[r:HAS_OBLIGATION {period: $period}]->(j)
        SET r.obligation_id = $id
        """,
        id=o.id,
        period=o.period,
        obligation_type=o.obligation_type,
        confidence=o.confidence,
        source_rule_ids=o.source_rule_ids,
        eid=o.entity_id,
        jid=o.jurisdiction_id
    )