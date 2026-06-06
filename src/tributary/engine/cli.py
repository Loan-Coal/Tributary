"""
Module: cli
Layer: engine
Purpose: Command-line entry point for engine runs (`make run-golden`, `make demo`). Wires the
    real rule-pack loader and the attribution stub. The graph reader/writer is the Wave-2 graph
    layer (Neo4j); until it lands, this entry reports clearly rather than guessing. The full
    pipeline is proven end-to-end by tests/integration/test_engine_golden.py using in-memory fakes.
Dependencies: sys, tributary.engine, tributary.rules, tributary.common
Used by: Makefile run-golden / demo targets
"""
from __future__ import annotations

import sys

from tributary.common.errors import EngineError
from tributary.common.logging import get_logger

logger = get_logger(__name__)

_GOLDEN_REFERENCE_YEAR = 2025


def _build_graph_dependencies() -> tuple[object, object]:
    """Construct the Neo4j-backed GraphReader/GraphWriter (Wave 2 graph layer).

    Returns:
        (reader, writer) implementing the graph protocols.
    Raises:
        EngineError: Until the Wave-2 graph layer is available.
    """
    try:
        from tributary.graph.readers import Neo4jGraphReader  # type: ignore
        from tributary.graph.writer_engine import Neo4jGraphWriter  # type: ignore
    except ImportError as exc:
        raise EngineError(
            "run-golden needs the Wave-2 graph layer (graph/readers.py, graph/writer_engine.py). "
            "The engine pipeline is fully exercised today by tests/integration/test_engine_golden.py "
            "with in-memory fakes — run `make test`."
        ) from exc
    return Neo4jGraphReader(), Neo4jGraphWriter()


def run_golden() -> None:
    """Run the engine end-to-end on the golden scenario against the real graph layer."""
    from tributary.engine.runner import EngineRunner
    from tributary.engine.attribution_stub import AttributionStub
    from tributary.rules.loader import JSONRulePackLoader

    reader, writer = _build_graph_dependencies()
    runner = EngineRunner(reader, writer, AttributionStub(), JSONRulePackLoader(), _GOLDEN_REFERENCE_YEAR)
    results = runner.run()
    logger.info("Golden engine run complete", extra={"entities": len(results)})


def main(argv: list[str] | None = None) -> None:
    """Dispatch a CLI command.

    Args:
        argv: Command arguments; defaults to sys.argv[1:].
    Raises:
        SystemExit: With code 1 on EngineError.
    """
    args = argv if argv is not None else sys.argv[1:]
    command = args[0] if args else "run_golden"
    try:
        if command in ("run_golden", "demo"):
            run_golden()
        else:
            raise EngineError(f"Unknown command: {command}")
    except EngineError as exc:
        logger.error("Engine CLI failed", extra={"error": str(exc)})
        sys.exit(1)


if __name__ == "__main__":
    main()
