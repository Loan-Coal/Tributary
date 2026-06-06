# Tributary — Hackathon Roadmap

**Goal:** End-to-end demo: golden multinational → 3–4 fully cited filing briefs + cross-border conflict report.

Each phase is a vertical slice — the system stays runnable after every phase. The deterministic
engine is built and tested BEFORE the AI is wired in, so failures are isolatable.

---

## Phase 0 — Foundations & golden scenario

**Deliverable:**
- Repo structure; normalized data schema (Entity, Account, Transaction, Counterparty,
  Jurisdiction — including `fx_rate` and `fx_date` fields).
- Neo4j running (Docker).
- 3–4 jurisdictions chosen (HK, one EU member, US, SG or UK).
- Hand-authored **golden multinational**: ~10–15 transaction flows across the chosen countries,
  with expected obligations, expected flags, and a **planted cross-border conflict** worked
  out by hand.

**Mocked vs real:** all synthetic data; no rules yet.
**Milestone:** golden company loads into Neo4j; structure is traversable.
**Depends on:** —

### Tasks
- [ ] **P0.1** — scaffold repo, Docker Compose (Neo4j), Makefile with `make test`, `make ingest`, `make run-golden`
- [ ] **P0.2** — define normalized data schema as Pydantic models in `common/models.py`
- [ ] **P0.3** — decide jurisdictions; document the choice in `DECISIONS.md`
- [ ] **P0.4** — author golden mock files in `data/golden/` (CSV/JSON GL export format)
- [ ] **P0.5** — hand-compute expected obligations, thresholds, deadlines → `data/golden/EXPECTED.md`
- [ ] **P0.6** — design and document the planted cross-border conflict in `DECISIONS.md`
- [ ] **P0.7** — seed graph from golden files; verify traversal in Neo4j Browser

---

## Phase 1 — Ingestion & normalization

**Deliverable:** source-agnostic ingest (mock GL/bank CSV/JSON) → normalized records →
Neo4j graph writes; currency normalization with rate-date captured.

**Mocked vs real:** mock source files; real normalization + real graph writes.
**Milestone:** raw mock export in → populated graph out.
**Depends on:** P0

### Tasks
- [ ] **P1.1** — implement `ingestion/reader.py`: parse CSV/JSON mock exports to raw records
- [ ] **P1.2** — implement `ingestion/normalizer.py`: map raw → normalized `Transaction`/`Entity` models; FX normalize to base currency with `fx_date`
- [ ] **P1.3** — implement `graph/writer.py`: write normalized records to Neo4j (idempotent upsert)
- [ ] **P1.4** — integration test: golden mock files in → populated graph with correct node counts + edge types
- [ ] **P1.5** — `make ingest` wired up end-to-end

---

## Phase 2 — Rule-pack interface & country packs

**Deliverable:** the rule-pack contract + loader; handwritten country packs for the chosen
jurisdictions covering exactly what the golden scenario needs (registration thresholds, basic
rates, filing deadlines, a couple of source/treaty rules).

**Mocked vs real:** rules are placeholder-quality (public sources, possibly outdated); interface is production-grade.
**Milestone:** `get_rules(jurisdiction="HK", flow_type="revenue")` returns rules with provenance + as_of_date.
**Depends on:** P0

### Tasks
- [ ] **P2.1** — define `RulePack` and `Rule` Pydantic models + `RulePackLoader` protocol in `rules/models.py`
- [ ] **P2.2** — implement `rules/loader.py`: JSON file loader implementing the protocol
- [ ] **P2.3** — author HK rule pack JSON (`data/rules/hk.json`) — territorial income, profits tax rate, filing deadlines
- [ ] **P2.4** — author EU member rule pack JSON — VAT thresholds, CIT rate, PE rules, treaty pointers
- [ ] **P2.5** — author US rule pack JSON — worldwide income, federal CIT, state nexus triggers, withholding rates
- [ ] **P2.6** — author SG or UK rule pack JSON — territorial/residence scope, rates, deadlines
- [ ] **P2.7** — unit tests: loader returns correct rules for each jurisdiction/flow type; as_of_date and source_citation always present

---

## Phase 3 — Deterministic engine

**Deliverable:** obligation/nexus triggers, threshold booleans, aggregation, rate × base,
deadline calculation; pure, reproducible, unit-tested against golden expected values.
Jurisdiction attribution **stubbed** (manual annotations on flows) so engine is testable without AI.

**Mocked vs real:** attribution stubbed; all computation real and tested.
**Milestone:** given annotated flows, engine output matches golden EXPECTED.md values.
**Depends on:** P1, P2

### Tasks
- [ ] **P3.1** — `engine/triggers.py`: nexus/obligation trigger evaluation (boolean; reads rule packs)
- [ ] **P3.2** — `engine/thresholds.py`: threshold boolean logic (compare aggregated amounts to rule thresholds)
- [ ] **P3.3** — `engine/aggregator.py`: aggregate transactions by jurisdiction/period/flow type (no AI)
- [ ] **P3.4** — `engine/rates.py`: rate × base arithmetic (reads rate rules; emits amounts with provenance)
- [ ] **P3.5** — `engine/deadlines.py`: deadline calculation per country fiscal calendar + company accounting period
- [ ] **P3.6** — `engine/attribution_stub.py`: manual jurisdiction annotation loader (replaced by AI in P4)
- [ ] **P3.7** — unit tests for every engine function against hand-computed golden values
- [ ] **P3.8** — integration test: full engine run on golden scenario → matches EXPECTED.md

---

## Phase 4 — AI layer (grounded)

**Deliverable:** flow classification (structured output); candidate-jurisdiction attribution;
grounded rule retrieval with mandatory citation + confidence + abstention. Structured I/O
contract with the engine. Replaces P3's attribution stub.

**Mocked vs real:** real Claude calls; real packs; no AI-typed figures.
**Milestone:** flow in → classification + cited applicable rules + confidence; engine now runs on AI attributions end-to-end (minus conflict + brief).
**Depends on:** P2, P3

### Tasks
- [ ] **P4.1** — `ai/protocol.py`: define `AILayerProtocol` + `FlowClassification` + `RuleAttribution` Pydantic models
- [ ] **P4.2** — `ai/classifier.py`: classify flow nature (revenue / expense / inter-company / capital / loan) via Claude structured output
- [ ] **P4.3** — `ai/attributor.py`: attribute candidate jurisdiction(s) per flow; grounded to graph context
- [ ] **P4.4** — `ai/retriever.py`: retrieve applicable rules from packs; mandatory citation + as_of_date; abstain if insufficient info
- [ ] **P4.5** — `prompts/classify_flow.yaml`, `prompts/attribute_jurisdiction.yaml`, `prompts/retrieve_rules.yaml`
- [ ] **P4.6** — mock Claude adapter for tests
- [ ] **P4.7** — swap out attribution stub: engine now driven by AI attributions
- [ ] **P4.8** — integration test: full AI + engine pipeline on golden scenario

---

## Phase 5 — Conflict / cross-border detection

**Deliverable:** engine logic over AI jurisdiction annotations — detect base/flow claimed by
≥2 jurisdictions; flag double-tax / withholding / PE candidates; surface treaty pointers.

**Mocked vs real:** real.
**Milestone:** planted golden conflict fires and is explained.
**Depends on:** P4

### Tasks
- [ ] **P5.1** — `engine/conflict.py`: detect overlapping jurisdiction claims on the same flow/base
- [ ] **P5.2** — PE (permanent establishment) trigger detection
- [ ] **P5.3** — withholding tax exposure flag
- [ ] **P5.4** — double-tax candidate flag + treaty pointer lookup from packs
- [ ] **P5.5** — unit tests: golden planted conflict fires with correct explanation
- [ ] **P5.6** — cross-border flag report model in `common/models.py`

---

## Phase 6 — Brief assembly

**Deliverable:** per-jurisdiction brief = engine-filled numeric template + AI narrative
around fixed values; full traceability (rule + as_of_date + source transactions + confidence);
lawyer open-questions list; cross-border flag report.

**Mocked vs real:** real; AI prose wraps engine numbers only.
**Milestone:** full end-to-end run on golden company → 3–4 cited briefs + conflict report.
**Depends on:** P5

### Tasks
- [ ] **P6.1** — `brief/template.py`: per-jurisdiction brief data model (all numeric slots filled by engine)
- [ ] **P6.2** — `brief/narrator.py`: Claude generates prose narrative around engine-filled values (never restates raw figures)
- [ ] **P6.3** — `brief/assembler.py`: compose full brief — template + narrative + traceability + open questions
- [ ] **P6.4** — `brief/report.py`: cross-border flag report assembly
- [ ] **P6.5** — `prompts/brief_narrative.yaml`
- [ ] **P6.6** — `make run-golden` produces brief files in `output/`
- [ ] **P6.7** — integration test: briefs contain all required sections; all numeric fields sourced from engine; all recommendations cite a rule

---

## Phase 7 — Demo hardening

**Deliverable:** cache/freeze AI outputs for the golden dataset; UI (minimal web or terminal)
showing briefs with as_of_dates, citations, confidence, the conflict highlight, and graph view;
rehearsed answers to "who pays" and "what breaks at scale".

**Mocked vs real:** cached AI for reliability.
**Milestone:** repeatable, offline-safe live demo.
**Depends on:** P6

### Tasks
- [ ] **P7.1** — snapshot AI outputs for golden dataset to `data/golden/ai_cache/`
- [ ] **P7.2** — `make demo` runs on cached AI, never hits Claude live
- [ ] **P7.3** — brief output UI (terminal or minimal web): as_of_dates, citations, confidence, conflict highlight
- [ ] **P7.4** — Neo4j graph view accessible (browser) showing entity ownership + transaction flows
- [ ] **P7.5** — rehearse demo; document Q&A in `project-harness/DEMO_SCRIPT.md`

---

## Expansion roadmap (post-hackathon, reference only)

| Code | Expansion | Notes |
|------|-----------|-------|
| E1 | Statutory form filling | Brief fields → country statutory forms (HK BIR51 first). Scope-explosion zone — isolate. |
| E2 | Real licensed rule data | IBFD / Bloomberg Tax / Thomson Reuters ONESOURCE behind existing pack interface |
| E3 | Real ingestion connectors | Xero / QuickBooks / ERP; HK Open API / CDI consented bank rails |
| E4 | Tax-saving / planning | Advice-heavy, regulated — design only with professional sign-off |

---

## Session Log

| # | Date | Phase | What was done | Exit state |
|---|------|-------|---------------|------------|
| 1 | 2026-06-06 | setup | Copied + updated harness from NPCSystem | Harness ready, no code yet |
