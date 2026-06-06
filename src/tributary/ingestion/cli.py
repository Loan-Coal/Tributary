"""
Module: cli
Layer: ingestion
Purpose: Command-line entry point for ingestion operations.
Dependencies: tributary.ingestion.seed, sys
Used by: Makefile `make ingest` target
"""
from __future__ import annotations

import sys

from tributary.common.errors import IngestionError
from tributary.common.logging import get_logger
from tributary.ingestion.seed import run_seed

logger = get_logger(__name__)


def main() -> None:
    """Run the golden data seed.

    Raises:
        SystemExit: With exit code 1 on IngestionError.
    """
    try:
        run_seed()
        logger.info("Seed complete")
    except IngestionError as exc:
        logger.error("Seed failed", extra={"error": str(exc)})
        sys.exit(1)


if __name__ == "__main__":
    main()
