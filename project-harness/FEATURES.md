# Tributary — Feature Compilation

**As of:** 2026-06-06 (project start — harness setup only).

Legend: ✅ implemented + tested · 🟡 implemented, no dedicated test · ⬜ not started · ⚠️ known issue (see ISSUES.md)

---

## A. Ingestion & normalization

| Capability | Status |
|-----------|--------|
| Parse CSV/JSON mock GL/bank exports | ⬜ |
| Normalize to canonical `Transaction` / `Entity` / `Account` / `Counterparty` / `Jurisdiction` models | ⬜ |
| Currency normalization to base reporting currency with `fx_rate` + `fx_date` | ⬜ |
| Idempotent Neo4j upsert (entities, accounts, transactions, counterparties, jurisdictions) | ⬜ |

---

## B. Graph store (Neo4j)

| Capability | Status |
|-----------|--------|
| Entity nodes (holdco / subsidiary / branch) | ⬜ |
| Ownership edges `[:OWNS {pct}]` | ⬜ |
| Account, Transaction, Counterparty, Jurisdiction nodes | ⬜ |
| Relationship edges (HOLDS, RECORDS, WITH, RESIDENT_IN, BASED_IN) | ⬜ |
| Related-party detection (common ownership within N hops) | ⬜ |
| Fund-flow tracing across the graph | ⬜ |
| Derived `[:HAS_OBLIGATION]` edge (written by engine) | ⬜ |

---

## C. Rule packs

| Capability | Status |
|-----------|--------|
| `RulePack` / `Rule` Pydantic models with required fields (id, jurisdiction, type, parameters, as_of_date, source_citation) | ⬜ |
| `RulePackLoader` protocol + JSON file implementation | ⬜ |
| HK pack (territorial income, profits tax rate, filing deadlines) | ⬜ |
| EU member pack (VAT, CIT, PE rules, treaty pointers) | ⬜ |
| US pack (worldwide income, federal CIT, state nexus triggers, withholding rates) | ⬜ |
| SG / UK pack (scope, rates, deadlines) | ⬜ |

---

## D. Deterministic engine

| Capability | Status |
|-----------|--------|
| Nexus / obligation trigger evaluation | ⬜ |
| Threshold boolean logic (amounts vs. rule thresholds) | ⬜ |
| Transaction aggregation by jurisdiction / period / flow type | ⬜ |
| Rate × base arithmetic (with rule provenance) | ⬜ |
| Deadline calculation (fiscal calendar + company accounting period) | ⬜ |
| Cross-border conflict detection (same flow/base claimed by ≥2 jurisdictions) | ⬜ |
| PE (permanent establishment) trigger detection | ⬜ |
| Withholding tax exposure flag | ⬜ |
| Double-tax candidate flag + treaty pointer lookup | ⬜ |
| All engine output carries rule id, as_of_date, source_citation | ⬜ |

---

## E. AI layer (grounded)

| Capability | Status |
|-----------|--------|
| Flow nature classification (revenue / expense / inter-company / capital / loan) | ⬜ |
| Candidate jurisdiction attribution per flow | ⬜ |
| Grounded rule retrieval from packs (must cite rule id + as_of_date) | ⬜ |
| Confidence level output per recommendation | ⬜ |
| Abstention ("insufficient information, needs legal review") | ⬜ |
| AI emits no figures — all numbers come from engine | ⬜ |
| Mock Claude adapter for tests | ⬜ |

---

## F. Brief assembly

| Capability | Status |
|-----------|--------|
| Per-jurisdiction brief data model (all numeric slots pre-filled by engine) | ⬜ |
| AI narrative prose around engine-filled values | ⬜ |
| Full traceability per brief item (rule + as_of_date + source transactions + confidence) | ⬜ |
| Lawyer open-questions list | ⬜ |
| Cross-border flag report | ⬜ |
| Brief output in `output/` directory | ⬜ |

---

## G. Demo / reliability

| Capability | Status |
|-----------|--------|
| Golden multinational mock dataset (~10–15 flows, 3–4 jurisdictions) | ⬜ |
| Planted cross-border conflict (hand-computed, verified) | ⬜ |
| Hand-computed expected values in `data/golden/EXPECTED.md` | ⬜ |
| Cached AI outputs for golden dataset (offline-safe demo) | ⬜ |
| `make demo` reproducible without live Claude API | ⬜ |
| Brief UI showing as_of_dates, citations, confidence, conflict highlight | ⬜ |
| Neo4j graph view (entity structure + fund flows) | ⬜ |
