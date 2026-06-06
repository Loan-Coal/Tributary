# Makefile
ingest:
	python -m seed.seed

test:
	pytest tests/ -v

run-golden:
	python -m pipeline.run_golden

neo4j-up:
    @echo "Start Neo4j Desktop manually, then press enter"