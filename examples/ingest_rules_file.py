"""Ingest a rules JSON file into the local SQLite rules DB.
Usage: PYTHONPATH=src python examples/ingest_rules_file.py examples/Datasets/hk_dipn21_rules.json
"""
import json
import sys
from pathlib import Path
from tributary.rules.db import init_db, ingest_rules

def main():
    if len(sys.argv) < 2:
        print("Usage: python examples/ingest_rules_file.py <path-to-json>")
        sys.exit(2)
    src = Path(sys.argv[1])
    if not src.exists():
        print(f"File not found: {src}")
        sys.exit(2)
    root = Path(__file__).parent
    db_path = root / "rules.db"
    init_db(db_path)
    with src.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    ingest_rules(db_path, data)
    print(f"Ingested {len(data)} rules into {db_path}")

if __name__ == '__main__':
    main()
