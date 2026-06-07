"""
Module: cli
Layer: engine
Purpose: Command-line entry point for engine runs (`make run-golden`, `make demo`,
    `make snapshot-ai`). Supports offline demo via cached AI narratives.
    Prerequisites: `docker-compose up -d && make ingest`. ANTHROPIC_API_KEY only required
    when TRIBUTARY_LLM=claude (default); not needed for ollama or qwen backends.
Dependencies: sys, json, pathlib, decimal, tributary.engine, tributary.rules, tributary.common,
    tributary.graph, tributary.ai, tributary.brief, tributary.config
Used by: Makefile run-golden / demo / snapshot-ai targets
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from tributary.ai.adapter import AILayerAdapter
from tributary.ai.cached_narrator_client import CachedNarratorClient
from tributary.ai.client import ClaudeClient
from tributary.ai.narrator_client import ClaudeNarratorClient
from tributary.ai.ollama_narrator_client import OllamaNarratorClient
from tributary.brief import BriefAssembler, render_brief_markdown, render_report_markdown
from tributary.brief.group_renderer import render_group_summary_markdown
from tributary.brief.group_summary import build_group_summary
from tributary.brief.narrator import BriefNarrator
from tributary.common.errors import ConfigurationError, EngineError
from tributary.common.jurisdictions import JURISDICTION_CURRENCY
from tributary.common.logging import get_logger
from tributary.config import settings
from tributary.engine.fx_provider import FileFXRateProvider, FrankfurterFXRateProvider
from tributary.engine.runner import EngineRunner
from tributary.rules.loader import JSONRulePackLoader

logger = get_logger(__name__)

_GOLDEN_REFERENCE_YEAR = 2025
_OUTPUT_DIR = Path("output")
_FX_RATES_PATH = Path("data/golden/fx_rates.json")
_AI_CACHE_PATH = Path("data/golden/ai_cache/narratives.json")


def _load_fx_map() -> tuple[dict[str, Decimal], str]:
    """Load currency → HKD rates, using live ECB rates when TRIBUTARY_FX_LIVE=1.

    Tries the live frankfurter.app provider first (if configured), then falls back
    to the static golden-scenario file.

    Returns:
        Tuple of (rates_dict, source_label) where rates_dict maps ISO 4217 currency
        code → HKD per one unit, and source_label describes the data origin for headers.
    """
    currencies = [c for c in JURISDICTION_CURRENCY.values() if c != "HKD"]

    if settings.FX_LIVE:
        live = FrankfurterFXRateProvider(cache_minutes=settings.FX_CACHE_MINUTES)
        rates = live.get_rates(currencies)
        if rates:
            logger.info("FX rates fetched live", extra={"source": "frankfurter.app", "currencies": currencies})
            return {"HKD": Decimal("1"), **rates}, live.rate_source_label()
        logger.warning("Live FX fetch returned no rates; falling back to file")

    file_provider = FileFXRateProvider(_FX_RATES_PATH)
    rates = file_provider.get_rates(currencies)
    fx: dict[str, Decimal] = {"HKD": Decimal("1"), **rates}
    return fx, file_provider.rate_source_label()


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

    # notifications_min_severity="OFF" suppresses schema advisory warnings
    # (e.g. "property key does not exist" for optional nullable properties).
    driver = neo4j.GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        notifications_min_severity="OFF",
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


def _build_live_narrator_client() -> object:
    """Construct a live NarratorClientProtocol using the configured LLM backend.

    Mirrors _build_llm_client() but returns a narrator client (plain-string output)
    rather than a structured AILayerOutput client.

    Returns:
        A NarratorClientProtocol implementation for the configured backend.
    Raises:
        EngineError: If the selected backend cannot be initialised.
    """
    backend = settings.LLM_BACKEND.lower()
    if backend == "ollama":
        logger.info(
            "AI narrator live mode (writes to cache)",
            extra={"backend": "ollama", "model": settings.OLLAMA_MODEL},
        )
        return OllamaNarratorClient(model=settings.OLLAMA_MODEL, base_url=settings.OLLAMA_BASE_URL)

    if backend == "qwen":
        # Qwen uses the same Ollama-compatible API when served via ollama; fall through
        # to Claude if running natively. Treat qwen-via-ollama as ollama backend.
        logger.info(
            "AI narrator live mode (writes to cache)",
            extra={"backend": "qwen-via-ollama", "model": settings.OLLAMA_MODEL},
        )
        return OllamaNarratorClient(model=settings.OLLAMA_MODEL, base_url=settings.OLLAMA_BASE_URL)

    try:
        client = ClaudeNarratorClient(api_key=settings.ANTHROPIC_API_KEY)
        logger.info("AI narrator live mode (writes to cache)", extra={"backend": "claude"})
        return client
    except Exception as exc:
        raise EngineError(
            "Cannot initialise Claude narrator. Ensure ANTHROPIC_API_KEY is set, "
            "or set TRIBUTARY_LLM=ollama to use a local model."
        ) from exc


def _build_narrator(command: str) -> BriefNarrator | None:
    """Construct the BriefNarrator according to the current settings.

    Four modes:
    - AI_ENABLED=False → narrator=None (engine-only briefs, no prose)
    - AI_ENABLED=True + AI_CACHE_ONLY=True + command!=snapshot_ai → read-only cache
    - AI_ENABLED=True + AI_CACHE_ONLY=False → write-through cache wrapping live backend
    - command==snapshot_ai → always write-through (overrides AI_CACHE_ONLY) to populate cache

    Args:
        command: The CLI command being executed (snapshot_ai bypasses read-only mode).
    Returns:
        BriefNarrator wired to the appropriate client, or None for offline mode.
    """
    if not settings.AI_ENABLED:
        logger.info("AI narrator disabled (TRIBUTARY_AI_ENABLED not set)")
        return None

    if settings.AI_CACHE_ONLY and command != "snapshot_ai":
        logger.info("AI narrator in cache-only mode (TRIBUTARY_AI_CACHE_ONLY=1)")
        client: object = CachedNarratorClient(
            underlying=None,
            cache_path=_AI_CACHE_PATH,
            read_only=True,
        )
    else:
        underlying = _build_live_narrator_client()
        client = CachedNarratorClient(
            underlying=underlying,
            cache_path=_AI_CACHE_PATH,
            read_only=False,
        )

    return BriefNarrator(llm_client=client)  # type: ignore[arg-type]


def _write_outputs(
    briefs: list,
    report: object,
    fx_map: dict[str, Decimal],
    fx_source: str,
    results: list,
    entities: dict,
) -> None:
    """Write brief markdown files, conflict report, and group summary to output/.

    Args:
        briefs: List of FilingBrief objects.
        report: CrossBorderReport object.
        fx_map: Currency → HKD rate mapping for local-currency rendering.
        fx_source: Human-readable label for the FX rate source shown in brief headers.
        results: List of EngineRunResult objects (for group summary aggregation).
        entities: Dict of entity_id → EntityRecord (for group summary names/jurisdictions).
    """
    _OUTPUT_DIR.mkdir(exist_ok=True)
    for brief in briefs:
        jur = brief.jurisdiction
        local_currency = JURISDICTION_CURRENCY.get(jur, "HKD")
        fx_rate = fx_map.get(local_currency, Decimal("1"))
        path = _OUTPUT_DIR / f"{brief.entity_id}_brief.md"
        path.write_text(
            render_brief_markdown(brief, local_currency, fx_rate, fx_source), encoding="utf-8"
        )
        logger.info("Wrote brief", extra={"path": str(path), "currency": local_currency})
    report_path = _OUTPUT_DIR / "conflict_report.md"
    report_path.write_text(render_report_markdown(report), encoding="utf-8")
    logger.info("Wrote conflict report", extra={"path": str(report_path)})
    group_summary = build_group_summary(results, entities)
    summary_path = _OUTPUT_DIR / "GROUP_SUMMARY.md"
    summary_path.write_text(
        render_group_summary_markdown(group_summary, fx_map, fx_source), encoding="utf-8"
    )
    logger.info("Wrote group summary", extra={"path": str(summary_path)})


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
    narrator = _build_narrator(command)
    assembler = BriefAssembler(narrator=narrator)
    entities = {e.entity_id: e for e in reader.get_all_entities()}
    briefs = [assembler.assemble(r, entities[r.entity_id]) for r in results]
    report = assembler.assemble_report(briefs)
    fx_map, fx_source = _load_fx_map()
    _write_outputs(briefs, report, fx_map, fx_source, results, entities)
    logger.info(
        "Run complete",
        extra={"command": command, "entities": len(results), "output_dir": str(_OUTPUT_DIR)},
    )


def demo() -> None:
    """Run the pipeline in offline-safe mode using cached AI narratives.

    Prerequisites:
        - docker-compose up -d && make ingest  (Neo4j must be seeded)
        - Run `make snapshot-ai` once (with ANTHROPIC_API_KEY) to populate the cache.
          Without the cache, narrative sections show a placeholder message.
    """
    _run("demo")


def run_golden() -> None:
    """Run the full production pipeline on the golden scenario with live AI.

    Prerequisites:
        - docker-compose up -d && make ingest  (Neo4j must be seeded)
        - ANTHROPIC_API_KEY set in environment or .env
    """
    _run("run_golden")


def snapshot_ai() -> None:
    """Run with live AI and write all narratives to the cache.

    After this, `make demo` runs fully offline. Requires the configured LLM
    backend to be reachable (Ollama, Qwen, or Claude per TRIBUTARY_LLM).
    """
    _run("snapshot_ai")


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
        elif command in ("snapshot_ai", "snapshot-ai"):
            snapshot_ai()
        else:
            raise EngineError(
                f"Unknown command: {command!r}. Use 'demo', 'run_golden', or 'snapshot_ai'."
            )
    except (EngineError, ConfigurationError) as exc:
        logger.error("CLI failed", extra={"command": command, "error": str(exc)})
        sys.exit(1)


if __name__ == "__main__":
    main()
