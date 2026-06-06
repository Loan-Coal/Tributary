# seed/seed.py
from pathlib import Path
from neo4j import GraphDatabase
from pipeline.normalize_oecd_data import normalize_oecd_to_transactions
from graph.writer import (
    write_jurisdiction, write_entity, write_ownership,
    write_account, write_counterparty, write_transaction,
)

# use pipeline for I/O and normalization
from pipeline.io import read_csv, read_json
from pipeline.normalizer import (
    normalize_entity, normalize_account,
    normalize_counterparty, normalize_ownership,
    normalize_transaction,
)
from common.models import Jurisdiction

# New canonical data folder produced by the pipeline
DATA = Path("data/processed")
driver = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", "taxcopilot")
)


def apply_constraints(session) -> None:
    cypher = Path("graph/constraints.cypher").read_text()
    for stmt in cypher.split(";"):
        stmt = stmt.strip()
        if stmt:
            session.run(stmt)
    print("  Constraints applied.")


def seed() -> None:
    print("=== Tributary — seeding graph ===\n")

    with driver.session() as session:

        apply_constraints(session)

        # ── 1. Jurisdictions ──────────────────────────────────────────────
        juris_path = DATA / "jurisdictions.json"
        if juris_path.exists():
            jurs = [Jurisdiction(**r) for r in read_json(juris_path)]
            for j in jurs:
                write_jurisdiction(session, j)
            print(f"  {len(jurs)} jurisdictions written.")
        else:
            print(f"  Skipping jurisdictions: {juris_path} not found.")

        # ── 2. Entities ───────────────────────────────────────────────────
        entities_path = DATA / "entities.json"
        if entities_path.exists():
            entities = [normalize_entity(r) for r in read_json(entities_path)]
            for e in entities:
                write_entity(session, e)
            print(f"  {len(entities)} entities written.")
        else:
            print(f"  Skipping entities: {entities_path} not found.")

        # ── 3. Ownerships ─────────────────────────────────────────────────
        ownerships_path = DATA / "ownerships.json"
        if ownerships_path.exists():
            ownerships = [normalize_ownership(r) for r in read_json(ownerships_path)]
            for o in ownerships:
                write_ownership(session, o)
            print(f"  {len(ownerships)} ownership edges written.")
        else:
            print(f"  Skipping ownerships: {ownerships_path} not found.")

        # ── 4. Accounts ───────────────────────────────────────────────────
        accounts_path = DATA / "accounts.json"
        if accounts_path.exists():
            accounts = [normalize_account(r) for r in read_json(accounts_path)]
            for a in accounts:
                write_account(session, a)
            print(f"  {len(accounts)} accounts written.")
        else:
            print(f"  Skipping accounts: {accounts_path} not found.")

        # ── 5. Counterparties ─────────────────────────────────────────────
        cps_path = DATA / "counterparties.json"
        if cps_path.exists():
            cps = [normalize_counterparty(r) for r in read_json(cps_path)]
            for cp in cps:
                write_counterparty(session, cp)
            print(f"  {len(cps)} counterparties written.")
        else:
            print(f"  Skipping counterparties: {cps_path} not found.")

        # ── 6. Transactions ───────────────────────────────────────────────
        # If raw OECD data exists, generate normalized transactions into DATA
        raw_oecd = Path("data/raw/transactions_raw.csv")
        normalized_target = DATA / "transactions.csv"
        alt_normalized = DATA / "transactions_normalized.csv"

        if raw_oecd.exists():
            print("  Running pipeline.normalize_oecd_to_transactions on raw OECD data")
            try:
                normalized_target.parent.mkdir(parents=True, exist_ok=True)
                normalize_oecd_to_transactions(raw_oecd, normalized_target)
            except Exception as e:
                print("  Pipeline normalization failed (continuing):", e)

        txn_input = normalized_target if normalized_target.exists() else (alt_normalized if alt_normalized.exists() else None)

        if txn_input:
            txns = [normalize_transaction(r) for r in read_csv(txn_input)]
            for tx in txns:
                write_transaction(session, tx)
            print(f"  {len(txns)} transactions written.")
        else:
            print(f"  Skipping transactions: no normalized transactions found in {DATA}")

    driver.close()
    print("\n=== Done. Open http://localhost:7474 to explore the graph. ===")


if __name__ == "__main__":
    seed()