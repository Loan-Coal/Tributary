.PHONY: test test-engine ingest run demo snapshot-ai check-layers lint deadcode audit-mechanical run-golden

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

run: ingest
	set TRIBUTARY_AI_ENABLED=1 && python -m tributary.engine.cli run_golden

# Alias kept for muscle-memory; remove once everyone is using `make run`.
run-golden: run

# Demo: offline-safe — uses cached AI narratives; never hits the LLM live.
# Run `make snapshot-ai` once to pre-populate the cache.
demo: ingest
	set TRIBUTARY_AI_ENABLED=1 && set TRIBUTARY_AI_CACHE_ONLY=1 && python -m tributary.engine.cli demo

# One-time: generate AI narratives and write them to data/golden/ai_cache/narratives.json.
# Requires the configured LLM backend (TRIBUTARY_LLM=ollama|qwen|claude in .env).
# After this, `make demo` runs fully offline.
snapshot-ai: ingest
	set TRIBUTARY_AI_ENABLED=1 && python -m tributary.engine.cli snapshot_ai

check-layers:
	python scripts/check_layers.py
