"""
Seed the local rules DB from example JSON files.
For demo purposes this script reads `examples/input_transaction.json` and ingests
the `rule_summaries` array into the DB, assigning jurisdictions when available.
"""
import json
from pathlib import Path
from tributary.rules.db import init_db, ingest_rules


def main():
    root = Path(__file__).parent
    db_path = root / "rules.db"
    init_db(db_path)
    input_path = root / "input_transaction.json"
    with input_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    rules = payload.get("rule_summaries", [])
    # If the payload provides candidate_jurisdictions, assign to each rule for demo
    candidate_jurisdictions = payload.get("transaction_context", {}).get("candidate_jurisdictions", [])
    ingestable = []
    for r in rules:
        rec = dict(r)
        rec["jurisdiction"] = candidate_jurisdictions[0] if candidate_jurisdictions else None
        ingestable.append(rec)
    ingest_rules(db_path, ingestable)
    print(f"Seeded rules DB at: {db_path}")


if __name__ == "__main__":
    main()
