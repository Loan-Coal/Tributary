# Tributary — Feature Compilation

**As of:** 2026-06-06 (session 3 — engine + AI layer complete).

Legend: ✅ implemented + tested · 🟡 implemented, no dedicated test · ⬜ not started · ⚠️ known issue (see ISSUES.md)

---

## A. Ingestion & normalization

| Capability | Status |
|-----------|--------|
| Parse CSV/JSON mock GL/bank exports | 🟡 dev seed only (`ingestion/seed.py`) |
| Normalize to canonical `Transaction` / `Entity` / `Account` / `Counterparty` / `Jurisdiction` models | ✅ Pydantic models in `common/` |
| Currency normalization to base reporting currency with `fx_rate` + `fx_date` | 🟡 modeled in `Transaction`; seed loads from `fx_rates.json` |
| Idempotent Neo4j upsert (entities, accounts, transactions, counterparties, jurisdictions) | ⬜ Wave 2 (graph colleague) |

---

## B. Graph store (Neo4j)

| Capability | Status |
|-----------|--------|
| Entity nodes (holdco / subsidiary / branch) | 🟡 seed writes; production writer (Wave 2) pending |
| Ownership edges `[:OWNS {pct}]` | 🟡 seed writes |
| Account, Transaction, Counterparty, Jurisdiction nodes | 🟡 seed writes |
| Relationship edges (HOLDS, RECORDS, WITH, RESIDENT_IN, BASED_IN) | 🟡 seed writes |
| Related-party detection (common ownership within N hops) | ⬜ Wave 2 |
| Fund-flow tracing across the graph | ⬜ Wave 2 |
| Derived `[:HAS_OBLIGATION]` edge (written by engine) | 🟡 `GraphWriter` protocol defined; Neo4j implementation is Wave 2 |

---

## C. Rule packs

| Capability | Status |
|-----------|--------|
| `RulePack` / `Rule` Pydantic models with required fields (id, jurisdiction, type, parameters, as_of_date, source_citation) | ✅ `rules/models.py` |
| `RulePackLoader` protocol + JSON file implementation | ✅ `rules/loader.py` |
| HK pack (territorial income, profits tax rate, WHT, filing deadlines) | ✅ `data/rules/hk.json` |
| DE pack (CIT, trade tax, WHT, Mindestbesteuerung, Zinsschranke, PE) | ✅ `data/rules/de.json` |
| FR pack (CIT 25%, VAT, WHT, PE definition, loss cap) | ✅ `data/rules/fr.json` |
| Treaty packs HK-DE and DE-FR (WHT rates, PE, elimination method) | ✅ `data/rules/treaties/` |
| US pack (worldwide income, federal CIT, state nexus) | ⬜ post-hackathon |
| SG / UK pack | ⬜ post-hackathon |

---

## D. Deterministic engine

| Capability | Status |
|-----------|--------|
| Nexus / obligation trigger evaluation | ✅ `engine/triggers.py` |
| Threshold boolean logic (amounts vs. rule thresholds) | ✅ `engine/thresholds.py` |
| Transaction aggregation by jurisdiction / period / flow type with IC elimination | ✅ `engine/aggregator.py` |
| CIT computation (rate × base, loss offset, PE adjustment, participation exemption) | ✅ `engine/cit_engine.py` |
| WHT computation (gross × rate, treaty relief, EU Directive exemption) | ✅ `engine/wht_engine.py` |
| VAT threshold check + filing obligation flag | ✅ `engine/vat_engine.py` |
| German Trade Tax (Gewerbesteuer) — rule-pack-activated | ✅ `engine/trade_tax_engine.py` |
| Deadline calculation (fiscal calendar + rule deadlines) | ✅ `engine/deadlines.py` |
| Loss carryforward ledger (FIFO, Mindestbesteuerung cap) | ✅ `engine/loss_ledger.py` |
| PE trigger detection + profit attribution | ✅ `engine/pe.py` |
| PE double-tax conflict flag + treaty pointer lookup | ✅ `engine/conflict.py` |
| WHT exposure flag (over-withholding vs treaty entitlement) | ⬜ W6.4 |
| Group profit redistribution opportunity detection | ⬜ Wave 6b |
| All engine output carries rule id, as_of_date, source_citation | ✅ enforced on all `ObligationResult` |
| Full `EngineRunner` orchestrator (6-phase pipeline) | ✅ `engine/runner.py` |

---

## E. AI layer (grounded)

| Capability | Status |
|-----------|--------|
| Flow nature classification (revenue / expense / inter-company / capital / loan) | ✅ `ai/service.py` |
| Candidate jurisdiction attribution per flow | ✅ `ai/adapter.py` |
| Grounded rule retrieval from packs (must cite rule id + as_of_date) | ✅ `ai/rag_retriever.py` |
| Confidence level output per recommendation | ✅ `ai/models.py` |
| Abstention ("insufficient information, needs legal review") | ✅ `ai/service.py` |
| AI emits no figures — all numbers come from engine | ✅ enforced by prompt + adapter |
| Mock (fake) Claude adapter for tests | ✅ `ai/fake_client.py` |
| Local Qwen model adapter (offline demo) | ✅ `ai/qwen_client.py` |
| Anthropic Claude API adapter | 🟡 `ai/client.py` — uses legacy completions API; needs migration to `messages` API |
| AILayerAdapter bridging service ↔ engine protocol | ✅ `ai/adapter.py` |
| Per-flow LLM call cache (one call per flow_id) | ✅ `ai/adapter.py` |

---

## F. Brief assembly

| Capability | Status |
|-----------|--------|
| Per-jurisdiction brief data model (all numeric slots pre-filled by engine) | ⬜ Wave 7 |
| AI narrative prose around engine-filled values | ⬜ Wave 7 |
| Full traceability per brief item (rule + as_of_date + source transactions + confidence) | ⬜ Wave 7 |
| Lawyer open-questions list | ⬜ Wave 7 |
| Cross-border flag report | ⬜ Wave 7 |
| Group relief opportunity section in brief | ⬜ Wave 7 (depends on Wave 6b) |
| Brief output in `output/` directory | ⬜ Wave 7 |

---

## G. Demo / reliability

| Capability | Status |
|-----------|--------|
| Golden multinational mock dataset (Meridian Group, 3 jurisdictions, T001–T009) | ✅ `data/golden/` |
| Planted cross-border conflict — PE Triangle (MERID-DE in France 185 days) | ✅ modeled + engine fires |
| Hand-computed expected values in `data/golden/EXPECTED.md` | ✅ HK + DE + FR + PE Triangle |
| 179 passing unit tests (6 skipped — Neo4j integration) | ✅ `make test` green |
| Cached AI outputs for golden dataset (offline-safe demo) | ⬜ Wave 8 |
| `make demo` reproducible without live Claude API | ⬜ Wave 8 |
| Brief UI showing as_of_dates, citations, confidence, conflict highlight | ⬜ Wave 8 |
| Neo4j graph view (entity structure + fund flows) | ⬜ Wave 8 |
