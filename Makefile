.PHONY: test test-engine ingest run-golden demo snapshot-ai check-layers lint deadcode audit-mechanical

test:
	pytest tests/ --cov=src/tributary --cov-report=term-missing -q

lint:
	ruff check src/ tests/

deadcode:
	vulture

# Cheap deterministic gate the /audit skill runs before spending model tokens.
audit-mechanical: check-layers lint deadcode
	@echo "mechanical gate complete — see ruff/vulture output above"

test-engine:
	pytest tests/ -k "engine" --cov=src/tributary/engine --cov-report=term-missing -q

ingest:
	python -m tributary.ingestion.cli

run-golden: ingest
	TRIBUTARY_AI_ENABLED=1 python -m tributary.engine.cli run_golden

# Demo: offline-safe — uses cached AI narratives; never hits Claude live.
# Run `make snapshot-ai` once (with ANTHROPIC_API_KEY) to pre-populate the cache.
demo: ingest
	TRIBUTARY_AI_ENABLED=1 TRIBUTARY_AI_CACHE_ONLY=1 python -m tributary.engine.cli demo

# One-time: generate AI narratives and write them to data/golden/ai_cache/narratives.json.
# Requires the configured LLM backend (TRIBUTARY_LLM=ollama|qwen|claude in .env).
# After this, `make demo` runs fully offline.
snapshot-ai: ingest
	TRIBUTARY_AI_ENABLED=1 python -m tributary.engine.cli snapshot_ai

check-layers:
	python scripts/check_layers.py
