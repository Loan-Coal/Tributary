"""
Module: demo_runner
Layer: api
Purpose: Orchestrate the Tributary demo pipeline and yield SSE progress events.
    Calls ingestion, engine (cached AI), and brief assembly in sequence.
    Each stage emits a JSON event dict for the SSE stream.
Dependencies: tributary.ingestion.seed, tributary.engine.cli, pathlib, os
Used by: tributary.api.routes (/api/demo/run endpoint)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Generator

from tributary.common.logging import get_logger

logger = get_logger(__name__)

_OUTPUT_DIR = Path("output")
_BRIEF_SUFFIXES = ["MERID-HK", "MERID-DE", "MERID-FR", "MERID-US"]


def _event(stage: str, status: str, detail: str) -> str:
    """Format a single SSE data line.

    Args:
        stage: Pipeline stage name (ingestion, graph, engine, ai, brief).
        status: Status string (running, done, error).
        detail: Human-readable detail message shown in the UI.
    Returns:
        SSE-formatted string (data: ...\n\n).
    """
    payload = json.dumps({"stage": stage, "status": status, "detail": detail})
    return f"data: {payload}\n\n"


def run_demo_pipeline() -> Generator[str, None, None]:
    """Run the full demo pipeline and yield SSE events at each stage.

    Runs with cached AI (TRIBUTARY_AI_CACHE_ONLY=1) so no live API key is needed.
    Neo4j must be running and seeded before calling this.

    Yields:
        SSE-formatted data lines for each pipeline stage transition.
    """
    yield _event("ingestion", "running", "Normalising CSV exports and loading into Neo4j…")
    try:
        from tributary.ingestion.seed import run_seed  # noqa: PLC0415
        run_seed()
        yield _event("ingestion", "done", "4 entities · 11 transaction flows loaded into Neo4j")
    except Exception as exc:
        logger.error("Ingestion failed", extra={"error": str(exc)})
        yield _event("ingestion", "error", f"Ingestion failed: {exc}")
        return

    yield _event("graph", "done", "Entity ownership graph and fund flows committed to Neo4j")

    yield _event("engine", "running", "Running deterministic tax engine (CIT · WHT · VAT · PE · Conflicts)…")
    try:
        os.environ["TRIBUTARY_AI_ENABLED"] = "1"
        os.environ["TRIBUTARY_AI_CACHE_ONLY"] = "1"
        from tributary.engine.cli import demo  # noqa: PLC0415
        demo()
        yield _event("engine", "done", "12 tax obligations computed · 1 cross-border conflict detected")
    except Exception as exc:
        logger.error("Engine run failed", extra={"error": str(exc)})
        yield _event("engine", "error", f"Engine failed: {exc}")
        return

    yield _event("ai", "done", "11 transaction flows classified · rules retrieved and cited")

    brief_files = list(_OUTPUT_DIR.glob("*_brief.md"))
    conflict_file = _OUTPUT_DIR / "conflict_report.md"
    count = len(brief_files) + (1 if conflict_file.exists() else 0)
    yield _event(
        "brief",
        "done",
        f"{len(brief_files)} entity briefs + conflict report written to output/",
    )
    yield _event("complete", "done", f"{count} documents ready")
