# Decisions Log

Non-obvious architectural choices. Each entry explains what was decided and why,
so future maintainers can judge edge cases without re-deriving the rationale.

Rules:
- Append-only. Never delete entries.
- Monotonic DEC-NNN IDs. Never reuse.
- Context, options considered, decision, why. No essays.

**Canonical location:** This file lives at `project-harness/DECISIONS.md`. Never create or edit a root-level copy.

---

## DEC-001: Rule packs stored as structured JSON, not in Neo4j

**Date:** 2026-06-06
**Context:** The graph stores operational data (entities, transactions, counterparties). Rule packs
are versioned, static reference data with a stable contract.
**Options considered:**
  1. Store rules as Neo4j nodes — enables graph traversal across rules + transactions but couples
     rule versioning to the graph lifecycle and makes rule updates a schema migration.
  2. Store rules as versioned JSON files behind a loader interface — decoupled, independently
     deployable, easy to swap for a licensed data feed later.
**Decision:** Option 2. Rule packs are versioned JSON behind `RulePackLoader` protocol.
**Why:** The loader interface is the integration point — swapping demo packs for licensed data
(IBFD, Bloomberg Tax) means implementing the same interface against a new source, not migrating
graph schema. Heavy aggregation also belongs in the engine's relational/columnar step, not the graph.

## DEC-002: AI emits no figures — engine owns all numbers

**Date:** 2026-06-06
**Context:** Fundamental design constraint from the architecture plan.
**Decision:** The AI layer produces only: flow classification, jurisdiction attribution, rule
citations (by id), confidence levels, abstention flags, and brief narrative prose. All amounts,
rates, thresholds, deadlines, and boolean outcomes are computed by the deterministic engine and
passed to the brief template as pre-filled values. The AI narrative wraps these values but never
restates or re-derives them.
**Why:** Tax figures carry legal liability. An AI-generated number that turns out wrong (due to
hallucination, outdated context, or arithmetic error) is a professional liability issue.
Deterministic computation is auditable; AI arithmetic is not.

## DEC-003: Build deterministic engine before AI layer

**Date:** 2026-06-06
**Context:** Phase ordering in the hackathon build plan.
**Decision:** Phases 0–3 establish the graph, ingestion, rule packs, and deterministic engine —
fully tested against hand-computed golden values — before the AI layer is introduced in Phase 4.
**Why:** If the engine and AI are wired together from the start, a wrong answer cannot be
localized. Building the engine first with a stub attribution layer means any engine failure is
isolated. The AI stub (P3.6) is a thin shim that can be swapped out in P4 without touching engine logic.

## DEC-004: as_of_date always surfaced in output

**Date:** 2026-06-06
**Context:** Demo rule packs use handwritten / outdated rules. This could be a hidden liability.
**Decision:** Every rule application in briefs, reports, and conflict flags must display the
rule's `as_of_date` and `source_citation`. This is non-optional and enforced in the brief template model.
**Why:** Surfacing "this rule is from 2023" turns outdated demo data from a hidden bug into an
honest, defensible design choice. Tax professionals reviewing the brief can judge currency.

## DEC-005: One Neo4j instance per deployment; no multi-tenancy

**Date:** 2026-06-06
**Context:** Hackathon scope — single golden company demo.
**Decision:** Single Docker Neo4j instance, single graph, no `world_id` or tenant isolation needed.
**Why:** Multi-tenancy adds complexity with no hackathon benefit. The company is a distinct unit;
post-hackathon this can be revisited if the product goes multi-tenant.

## DEC-006: Per-country balance sheets sourced from one company's multi-exchange listings

**Date:** 2026-06-06
**Context:** `data/raw/get_data.py` needed real, per-country balance sheets for the same
multinational (Lenovo Group). Initial attempts used per-country *stand-in* tickers (Medion/Infineon
for Germany, Luxshare for a CNY "Beijing" entity), which is fabrication-by-proxy. The original
German ticker `MDN.DE` (Medion) returns empty from Yahoo Finance (delisted after Lenovo's squeeze-out).
**Options considered:**
- (a) Per-country stand-in companies in local currency — rejected: not the same company; misleading.
- (b) FX-convert the one USD statement into HKD/EUR/CNY at rate-dated FX — viable but introduces
  derived (non-source) numbers.
- (c) Pull the same Lenovo statement from each country's exchange listing, as reported (USD).
**Decision:** Option (c). Pull Lenovo Group's consolidated balance sheet from its Hong Kong primary
listing (`0992.HK`), US ADR (`LNVGY`), and Frankfurt listing (`LHL.F`). All return the identical
real statement in USD (verified byte-identical). Files: `lenovo_consolidated_<country>_<ticker>.csv`.
**Why:** A multinational files ONE consolidated balance sheet; a stock-exchange listing changes where
shares trade, not the underlying statement. Pulling per listing keeps every figure real and traceable
to the issuer's filing, with no fabricated entities and no derived FX numbers. **China is omitted**:
Lenovo has no mainland listing (its Shanghai STAR Market CDR was withdrawn in 2021), so no real
Chinese-filed statement exists. The available fiscal years are FY2022–FY2025 (ending March 31), not
2020 — filenames reflect this rather than the earlier misleading `_2020` suffix.

## DEC-007: Balance sheets modelled as FinancialLineItem nodes; package dirs lowercased

**Date:** 2026-06-06
**Context:** Wiring the Lenovo balance-sheet CSVs into the Neo4j graph. A balance sheet does not fit
the existing `Entity → Account → Transaction → Counterparty` model (line items have no account or
counterparty). The `seed` orchestrator also could not be imported.
**Decision:**
1. **New graph node type `FinancialLineItem`** `{id, entity_id, period, line_item, amount, currency,
   statement_type, source}`, linked `Entity-[:REPORTS]->FinancialLineItem`. One Entity (type `holdco`)
   per country listing (HK/US/DE), each `RESIDENT_IN` its Jurisdiction. (User-approved schema addition.)
2. **New balance-sheet normalizer** `pipeline/normalize_balance_sheet.py` (separate file per OCP; the
   OECD normalizer is untouched). `seed/seed.py` now seeds only the balance-sheet graph and exports a
   JSON snapshot via `graph/snapshot.py` into the `graph/` folder.
3. **Renamed `Graph/`→`graph/` and `Seed/`→`seed/`.** Python's import finder is case-sensitive even on
   case-insensitive macOS, so the lowercase imports (`from graph.writer …`) and the makefile target
   (`python -m seed.seed`) never resolved against the capitalised dirs. Lowercase matches the makefile,
   the import statements, and the snake_case naming rule.
4. **`seed()` now wipes the graph (`DETACH DELETE`) before rebuilding**, so the graph reflects exactly
   the source data (the scratch DB held unrelated `LegalEntity`/`Transaction` nodes from prior tests).
5. **Neo4j default password corrected** to match the running container (`NEO4J_AUTH`); credentials are
   now read from `NEO4J_URI`/`NEO4J_USER`/`NEO4J_PASSWORD` env vars with local-dev fallbacks.
**Why:** Faithful representation of balance-sheet data without distorting the transaction model; a
runnable, reproducible seed that matches the project's intended invocation and naming conventions.
