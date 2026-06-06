.PHONY: test test-engine ingest run-golden demo check-layers

test:
	pytest tests/ --cov=src/tributary --cov-report=term-missing -q

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
