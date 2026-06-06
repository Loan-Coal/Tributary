import csv
import json
from pathlib import Path
from typing import List


def read_csv(path: Path) -> List[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> List[dict]:
    return json.loads(path.read_text())
