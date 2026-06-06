.PHONY: test test-engine ingest run-golden demo check-layers lint deadcode audit-mechanical

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

run-golden:
	python -m tributary.engine.cli run_golden

demo:
	python -m tributary.engine.cli demo

check-layers:
	python scripts/check_layers.py
