"""
Module: cli
Layer: engine
Purpose: Command-line entry point for engine runs (`make run-golden`, `make demo`).
    Both commands follow the same production path: Neo4j graph layer + real Claude AI.
    Prerequisites: `docker-compose up -d && make ingest`, ANTHROPIC_API_KEY set.
Dependencies: sys, pathlib, tributary.engine, tributary.rules, tributary.common,
    tributary.graph, tributary.ai, tributary.brief, tributary.config
Used by: Makefile run-golden / demo targets
"""
from __future__ import annotations

import sys
from pathlib import Path

from tributary.ai.adapter import AILayerAdapter
from tributary.ai.client import ClaudeClient
from tributary.brief import BriefAssembler, render_brief_markdown, render_report_markdown
from tributary.common.errors import ConfigurationError, EngineError
from tributary.common.logging import get_logger
from tributary.config import settings
from tributary.engine.runner import EngineRunner
from tributary.rules.loader import JSONRulePackLoader

logger = get_logger(__name__)

_GOLDEN_REFERENCE_YEAR = 2025
_OUTPUT_DIR = Path("output")


def _build_graph_dependencies() -> tuple[object, object]:
    """Construct Neo4j-backed GraphReader/GraphWriter.

    Returns:
        (reader, writer) implementing the graph protocols.
    Raises:
        EngineError: If the neo4j package is unavailable or Neo4j is unreachable.
    """
    try:
        import neo4j  # noqa: PLC0415

        from tributary.graph.readers import Neo4jGraphReader  # noqa: PLC0415
        from tributary.graph.writer_engine import Neo4jGraphWriter  # noqa: PLC0415
    except ImportError as exc:
        raise EngineError(
            "Neo4j package unavailable. Install with `pip install neo4j`."
        ) from exc

    driver = neo4j.GraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    try:
        driver.verify_connectivity()
    except Exception as exc:
        raise EngineError(
            "Cannot reach Neo4j. Run `docker-compose up -d && make ingest` first."
        ) from exc

    return Neo4jGraphReader(driver), Neo4jGraphWriter(driver)


def _build_llm_client() -> object:
    """Construct the LLM client selected by the TRIBUTARY_LLM environment variable.

    Supported values (case-insensitive):
        claude  — Anthropic Claude via API (default); requires ANTHROPIC_API_KEY.
        qwen    — Local Qwen model via HuggingFace transformers; requires TRIBUTARY_QWEN_MODEL
                  or defaults to Qwen/Qwen3-30B-A3B-Instruct-2507.

    Returns:
        An object satisfying LLMClientProtocol.
    Raises:
        EngineError: If the selected backend cannot be initialised.
    """
    backend = settings.LLM_BACKEND.lower()
    if backend == "ollama":
        from tributary.ai.ollama_client import OllamaClient  # noqa: PLC0415
        model = settings.OLLAMA_MODEL
        base_url = settings.OLLAMA_BASE_URL
        logger.info("Using Ollama", extra={"model": model, "url": base_url})
        return OllamaClient(model=model, base_url=base_url)

    if backend == "qwen":
        try:
            from tributary.ai.qwen_client import QwenLocalClient  # noqa: PLC0415
        except ImportError as exc:
            raise EngineError(
                "QwenLocalClient requires 'transformers' and 'torch'. "
                "Install them or set TRIBUTARY_LLM=ollama."
            ) from exc
        model = settings.QWEN_MODEL
        logger.info("Using local Qwen model", extra={"model": model})
        try:
            return QwenLocalClient(model_name=model)
        except Exception as exc:
            raise EngineError(f"Failed to load Qwen model '{model}': {exc}") from exc

    # Default: Claude
    try:
        return ClaudeClient(api_key=settings.ANTHROPIC_API_KEY)
    except Exception as exc:
        raise EngineError(
            "Cannot initialise Claude client. Ensure ANTHROPIC_API_KEY is set and "
            "the anthropic package is installed."
        ) from exc


def _build_ai_layer(loader: JSONRulePackLoader) -> AILayerAdapter:
    """Construct the AI layer adapter wrapping the configured LLM client.

    Args:
        loader: Rule-pack loader passed through to the adapter for rule grounding.
    Returns:
        AILayerAdapter wrapping the selected LLM client.
    Raises:
        EngineError: If the selected backend cannot be initialised.
    """
    return AILayerAdapter(llm_client=_build_llm_client(), rule_loader=loader)


def _write_outputs(briefs: list, report: object) -> None:
    """Write brief markdown files and the conflict report to output/.

    Args:
        briefs: List of FilingBrief objects.
        report: CrossBorderReport object.
    """
    _OUTPUT_DIR.mkdir(exist_ok=True)
    for brief in briefs:
        path = _OUTPUT_DIR / f"{brief.entity_id}_brief.md"
        path.write_text(render_brief_markdown(brief), encoding="utf-8")
        logger.info("Wrote brief", extra={"path": str(path)})
    report_path = _OUTPUT_DIR / "conflict_report.md"
    report_path.write_text(render_report_markdown(report), encoding="utf-8")
    logger.info("Wrote conflict report", extra={"path": str(report_path)})


def _run(command: str) -> None:
    """Execute the production engine run (shared by demo and run_golden).

    Validates config, connects to Neo4j, wires the real Claude AI layer, runs
    the deterministic engine, assembles briefs, and writes markdown to output/.

    Args:
        command: Name of the invoking command (for log context only).
    Raises:
        ConfigurationError: If required environment variables are missing.
        EngineError: If Neo4j is unreachable or the Claude client cannot be built.
    """
    settings.validate()
    reader, writer = _build_graph_dependencies()
    loader = JSONRulePackLoader()
    ai = _build_ai_layer(loader)
    runner = EngineRunner(reader, writer, ai, loader, _GOLDEN_REFERENCE_YEAR)
    results = runner.run()
    assembler = BriefAssembler(narrator=None)
    entities = {e.entity_id: e for e in reader.get_all_entities()}
    briefs = [assembler.assemble(r, entities[r.entity_id]) for r in results]
    report = assembler.assemble_report(briefs)
    _write_outputs(briefs, report)
    logger.info(
        "Run complete",
        extra={"command": command, "entities": len(results), "output_dir": str(_OUTPUT_DIR)},
    )


def demo() -> None:
    """Run the full production pipeline on the golden scenario.

    Prerequisites:
        - docker-compose up -d && make ingest  (Neo4j must be seeded)
        - ANTHROPIC_API_KEY set in environment or .env
    """
    _run("demo")


def run_golden() -> None:
    """Alias for demo(); runs the same production pipeline."""
    _run("run_golden")


def main(argv: list[str] | None = None) -> None:
    """Dispatch a CLI command.

    Args:
        argv: Command arguments; defaults to sys.argv[1:].
    Raises:
        SystemExit: With code 1 on EngineError or ConfigurationError.
    """
    args = argv if argv is not None else sys.argv[1:]
    command = args[0] if args else "demo"
    try:
        if command == "demo":
            demo()
        elif command in ("run_golden", "run-golden"):
            run_golden()
        else:
            raise EngineError(f"Unknown command: {command!r}. Use 'demo' or 'run_golden'.")
    except (EngineError, ConfigurationError) as exc:
        logger.error("CLI failed", extra={"command": command, "error": str(exc)})
        sys.exit(1)


if __name__ == "__main__":
    main()
