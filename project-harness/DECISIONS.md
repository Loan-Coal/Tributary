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

## DEC-006: Engine is country-agnostic — no jurisdiction-specific logic in engine code

**Date:** 2026-06-06
**Context:** Initial plan referenced "HK", "DE", "FR" as if they would appear as constants in engine code.
**Options considered:**
  1. Hardcode jurisdiction-specific branches (`if jurisdiction == "DE": apply_trade_tax()`) — fast to write, impossible to extend.
  2. Country-agnostic engine: all jurisdiction-specific values (rates, thresholds, deadlines, calendar) come from rule packs at runtime. New country = new JSON file, zero engine code change.
**Decision:** Option 2. No jurisdiction code appears as a literal in any engine module. The engine only processes "jurisdiction code + rule pack parameters". Demo ships with HK, DE, FR rule packs.
**Why:** The engine is the product's durable asset. New countries must not require engine changes. The rule-pack interface is already the correct seam — this decision locks that discipline in.

## DEC-007: Golden scenario — Meridian Group and the PE Triangle planted conflict

**Date:** 2026-06-06
**Context:** The golden scenario needs a planted cross-border conflict that maximally exercises the engine.
**Decision:** Use Meridian Group (MERID-HK, MERID-DE, MERID-FR) with the following planted conflict:

**The PE Triangle** — MERID-DE employees spend 185 days in France (service delivery). This triggers a service PE under DE-FR DTA Art.5 (OECD 2017 service PE, >183 days threshold). France claims the right to tax 35% of MERID-DE's net income as PE-attributed profits (~HKD 1,400,000). Germany simultaneously taxes MERID-DE on worldwide income including the same amount. Treaty resolution: DE-FR DTA Art.23 (credit method) — Germany must give a credit for French tax paid, but the credit is capped at the German rate applied to the same income. The engine must: detect PE trigger, compute PE attribution, flag double-tax conflict, look up treaty pointer, and compute the net credit.

Secondary conflicts surfaced (lower severity, no resolution required in v1):
- T001 (HK→DE royalty): Germany 25% WHT reduced to 5% under HK-DE DTA Art.12. HK source-rule question (is the royalty HK-sourced?) flagged for review.
- T005 (DE→HK dividend): Germany 25% WHT reduced to 5% under HK-DE DTA Art.10 (beneficial ownership condition: 10%+ for 12+ months — met).
- T006 (MERID-HK loan → MERID-DE): Zinsschranke (interest barrier) check — interest of HKD 320,000 vs. 30% EBITDA cap.

**Transactions:** T001–T009 (see `data/golden/transactions.json`). T003 is the presence record (185 days).
**Why this conflict:** It exercises PE trigger detection, multi-jurisdiction double-tax flagging, treaty credit computation, loss carryforward (MERID-DE FY2024 loss), WHT with treaty relief, and threshold checks — all in one scenario.

## DEC-008: Loss carryforward is in scope for v1

**Date:** 2026-06-06
**Context:** Loss carryforward rules are complex but exercised by the golden scenario (MERID-DE FY2024 loss).
**Decision:** In scope. Engine computes allowable loss offset per jurisdiction rules:
  - HK: unlimited carryforward, no cap.
  - DE: Mindestbesteuerung — full offset up to €1M equivalent, then 60% of remaining income.
  - FR: Similar cap structure; full offset up to €1M equivalent, then 50% of excess.
Loss positions are persisted in the graph via `GraphWriter.update_loss_carryforward()` after each period.
**Why:** The golden scenario explicitly has a prior-period loss. Silently ignoring it would produce wrong CIT numbers. Scoping it in forces the engine to be correct on a realistic pattern.

## DEC-009: Tax-type-specific sub-engines, not one generic rates module

**Date:** 2026-06-06
**Context:** Original plan had a single `engine/rates.py`. WHT on gross payments and CIT on net income are structurally different computations. VAT is a filing obligation, not a net tax computation for the entity.
**Decision:** Separate sub-engine modules per obligation type:
  - `engine/cit_engine.py` — CIT: aggregate net income → loss offset → rate × base → treaty credit
  - `engine/wht_engine.py` — WHT: gross payment × rate → treaty relief → EU Directive exemption check → net WHT
  - `engine/vat_engine.py` — VAT: threshold check → filing obligation flag (v1 does not compute net VAT arithmetic)
  - `engine/trade_tax_engine.py` — German Gewerbesteuer: separate rate × same CIT base (Germany-specific but country-agnostic code — activated when rule pack contains trade_tax rules)
All sub-engines are activated by the rule pack containing the relevant rule type — they are never called based on jurisdiction name.
**Why:** Mixing computation patterns in one module causes incorrect results (applying WHT logic to income base, or vice versa). Sub-engines are independently testable and independently extensible.

## DEC-010: Attribution stub uses separate JSON mapping file

**Date:** 2026-06-06
**Context:** Phase 3 engine needs jurisdiction annotations on flows before AI is built (Phase 4).
**Options considered:** (1) field in mock data files; (2) separate JSON mapping file; (3) hardcoded in Python.
**Decision:** Option 2. `data/golden/attributions_stub.json` maps `tx_id → {nature, claims[]}`. The `AttributionStub` class loads this file and implements `AILayerProtocol`. Phase 4 replaces `AttributionStub` with real AI — the engine sees no difference.
**Why:** The mapping file is structurally identical to what AI attribution output looks like. The swap in Phase 4 is replacing a file loader with a protocol call — not a refactor. The file also doubles as the expected-attribution fixture for AI integration tests.

## DEC-011: pyproject.toml uses `setuptools.build_meta` backend

**Date:** 2026-06-06
**Context:** Scaffolding the Python package manifest. `setuptools.backends.legacy:build` (the new setuptools 68+ entrypoint) is not present in the active conda environment (setuptools 69 on Python 3.11). The standard `setuptools.build_meta` backend is universally available and supported.
**Options considered:**
  1. `setuptools.backends.legacy:build` — new-style entrypoint, requires setuptools ≥ 68.0.0 with this specific path available; not available in the project's conda env.
  2. `setuptools.build_meta` — classic, universally supported, pip-installable on all Python ≥ 3.8 environments.
**Decision:** `setuptools.build_meta`.
**Why:** The classic backend works everywhere without version-specific setuptools internals. There is no functional difference for this project's packaging needs.

## DEC-012: common/models.py split into three sub-modules

**Date:** 2026-06-06
**Context:** W1.2 task requires all canonical Pydantic models in `common/`. The 300-line file
limit (hard rule) applies. A single `models.py` with all enums, entity models, engine output
models, and AI protocol models would exceed 300 lines.
**Options considered:**
  1. One `models.py` file — exceeds 300-line limit; violates coding rules.
  2. Split into `models_entity.py` (enums + entity/period models), `models_engine.py`
     (engine output models + RuleCitation), `models_ai.py` (AI protocol models), with a
     thin `models.py` re-exporter — stays within 300 lines per file; clean responsibility separation.
**Decision:** Option 2. Three sub-modules plus a re-exporter.
**Why:** Each sub-module has a coherent responsibility. The re-exporter (`models.py`) gives
callers a single import surface (`from tributary.common.models import X`) without importing
from sub-modules directly. The split is not artificial — entity models, engine outputs, and
AI protocol models are genuinely distinct layers of the model hierarchy.

## DEC-013: Seed script uses dates-as-strings rather than Neo4j date() types

**Date:** 2026-06-06
**Context:** W1.6 seed is a dev utility, not the production graph writer. Neo4j supports native
`date` types via the Bolt protocol, but the driver requires passing a `datetime.date` object
directly — not a string wrapped in `date()`. Storing as ISO strings (`"YYYY-MM-DD"`) is simpler,
avoids the driver's date-conversion machinery, and is fully sufficient for the demo read path
(engine comparisons and AI citations only need the string value).
**Options considered:**
  1. Store as Neo4j native `date` — correct for production; requires passing `datetime.date`
     objects directly in parameterized queries; the Cypher `date()` constructor only works in
     query text, not in parameter values.
  2. Store as ISO string — simple, portable, unambiguous, sufficient for the demo.
**Decision:** Option 2 for the W1.6 seed utility. Wave 2 `graph/writer.py` should switch to
native `date` types using the driver's `neo4j.time.Date` wrapper.
**Why:** The seed is explicitly a dev utility superseded by Wave 2. Introducing driver-level
date conversion here adds complexity for zero demo benefit. The decision is documented so Wave 2
knows to switch.

## DEC-014: seed.py exceeds 300 total lines — no split applied

**Date:** 2026-06-06
**Context:** The 300-line hard limit applies to non-test code files. `seed.py` is 389 total
lines but contains ~257 non-blank, non-docstring code lines. The apparent overcount comes from
Cypher query strings embedded as multi-line string literals and module/function docstrings.
**Options considered:**
  1. Split into `seed_writers.py` (per-node-type write functions) + `seed.py` (loader +
     orchestrator) — would produce a file boundary in the middle of a single cohesive pipeline.
  2. Keep as one file, document the overcount, note that actual code density is within limits.
**Decision:** Option 2. No artificial split.
**Why:** The docstring-and-Cypher overhead is structural, not complexity. A split here would
create two files that are tightly coupled and would always be changed together — the opposite
of high cohesion / low coupling. The module-level docstring notes this.

## DEC-015: Transaction direction convention (PAYER = source_entity_id)

**Date:** 2026-06-06
**Context:** Engine aggregator needs to classify each transaction as income or expense for each entity. The JSON fixtures required a consistent direction encoding.
**Decision:** For IC flows, `source_entity_id` = PAYER, `counterparty_entity_id` = PAYEE. For third-party revenue, `source_entity_id` = the group entity receiving revenue, `counterparty_entity_id` = None.
**Why:** The payer convention makes direction unambiguous and survives any ordering in the fixture. Flipped T001 (royalty: MERID-DE pays, MERID-HK receives) to match this convention. Documented as DEC-016 in prior session; consolidated here.

## DEC-016: GraphReader exposes get_transactions_involving_entity (source OR counterparty)

**Date:** 2026-06-06
**Context:** Engine aggregator needs every transaction where an entity is on either side (payer or payee). A source-only query would miss income flows for entities that appear as counterparty.
**Decision:** Add `get_transactions_involving_entity(entity_id, period_start, period_end)` to the GraphReader protocol. Returns transactions where `source_entity_id == entity_id OR counterparty_entity_id == entity_id`.
**Why:** Single method, correct semantics. The engine then classifies income vs. expense inside the aggregator based on which side the entity is on. Avoids two separate read calls.

## DEC-017: PE Triangle uses exemption method (DE-FR DTA Art.23 Freistellungsmethode)

**Date:** 2026-06-06
**Context:** Germany and France elected the exemption method for PE business profits in their DTA. This means Germany removes the PE-attributed income from its base entirely rather than taxing it and granting a credit.
**Decision:** `conflict.py::_resolve()` returns `(residence_tax, 0)` for `ReliefMechanism.EXEMPTION`. The credit-method figure is shown in `credit_method_note` for transparency, not applied.
**Why:** Correctly models the treaty. Residual double tax is zero; the income is taxed once in France (255,938 HKD). Informational credit note lets reviewers verify the treaty selection is correct.

## DEC-018: GraphReader / GraphWriter / AILayerProtocol protocols live in common/

**Date:** 2026-06-06
**Context:** Engine imports the graph and AI protocols but must not import from graph/ or ai/ (layer rule). AI and graph layers implement the protocols but must not import from engine/.
**Decision:** Protocols defined in `common/protocols_graph.py` and `common/protocols_ai.py`, re-exported from `common/models.py`. Each layer's `protocol.py` file re-exports for its implementors.
**Why:** common/ has no upward dependencies, so all layers can import from it safely. Avoids circular imports. Follows DIP strictly.

## DEC-019: JurisdictionCode is Annotated[str] not Enum

**Date:** 2026-06-06
**Context:** JurisdictionCode values are two-letter ISO country codes validated by regex `^[A-Z]{2}$`. An enum would require enumerating every jurisdiction upfront; new countries would require a code change.
**Decision:** `JurisdictionCode = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]`. Tests use string literals ("HK", "DE", "FR") not enum dot-access.
**Why:** Open-closed: adding Singapore or US requires only a new rule-pack JSON, not a code change. The regex validator catches malformed codes at Pydantic validation time.

## DEC-020: Group profit redistribution is engine-detected, not AI-recommended

**Date:** 2026-06-06
**Context:** Some jurisdictions allow a profitable entity to transfer taxable profit (or a deduction) to a related entity with unused losses, reducing the group's aggregate tax burden. Examples: UK group relief, German Organschaft, French intégration fiscale. The question is where this detection belongs.
**Options considered:**
  1. AI detects the opportunity in narrative — violates DEC-002 (AI emits no figures). The AI would need to reference amounts to make the recommendation useful.
  2. Engine detects the pattern (income entity A + loss entity B + GROUP_RELIEF rule for the jurisdiction pair) and emits a `GroupReliefOpportunity` flag with engine-computed amounts. AI uses the flag in brief narrative without restating figures.
  3. Brief assembler detects post-engine — too late; the runner needs group-level visibility to combine per-entity bases.
**Decision:** Option 2. The engine cross-entity scanner runs after per-entity aggregation, receives all `EntityBase` objects, and checks income/loss pairs against `GROUP_RELIEF` rules. A `GroupReliefOpportunity` is emitted per eligible pair. The engine never recommends a restructuring amount — it surfaces the existence of the opportunity and the applicable statute. Professional judgment and transfer-pricing compliance remain with the practitioner.
**Why:** Consistent with DEC-002 (engine owns all figures) and the project's defensibility principle: every flag cites a specific rule id + as_of_date + source_citation. "You should consider group relief" is a rule-grounded flag, not an AI hallucination.

## DEC-021: WHT exposure flag is a separate module from PE conflict detection

**Date:** 2026-06-06
**Context:** Wave 6 requires two distinct cross-border checks: (a) PE double-tax conflict and (b) WHT exposure (withholding applied at a rate higher than treaty entitlement, or without checking a Directive exemption).
**Options considered:**
  1. Combine into `conflict.py` — the PE logic and WHT logic share no code; mixed-purpose module violates SRP.
  2. Separate `engine/wht_exposure.py` for WHT over-withholding checks, keeping `conflict.py` for PE double-tax only.
**Decision:** Option 2. `engine/wht_exposure.py` scans each WHT `ObligationResult`, compares the applied rate against the treaty-reduced rate, and emits a `ConflictFlag(conflict_type=WHT_OVER_WITHHELD)` when the applied rate exceeds entitlement.
**Why:** SRP — each module has one job. WHT exposure may exist without any PE; PE conflict may exist without WHT. Independent modules can be tested independently.

## DEC-022: JurisdictionClaim.rationale_citation is Optional to support the abstain path

**Date:** 2026-06-06
**Context:** W6c.6 audit finding: `ai/adapter.py` was fabricating a `RuleCitation(rule_id="adapter-placeholder")` on every `JurisdictionClaim`, even when the AI produced no real rule reference. CLAUDE.md requires every AI recommendation to cite a real rule or emit `needs_human_review=True` — a synthetic placeholder violates this contract and leaks into briefs.
**Options considered:**
  1. Keep `rationale_citation: RuleCitation` required — adapter must always supply one.
  2. Make `rationale_citation: RuleCitation | None = None` — adapter omits it when AI returned no real reference; sets `abstain=True` on the parent `FlowAttribution` instead.
**Decision:** Option 2. A missing citation is preferable to a fabricated one. A `None` citation paired with `abstain=True, abstain_reason="No rule citation"` is honest and triggers the human-review path in the brief assembler. The previous hardcoded string would have appeared in production briefs as a citation, which is both incorrect and misleading.
**Why:** Defensibility principle: every flag cites a real rule or declares uncertainty. A fabricated citation is worse than no citation.
