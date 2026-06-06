# Tributary — Hackathon Roadmap

**Goal:** End-to-end demo: Meridian Group (HK/DE/FR multinational) → 3 fully cited filing briefs + cross-border conflict report (The PE Triangle).

Each wave = one focused coding session. The system is runnable and testable at the end of every wave. The deterministic engine is fully tested before the AI layer is wired in. See `DECISIONS.md` for the rationale behind every major choice.

---

## Architecture constraints (carried through all waves)

- **Engine is country-agnostic.** No jurisdiction-specific `if` statements in engine code. All country-specific values come from rule packs. New country = new JSON file, zero engine code change. (DEC-006)
- **AI emits no figures.** All amounts, rates, thresholds, deadlines are engine-computed. (DEC-002)
- **`source_flow_ids` on every `ObligationResult`.** Mandatory from Wave 4 onwards — enables conflict detection.
- **Loss carryforward in scope.** Engine handles prior-period loss offset with jurisdiction-specific limitation rules. (DEC-008)
- **PE data model from Wave 1.** `PresenceRecord` and PE fields on `Transaction` authored in golden data and carried through. PE trigger detection fires in Wave 6.
- **Attribution stub = separate JSON file.** `data/golden/attributions_stub.json` maps tx_id → {nature, claims}. Stub implements `AILayerProtocol`. Real AI replaces it in Wave 5. (DEC-010)
- **Graph layer is a separate concern.** Engine depends on `GraphReader` / `GraphWriter` protocols only (see `API_ENGINE_GRAPH.md`). Neo4j implementation is injected.

---

## Carry-forward notes

_Maintained by `/wave-parallel`. State that survives between sessions so a fresh
run needn't rediscover it. Add a line when a task completes and unblocks something
later; delete consumed lines; keep it under ~15 lines._

- **Waves 1, 3, 4a, 4b, 5 COMPLETE**: Engine produces golden figures; all AI layer files wired; 197 tests green.
- **Waves 1, 3, 4a, 4b, 5, 6 COMPLETE**: All engine passes golden; PE Triangle fires + verified; WHT exposure scanner built; 200 tests green. Wave 6b is next.
- **Wave 6b NEW**: Group profit redistribution detection — see Wave 6b section below. DEC-020 records the architectural decision.
- **Models split**: `common/models.py` re-exports from `models_entity.py`, `models_engine.py`, `models_ai.py`. See DEC-012.
- **EXPECTED.md canonical figures**: HK HKD 445,500; DE CIT HKD 47,673; DE Trade Tax HKD 42,175; FR CIT HKD 1,030,938. PE Triangle — exemption method, residual double-tax = 0.
- **Wave 2**: graph colleague primary (W2.1–W2.3, W2.6). Engine owner reviews W2.4 + W2.5 when PRs ready.
- **Next ISSUE id**: ISSUE-009. **Next DEC id**: DEC-021.

---

## Wave 1 — Foundations & golden data

**Owner:** both (graph colleague: schema; engine owner: golden data authoring)
**Deliverable:** repo scaffold, canonical Pydantic data models (including PE fields), Neo4j Docker running, Meridian Group golden scenario with hand-computed expected values and planted conflict authored.

**Entry:** empty repo
**Exit gate:** `make ingest` seeds graph; golden data traversable in Neo4j Browser; `EXPECTED.md` has hand-computed values for all 3 jurisdictions + PE Triangle conflict.

### Tasks
- [x] **W1.1** — scaffold repo, Docker Compose (Neo4j 5), Makefile with `make test`, `make ingest`, `make run-golden`, `make demo`, `make check-layers`, `make test-engine`
- [x] **W1.2** — `common/models.py`: canonical Pydantic v2 data models:
  - `Entity`, `Account`, `Transaction`, `Counterparty`, `Jurisdiction`
  - `FiscalPeriod(jurisdiction, start_date, end_date)`
  - `FiscalCalendar(jurisdiction, period_start_month, period_start_day)`
  - `PresenceRecord(entity_id, jurisdiction, period_start, period_end, total_days_present, activity_type, has_agent_authority, has_fixed_place)` — PE detection from day one
  - `PriorPeriodLoss(loss_id, entity_id, jurisdiction, loss_period_start, loss_period_end, original_loss_hkd, remaining_loss_hkd)`
  - Add to `Transaction`: `is_intercompany`, `counterparty_entity_id`, `activity_type`, `days_present`, `has_agent_authority`
- [x] **W1.3** — document jurisdiction + PE rationale in `DECISIONS.md` _(DEC-006 through DEC-010 already written; update if needed)_
- [x] **W1.4** — author `data/golden/` Meridian Group mock files:
  - `entities.json` — MERID-HK, MERID-DE, MERID-FR
  - `ownership.json` — MERID-HK →100%→ MERID-DE →100%→ MERID-FR
  - `transactions.json` — T001–T009 (see DEC-007 for list; T003 is the 185-day presence record)
  - `presence_records.json` — MERID-DE in France, 185 days, service_delivery
  - `prior_losses.json` — MERID-DE FY2024 loss HKD 1,600,000 in Germany
  - `fx_rates.json` — HKD/EUR and HKD/USD reference rates
- [x] **W1.5** — hand-compute `data/golden/EXPECTED.md`:
  - **MERID-HK:** HK Profits Tax on T001 royalty income (source-rule question); no tax on T005 inbound dividend (territorial)
  - **MERID-DE:** German CIT (post FY2024 loss offset, Mindestbesteuerung check); German Trade Tax; WHT on T005 dividend to HK (5% under DTA); Zinsschranke check on T006 interest; PE-attributed income to France (35% of net income = ~HKD 1,400,000); treaty credit for French tax
  - **MERID-FR:** French CIT on T009 third-party revenue + PE-attributed income from MERID-DE; VAT filing obligation
  - **PE Triangle conflict:** same HKD ~1,400,000 taxed in FR (via PE) and DE (worldwide); treaty pointer DE-FR DTA Art.23; net credit amount
- [x] **W1.6** — seed Neo4j from golden files; verify traversal and presence records in Neo4j Browser

**Handoffs after Wave 1:**
- Share `common/models.py` with graph colleague (schema foundation)
- Share `API_ENGINE_GRAPH.md` with graph colleague (what the engine will call)
- Share `data/golden/EXPECTED.md` with both colleagues (ground truth)

---

## Wave 2 — Ingestion & graph layer

**Owner:** graph colleague (primary); engine owner reviews `GraphReader` / `GraphWriter` implementations
**Deliverable:** ingest pipeline (mock exports → Neo4j); `GraphReader` and `GraphWriter` protocols implemented and unit-tested; engine can call graph reads against real data.

**Entry:** Wave 1 complete; `common/models.py` stable
**Exit gate:** `make ingest` populates graph with correct node/edge counts; `GraphReader` unit tests pass with real Neo4j; presence records and prior losses stored and queryable.

### Tasks
- [ ] **W2.1** — `ingestion/reader.py`: parse CSV/JSON mock exports to raw records
- [ ] **W2.2** — `ingestion/normalizer.py`: map raw → normalized Pydantic models; FX-normalize to HKD with `fx_date`
- [ ] **W2.3** — `graph/writer.py`: idempotent upsert for Entity, Account, Transaction, Counterparty, PresenceRecord, PriorPeriodLoss nodes and all relationship edges
- [ ] **W2.4** — `graph/readers.py`: Neo4j-backed implementation of `GraphReader` protocol (see `API_ENGINE_GRAPH.md` §4)
- [ ] **W2.5** — `graph/writer_engine.py`: Neo4j-backed implementation of `GraphWriter` protocol (see `API_ENGINE_GRAPH.md` §5)
- [ ] **W2.6** — integration test: golden mock files in → correct node counts, edge types, presence records (185 days), prior loss records

---

## Wave 3 — Rule packs

**Owner:** engine owner
**Deliverable:** rule-pack contract and loader; HK, DE, FR JSON packs covering exactly what the golden scenario needs; treaties HK-DE and DE-FR.

**Entry:** Wave 1 complete (rule packs are independent of Wave 2)
**Exit gate:** `get_rules("DE", "cit")` returns rules with as_of_date and source_citation; fiscal calendars correct; treaty packs load and return treaty relief rates.

### Tasks
- [ ] **W3.1** — `rules/models.py`: `Rule`, `RulePack`, `RulePackLoader` protocol, `FiscalCalendarRule`
- [ ] **W3.2** — `rules/loader.py`: JSON file loader implementing `RulePackLoader`
- [ ] **W3.3** — `data/rules/hk.json`:
  - Profits Tax rate 16.5%; territorial scope rule; source rule for royalties
  - No WHT on dividends paid out; no VAT
  - Filing deadline: within 1 month of profits tax return (typically April)
  - Fiscal calendar: April 1 – March 31
  - Loss carryforward: unlimited, no cap
- [ ] **W3.4** — `data/rules/de.json`:
  - CIT 15% + solidarity surcharge 5.5% (effective 15.825%)
  - Trade Tax 14% (average municipality rate) on same base
  - WHT on dividends outbound: 25%, reduced to 5% under HK-DE DTA
  - WHT on royalties outbound: 15%, reduced to 5% under HK-DE DTA
  - Zinsschranke: interest deduction capped at 30% EBITDA
  - Mindestbesteuerung: loss offset unlimited up to €1M equivalent, then 60% of excess
  - Participation exemption (§8b KStG): 95% of received dividends exempt
  - PE definition: service PE triggered at 183 days in 12-month period
  - Fiscal calendar: calendar year; filing deadline: July 31 following year
- [ ] **W3.5** — `data/rules/fr.json`:
  - CIT 25% flat
  - VAT: 20% standard rate; registration threshold; quarterly filing obligation
  - WHT on dividends/royalties to non-EU: 12.8% (management fees: 12.8% unless treaty)
  - EU Interest & Royalties Directive: 0% WHT on intra-EU royalties (conditions: 25%+ holding, 2-year minimum)
  - PE definition: service PE triggered at 183 days
  - Loss carryforward: unlimited, 50% cap beyond €1M equivalent
  - Fiscal calendar: calendar year; filing deadline: May following year
- [ ] **W3.6** — `data/rules/treaties/hk_de.json`:
  - Art.5 PE (no service PE provision — OECD pre-2017; note this in as_of_date)
  - Art.10 Dividends: 5% WHT if ≥10% ownership for ≥12 months; 15% otherwise
  - Art.11 Interest: 0% WHT
  - Art.12 Royalties: 5% WHT
  - Art.23 Elimination: credit method (Germany gives credit for HK tax; HK territorial exclusion)
- [ ] **W3.7** — `data/rules/treaties/de_fr.json`:
  - Art.5 PE: 183-day service PE provision (OECD 2017 update)
  - Art.7 Business profits: PE profits taxed in PE state; residence state gives credit
  - Art.10 Dividends: 5% WHT if ≥10% ownership; 15% otherwise; EU Parent-Sub Directive overrides (0% intra-EU if conditions met)
  - Art.23 Elimination: credit method for both states
- [ ] **W3.8** — unit tests: loader returns correct rules for each jurisdiction/flow type; fiscal calendars correct; treaty packs load; as_of_date and source_citation always present

---

## Wave 4a — Engine infrastructure

**Owner:** engine owner
**Deliverable:** engine protocols, orchestrator skeleton, aggregator with multi-period handling and IC elimination, attribution stub.

**Entry:** Waves 2 + 3 complete
**Exit gate:** `EngineRunner` instantiates with stub attribution; `aggregate_transactions()` returns correct per-jurisdiction per-period buckets for all golden flows including IC elimination; unit tests green.

### Tasks
- [ ] **W4a.1** — `ai/protocol.py`: `AILayerProtocol` ABC + all input/output Pydantic models (see `API_ENGINE_AI.md`). **Publish to AI colleague at this point.**
- [ ] **W4a.2** — `data/golden/attributions_stub.json`: `{tx_id: {nature, confidence, rule_citations, attribution: {primary_jurisdiction, claims[]}}}` for all T001–T009 (T003 is presence record — nature: "service_delivery", jurisdiction: FR, PE flag)
- [ ] **W4a.3** — `engine/attribution_stub.py`: `AttributionStub` implements `AILayerProtocol` by loading `attributions_stub.json`
- [ ] **W4a.4** — `engine/aggregator.py`:
  - Group transactions by attributed jurisdiction + fiscal period (uses `FiscalCalendar` from rule pack)
  - IC elimination step: net out `is_intercompany=True` transactions within the group
  - Multi-jurisdiction split: if a flow has multiple jurisdiction claims, split pro-rata by confidence weight
  - Returns `AggregatedBase` per jurisdiction per period per flow nature
- [ ] **W4a.5** — `engine/runner.py`: `EngineRunner` orchestrator:
  - Injected dependencies: `GraphReader`, `GraphWriter`, `AILayerProtocol`, `RulePackLoader`
  - Pipeline order: classify flows → attribute flows → aggregate → triggers → thresholds → [CIT | WHT | VAT | TradeTax] → deadlines → loss ledger → write results
  - Collects `EngineRunResult` per entity per period
- [ ] **W4a.6** — unit tests: aggregator IC elimination; period bucketing for HK (Apr–Mar) vs DE/FR (Jan–Dec); multi-jurisdiction split

---

## Wave 4b — Engine computation

**Owner:** engine owner
**Deliverable:** all tax-type computation modules; loss carryforward ledger; full integration test against `EXPECTED.md`.

**Entry:** Wave 4a complete
**Exit gate:** `make test-engine` fully green; engine output matches all values in `EXPECTED.md`; every `ObligationResult` carries `source_flow_ids` and `computation_trace`.

### Tasks
- [ ] **W4b.1** — `engine/triggers.py`: nexus/obligation trigger evaluation — reads threshold rules from pack; boolean output; flags PE days_present threshold breach (full PE logic in Wave 6)
- [ ] **W4b.2** — `engine/thresholds.py`: threshold boolean checks — VAT registration threshold; PE day-count threshold; Zinsschranke cap; Mindestbesteuerung limit
- [ ] **W4b.3** — `engine/cit_engine.py`: CIT computation per jurisdiction:
  - Taxable base = aggregated revenue − allowable deductions (IC-eliminated)
  - Loss carryforward offset (calls `loss_ledger.py`)
  - Participation exemption check (reads rule pack for exemption percentage)
  - Rate × base (reads CIT rate from rule pack — country-agnostic)
  - PE attribution deduction (if PE-attributed income moved to other jurisdiction)
  - Emits `ObligationResult(obligation_type=CIT)` with `computation_trace`
- [ ] **W4b.4** — `engine/wht_engine.py`: WHT computation per payment:
  - Gross payment amount × WHT rate (from rule pack)
  - Treaty relief lookup (reads treaty pack for reduced rate)
  - EU Directive exemption check (reads rule pack for I&R Directive conditions)
  - Beneficial ownership condition flag
  - Emits `ObligationResult(obligation_type=WHT)` with treaty_relief_hkd
- [ ] **W4b.5** — `engine/vat_engine.py`: VAT obligation:
  - Registration threshold check (is entity above threshold?)
  - If above: flag filing obligation + deadline
  - V1 does not compute net VAT arithmetic — flags obligation only
  - Emits `ThresholdResult` + `DeadlineResult`
- [ ] **W4b.6** — `engine/trade_tax_engine.py`: Trade Tax computation:
  - Only activated if rule pack contains a `trade_tax` rule type
  - Same taxable base as CIT (German Gewerbesteuer uses same base)
  - Rate × base using trade tax rate from rule pack
  - Emits `ObligationResult(obligation_type=TRADE_TAX)`
- [ ] **W4b.7** — `engine/deadlines.py`: filing + payment deadline calculation using fiscal calendar + rule deadlines
- [ ] **W4b.8** — `engine/loss_ledger.py`:
  - Reads `PriorPeriodLoss` records from graph via `GraphReader`
  - Computes allowable offset per jurisdiction limitation rules (from rule pack)
  - Returns `LossCarryforwardRecord`; runner calls `GraphWriter.update_loss_carryforward()` after
- [ ] **W4b.9** — unit tests for every engine module against hand-computed golden values
- [ ] **W4b.10** — integration test: full engine run on golden → all values match `EXPECTED.md`

---

## Wave 5 — AI layer

**Owner:** AI colleague
**Entry contract:** `ai/protocol.py` (published at W4a.1); `API_ENGINE_AI.md`
**Deliverable:** real Claude-backed `AILayerProtocol` implementation; replaces stub; full AI + engine pipeline integration test passes.

**Entry:** `ai/protocol.py` stable; Wave 4b complete
**Exit gate:** `make run-golden` produces correct engine-computed obligations driven by real AI attributions; AI attributions for golden scenario match `attributions_stub.json` (used as ground truth).

### Tasks
- [x] **W5.1** — `ai/classifier.py`: classify flow nature via Claude structured output
- [x] **W5.2** — `ai/attributor.py`: attribute candidate jurisdictions per flow; grounded to graph context + rule packs
- [x] **W5.3** — `ai/retriever.py`: retrieve applicable rules from packs; cite rule_id + as_of_date; abstain if insufficient
- [x] **W5.4** — `prompts/classify_flow.yaml`, `prompts/attribute_jurisdiction.yaml`, `prompts/retrieve_rules.yaml`
- [x] **W5.5** — `ai/mock_adapter.py`: mock Claude adapter returning `attributions_stub.json` values for unit tests
- [x] **W5.6** — swap: `EngineRunner` receives real `AILayer` implementation; attribution stub retired to test-only
- [x] **W5.7** — integration test: AI + engine pipeline on golden scenario matches `EXPECTED.md`

---

## Wave 6 — Conflict detection

**Owner:** engine owner
**Deliverable:** cross-border conflict detection on top of engine output; PE attribution full computation; planted PE Triangle conflict fires correctly.

**Entry:** Wave 5 complete (or Wave 4b with stub for engine testing)
**Exit gate:** PE Triangle conflict detected, explained, treaty pointer correct, credit amount matches `EXPECTED.md`.

### Tasks
- [x] **W6.1** — `engine/conflict.py`: scan `EngineRunResult.obligations` for flows where `source_flow_ids` overlap across jurisdictions → double-tax candidate
- [x] **W6.2** — full PE attribution computation: aggregate presence_days from graph; if above PE threshold: compute attribution percentage; split attributed income from parent jurisdiction's CIT base (`engine/pe.py`)
- [x] **W6.3** — double-tax flag: same attributed income appearing in two `ObligationResult` records → `ConflictFlag`
- [x] **W6.4** — WHT exposure flag: check WHT obligations against treaty entitlement; flag over-withheld cases (`engine/wht_exposure.py` — new module)
- [x] **W6.5** — `ConflictFlag` model in `common/models.py`; `EngineRunResult.conflicts` field populated
- [x] **W6.6** — treaty pointer lookup: conflict detector reads treaty pack for relevant DTA article + elimination method
- [x] **W6.7** — integration test: PE Triangle fires; exemption method applied; residual double-tax = 0; conflict report matches `EXPECTED.md`

---

## Wave 6b — Group profit redistribution detection

**Owner:** engine owner
**Deliverable:** Engine detects opportunities to redistribute pre-tax profit within the group to offset losses in another member entity, where a jurisdiction-level group-relief rule exists. Emits `GroupReliefOpportunity` flags citing the applicable statute. The AI uses these in the brief narrative (Wave 7). The engine never recommends an amount — it flags the opportunity and leaves quantification to the professional (DEC-002, DEC-020).

**Entry:** Wave 4b complete; rule packs in place
**Exit gate:** For each entity pair (A has income, B has unused losses) in a jurisdiction with a `GROUP_RELIEF` rule, one `GroupReliefOpportunity` is emitted per eligible pair. For the golden scenario (HK/DE/FR — no bilateral group relief available), no opportunities are emitted; this is itself a verifiable test result.

### Tasks
- [ ] **W6b.1** — `common/models_engine.py`: add `GroupReliefOpportunity` model:
  - `opportunity_id`, `income_entity_id`, `loss_entity_id`
  - `income_jurisdiction`, `loss_jurisdiction`
  - `available_income_hkd`, `unused_loss_hkd` (engine-computed amounts, not AI estimates)
  - `relief_mechanism` (Literal: `"group_relief"` | `"organschaft"` | `"integration_fiscale"` | `"transfer_pricing_note"`)
  - `applicable_rule_id`, `as_of_date`, `source_citation`, `conditions_summary`
  - `needs_review: bool = True` (always — professional sign-off required)
- [ ] **W6b.2** — extend `EngineRunResult` with `group_relief_opportunities: list[GroupReliefOpportunity] = []`
- [ ] **W6b.3** — `rules/models.py`: add `GROUP_RELIEF` to `RuleCategory` enum
- [ ] **W6b.4** — `engine/group_relief.py`: cross-entity scanner
  - Accepts all `EntityBase` objects from the runner's aggregation phase
  - For each ordered pair (A, B) where A has `net_income_hkd > 0` and B has unused losses in a related jurisdiction: check if `GROUP_RELIEF` rule exists for the pair's jurisdictions
  - If rule found: emit `GroupReliefOpportunity` citing the rule; set `available_income_hkd = A.net_income_hkd`, `unused_loss_hkd = B.total_unused_losses_hkd`
  - If no rule: no flag (correct — group relief is not universally available)
- [ ] **W6b.5** — wire into `engine/runner.py` after `_assemble_results`: call `scan_group_relief(bases, entities, loader)` and attach results to each affected `EngineRunResult`
- [ ] **W6b.6** — rule pack updates: add `GROUP_RELIEF` rules to any applicable jurisdiction packs. For golden scenario (HK, DE, FR): correctly have no bilateral group relief rule between these three — zero opportunities emitted for MERID group is the expected result
- [ ] **W6b.7** — unit tests:
  - Two entities (income + loss) in a jurisdiction pair with a `GROUP_RELIEF` rule → `GroupReliefOpportunity` emitted with correct fields
  - Same pair in jurisdictions without the rule → no opportunity (correct negative case)
  - Golden scenario produces zero opportunities (regression guard)

---

## Wave 7 — Brief assembly

**Owner:** engine owner + AI colleague
**Deliverable:** 3 per-jurisdiction briefs (HK, DE, FR) with engine-filled values and AI narrative; cross-border conflict report.

**Entry:** Wave 6 complete
**Exit gate:** `make run-golden` → 3 cited briefs + conflict report in `output/`; all numeric fields traced to engine; all recommendations cite a rule.

### Tasks
- [ ] **W7.1** — `brief/template.py`: per-jurisdiction brief data model (all numeric slots engine-filled)
- [ ] **W7.2** — `brief/narrator.py`: Claude generates prose around engine-filled values (never restates figures)
- [ ] **W7.3** — `brief/assembler.py`: compose full brief — template + narrative + traceability + open questions
- [ ] **W7.4** — `brief/report.py`: cross-border conflict report assembly (PE Triangle highlight)
- [ ] **W7.5** — `prompts/brief_narrative.yaml`
- [ ] **W7.6** — `make run-golden` produces brief files in `output/`
- [ ] **W7.7** — integration test: briefs contain all required sections; all numeric fields sourced from engine; all recommendations cite a rule; PE Triangle appears in conflict report

---

## Wave 8 — Demo hardening

**Owner:** both
**Deliverable:** cached AI outputs for golden dataset; `make demo` runs offline-safe; UI; rehearsed demo.

**Entry:** Wave 7 complete
**Exit gate:** `make demo` runs without live Claude API; rehearsed answers to "who pays", "what breaks at scale", "why trust the numbers".

### Tasks
- [ ] **W8.1** — snapshot AI outputs for golden dataset to `data/golden/ai_cache/`
- [ ] **W8.2** — `make demo` runs entirely on cached AI (never hits Claude live)
- [ ] **W8.3** — brief output UI (terminal or minimal web): as_of_dates, citations, confidence, PE Triangle conflict highlight
- [ ] **W8.4** — Neo4j graph view in browser: entity ownership + fund flows (T001–T009 visible)
- [ ] **W8.5** — rehearse demo; document Q&A in `project-harness/DEMO_SCRIPT.md`

---

## Expansion roadmap (post-hackathon, reference only)

| Code | Expansion | Notes |
|------|-----------|-------|
| E1 | Statutory form filling | Brief fields → country statutory forms (HK BIR51 first). Scope-explosion zone. |
| E2 | Real licensed rule data | IBFD / Bloomberg Tax behind existing pack interface |
| E3 | Real ingestion connectors | Xero / QuickBooks / ERP; Open APIs |
| E4 | New jurisdictions | US, Singapore, UK — new JSON packs only, zero engine code change (DEC-006) |
| E5 | Tax-saving / planning | Advice-heavy, regulated — design only with professional sign-off |

---

## Session Log

| # | Date | Wave | What was done | Exit state |
|---|------|------|---------------|------------|
| 1 | 2026-06-06 | setup | Copied + updated harness from NPCSystem | Harness ready, no code yet |
| 2 | 2026-06-06 | planning | Engine plan refined; API contracts written; planted conflict designed; wave roadmap authored | API_ENGINE_AI.md, API_ENGINE_GRAPH.md, DECISIONS.md updated, ROADMAP.md rewritten; ready for Wave 1 |
| 3 | 2026-06-06 | 0–1 | Technical audit, architecture fixes, full engine implementation | 137 tests green, layer check clean, engine produces golden figures |
| 4 | 2026-06-06 | 5 | AI layer v1 merge integration — AILayerAdapter, adapter tests, engine hardening | 179 tests green; Wave 5 ~80%; Wave 6 engine-side built; Wave 6b scoped |
| 5 | 2026-06-06 | 5+6 | Ticked Wave 5 complete; W6.4 WHT exposure scanner — wht_exposure.py + 14 tests | 197 tests green; Wave 5 done; Wave 6 open: W6.7 only |
