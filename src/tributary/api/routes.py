"""
Module: routes
Layer: api
Purpose: FastAPI route handlers for the Tributary demo UI. Exposes CSV preview,
    SSE pipeline run, graph data, and brief content endpoints.
Dependencies: fastapi, pathlib, csv, tributary.api.demo_runner, tributary.api.graph_data
Used by: tributary.api.app (registered on /api prefix)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from tributary.api.demo_runner import run_demo_pipeline
from tributary.api.graph_data import get_graph_data
from tributary.common.errors import EngineError

router = APIRouter()

_RAW_DIR = Path("data/raw")
_OUTPUT_DIR = Path("output")

_CSV_FILES: dict[str, str] = {
    "HK": "lenovo_consolidated_hong_kong_0992HK.csv",
    "DE": "lenovo_consolidated_germany_LHL_F.csv",
    "US": "lenovo_consolidated_united_states_LNVGY.csv",
}

_BRIEF_IDS = ["MERID-HK", "MERID-DE", "MERID-FR", "MERID-US"]


@router.get("/demo/csvpreview")
async def csv_preview() -> dict[str, Any]:
    """Return the first 8 rows of each raw balance-sheet CSV.

    Returns:
        Dict mapping jurisdiction code to {headers, rows} preview dicts.
    Raises:
        HTTPException 404: If no CSV files are found in data/raw/.
    """
    result: dict[str, Any] = {}
    for jur, filename in _CSV_FILES.items():
        path = _RAW_DIR / filename
        if not path.exists():
            continue
        rows: list[list[str]] = []
        headers: list[str] = []
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            for i, row in enumerate(reader):
                if i == 0:
                    headers = row
                elif i <= 8:
                    rows.append(row)
                else:
                    break
        result[jur] = {"filename": filename, "headers": headers, "rows": rows}
    if not result:
        raise HTTPException(status_code=404, detail="No CSV files found in data/raw/")
    return result


@router.post("/demo/run")
async def run_demo() -> StreamingResponse:
    """Trigger the full demo pipeline and stream SSE progress events.

    Runs ingestion → engine (cached AI) → brief assembly.
    Each stage emits a JSON event via Server-Sent Events.

    Returns:
        StreamingResponse with content-type text/event-stream.
    """

    async def _generate():
        for event in run_demo_pipeline():
            yield event

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/demo/graph")
async def graph_data() -> dict[str, Any]:
    """Return entity and transaction graph in vis.js format.

    Returns:
        Dict with 'nodes' (entity list) and 'edges' (ownership + flow list).
    Raises:
        HTTPException 503: If Neo4j is unreachable or graph is empty.
    """
    try:
        return get_graph_data()
    except EngineError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/demo/briefs")
async def get_briefs() -> dict[str, Any]:
    """Return all rendered brief markdown files from output/.

    Returns:
        Dict mapping entity_id / 'conflict' / 'group_summary' to markdown strings.
    Raises:
        HTTPException 404: If output/ directory has no brief files.
    """
    output: dict[str, str] = {}
    for entity_id in _BRIEF_IDS:
        path = _OUTPUT_DIR / f"{entity_id}_brief.md"
        if path.exists():
            output[entity_id] = path.read_text(encoding="utf-8")
    conflict_path = _OUTPUT_DIR / "conflict_report.md"
    if conflict_path.exists():
        output["conflict"] = conflict_path.read_text(encoding="utf-8")
    summary_path = _OUTPUT_DIR / "GROUP_SUMMARY.md"
    if summary_path.exists():
        output["group_summary"] = summary_path.read_text(encoding="utf-8")
    if not output:
        raise HTTPException(
            status_code=404,
            detail="No briefs found — run the pipeline first",
        )
    return output
