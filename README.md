# Tributary

Cross-border tax copilot for multinationals. Produces per-jurisdiction, fully cited **filing briefs** for a lawyer or tax professional to review.

Built for the HKTE Euro Hackathon Munich 2026.


---

## What it does

Ingest multi-country GL/bank exports → run a deterministic tax engine → wrap engine-computed numbers with grounded AI narrative → output 3–4 cited filing briefs + a cross-border conflict report.

**The AI never emits figures.** All amounts, rates, thresholds, and deadlines are engine-computed and rule-cited.

---

## Stack

| Component | Technology |
|-----------|-----------|
| API / orchestration | FastAPI + Uvicorn |
| Graph store | Neo4j 5 (Docker) |
| Rule packs | Versioned JSON behind a pluggable loader |
| Deterministic engine | Pure Python — no AI calls |
| AI layer | Anthropic Claude / local Qwen — grounded narrative only |
| Tests | pytest (179 passing) |

---

## Quick start

```bash
docker-compose up -d          # start Neo4j
make ingest                   # seed golden scenario
make test                     # full unit suite
make test-engine              # engine-only tests
make run-golden               # end-to-end run on Meridian Group
make demo                     # offline demo (cached AI)
```

---

## Golden scenario — Meridian Group

Three entities: MERID-HK (Hong Kong parent) → MERID-DE (Germany) → MERID-FR (France).

Planted conflict: **the PE Triangle** — MERID-DE employees spend 185 days in France, triggering a service PE under the DE-FR DTA. France and Germany simultaneously claim the same ~HKD 1,400,000 income base. Treaty resolution: DE-FR DTA Art.23 (exemption method) — Germany exempts the PE income; France taxes it alone; residual double-tax = 0.

Hand-computed expected obligations in `data/golden/EXPECTED.md`.

---

## Architecture

```
api/        → FastAPI routes
brief/      → per-jurisdiction briefs + conflict report
ai/         → grounded classification, attribution, rule retrieval (no figures)
engine/     → deterministic CIT, WHT, VAT, trade tax, PE, conflict, group relief
rules/      → versioned JSON rule packs (HK, DE, FR, treaties)
graph/      → Neo4j read/write protocols
ingestion/  → GL/bank export parsing and normalization
prompts/    → versioned YAML prompt files
config/     → settings and env validation
common/     → Pydantic models, protocols, exceptions, logging
```

Dependencies flow downward only. Full rules in `project-harness/CLAUDE.md`.

---

## Project docs

| File | Contents |
|------|----------|
| `project-harness/ROADMAP.md` | Wave-by-wave build plan |
| `project-harness/DECISIONS.md` | Architecture decision records (DEC-001–DEC-021) |
| `project-harness/ISSUES.md` | Persistent issue log |
| `project-harness/FEATURES.md` | Feature status tracker |
| `project-harness/NEXT_SESSION.md` | Next session handoff |
| `data/golden/EXPECTED.md` | Hand-computed golden figures |

---

## AI Layer Demo

```bash
cd /Tributary

# Qwen backend
python examples/run_ai_layer.py --backend qwen --limit 5

# Deterministic backend
python examples/run_ai_layer.py --backend deterministic --limit 10
```
