# Tributary — Hackathon Roadmap

**Goal:** End-to-end demo: Meridian Group (HK/DE/FR/US multinational) → 4 fully cited filing briefs + cross-border conflict report (The PE Triangle).

Each wave = one focused coding session. The system is runnable and testable at the end of every wave. See `DECISIONS.md` for the rationale behind every major choice.

---

## Architecture constraints (carried through all waves)

- **Engine is country-agnostic.** No jurisdiction-specific `if` statements in engine code. All country-specific values come from rule packs. New country = new JSON file, zero engine code change. (DEC-006). _Note: the engine reads jurisdictions from entities in the graph — `jurisdictions = sorted({e.resident_jurisdiction for e in entities})`. No jurisdiction codes are hardcoded in engine logic. The `EU_MEMBER_JURISDICTIONS` constant in `common/jurisdictions.py` is reference data for WHT directive checks — not a hardcoded set of supported countries._
- **AI emits no figures.** All amounts, rates, thresholds, deadlines are engine-computed. (DEC-002). _The AI layer is used for: (1) flow classification (royalty vs. dividend vs. service), (2) jurisdiction attribution (which jurisdiction claims this flow), (3) brief narrative prose. It does NOT determine tax rates or thresholds — those come from rule packs._
- **Rule packs are the source of tax law.** Rates, thresholds, deadlines, and treaty terms are encoded in `data/rules/<jurisdiction>.json` — authored by humans from authoritative statutory sources, with `source_citation` on every rule. The AI retrieves summaries of these rules as context for flow classification; it does not interpret raw tax codes at runtime. (DEC-024: RAG extraction is Wave 9)
- **`source_flow_ids` on every `ObligationResult`.** Mandatory — enables conflict detection.
- **Loss carryforward in scope.** Engine handles prior-period loss offset with jurisdiction-specific limitation rules. (DEC-008)
- **Graph layer is a separate concern.** Engine depends on `GraphReader` / `GraphWriter` protocols only. Neo4j implementation is injected.
- **Base currency is HKD (internal only).** The engine stores and computes all amounts in HKD. Briefs display amounts in the jurisdiction's local currency by applying the inverse FX rate at render time. FX rates are loaded from `data/golden/fx_rates.json`.

---

## Carry-forward notes

_Keep under 15 lines. Delete consumed lines._

- **Waves 1–8 COMPLETE**: 4-entity golden scenario (HK/DE/FR/US), 279 tests green, PE Triangle fires, cached AI narrator, offline demo ready.
- **EXPECTED.md canonical figures**: HK HKD 445,500; DE CIT HKD 47,673; DE Trade Tax HKD 42,175; FR CIT HKD 1,030,938; US CIT HKD 816,900.
- **Next ISSUE id**: ISSUE-028. **Next DEC id**: DEC-026.
- **Wave 9 (RAG)**: next session — extract rules from HK IRO / KStG / FR CGI text.

---

## Completed waves (summary)

| Wave | Deliverable | Status |
|------|-------------|--------|
| Wave 1 | Repo scaffold, Pydantic models, golden data, EXPECTED.md | ✅ Done |
| Wave 2 | Ingestion pipeline, Neo4j GraphReader/GraphWriter | ✅ Done |
| Wave 3 | Rule-pack contract + HK, DE, FR JSON packs + DE-FR treaty | ✅ Done |
| Wave 4a | Engine orchestrator skeleton, aggregator, attribution stub | ✅ Done |
| Wave 4b | CIT, WHT, VAT-threshold, Trade Tax, deadlines, loss ledger | ✅ Done |
| Wave 5 | AI layer: classifier, attributor, rule retriever, Claude adapter | ✅ Done |
| Wave 6 | Conflict detection: PE attribution, double-tax flags, WHT exposure | ✅ Done |
| Wave 6c | Audit remediation: all 13 P1s + 17 P2s resolved, coverage ≥80% | ✅ Done |
| Wave 6b (partial) | GroupReliefOpportunity model + GROUP_RELIEF rule category | ✅ Data contract done |
| Wave 7a | Brief output quality: currency rendering, WHT structure, narrator wiring, FX footnote | ✅ Done |
| Wave 7b | VAT obligation sections: FR brief contains [VAT] section with filing deadline | ✅ Done |
| Wave 7c | Golden scenario alignment: round_amount rename, DEC-025, jurisdiction literal audit | ✅ Done |
| Wave 7d | USA 4th entity: MERID-US, us.json, T010/T011, US WHT, EXPECTED.md, 7 tests | ✅ Done |
| Wave 8 | Demo hardening: CachedNarratorClient, offline demo, DEMO_SCRIPT.md | ✅ Done |

---

## Wave 6b — Group profit redistribution detection (remaining tasks)

**Owner:** engine owner
**Deliverable:** cross-entity scanner emitting `GroupReliefOpportunity` flags where jurisdiction-level group-relief rules exist. Golden scenario (HK/DE/FR — no bilateral group relief) must produce zero opportunities.

**Entry:** Wave 6c complete ✅
**Exit gate:** golden scenario emits zero opportunities; fabricated two-entity test (income + loss entity in a jurisdiction with a GROUP_RELIEF rule) emits one opportunity with correct fields.

### Verification step (do first)
Check `engine/runner.py` for the `scan_group_relief` call. The carry-forward notes from W6b.5 suggest it was wired. If already wired and W6b tests pass — mark all tasks done and skip to Wave 7a.

### Tasks
- [ ] **W6b.4** — `engine/group_relief.py`: verify cross-entity scanner is complete and correct — for each ordered pair (A has income, B has unused losses), checks `GROUP_RELIEF` rule exists for the jurisdiction pair; emits `GroupReliefOpportunity`; no flag if no rule.
- [ ] **W6b.5** — verify wiring in `engine/runner.py`: `scan_group_relief(bases, entities, loader)` called after `_assemble_results`; results attached to each `EngineRunResult`.
- [ ] **W6b.7** — unit tests: income+loss pair with GROUP_RELIEF rule → opportunity emitted; same pair without rule → no flag; golden scenario → zero opportunities (regression guard).

---

## Wave 7a — Brief output quality

**Owner:** engine owner + brief layer
**Deliverable:** All currency display, labelling, WHT presentation, narrator wiring, and needs-review reason bugs fixed. MERID-DE CIT figure matches EXPECTED.md. Briefs are readable by a non-HK tax professional without currency confusion.

**Entry:** Wave 6b complete ✅ (or verified)
**Exit gate:**
- DE brief shows EUR amounts; FR brief shows EUR amounts; HK brief shows HKD.
- PE days threshold renders "185 days vs limit 183 days" — no currency label.
- WHT sections show gross → treaty → net structure.
- Narrator wired and produces non-empty prose per section.
- As-of dates only include rules that produced an obligation.
- Every `⚠ Needs review` flag has a human-readable reason.
- MERID-DE CIT = HKD 47,673 (matches EXPECTED.md, ISSUE-027 fixed).

### Background: confirmed output bugs

1. **Currency labels wrong for non-HK entities** — `renderer.py:_fmt_hkd()` hardcodes `"HKD"` unconditionally.
2. **PE days labelled "HKD"** — `ThresholdResult` reuses `threshold_value_hkd`/`actual_value_hkd` fields for day counts. Renderer calls `_fmt_hkd()` producing "183 HKD" for a day count.
3. **WHT presentation misleads** — shows `Rate: 0.000% | Tax obligation: HKD 0` with separate `Treaty relief: HKD 90,000`. Should show gross statutory WHT → treaty reduction → net.
4. **AI narrator disabled** — `cli.py` passes `narrator=None` to `BriefAssembler`.
5. **As-of dates section bloated** — rule IDs that produced no obligation appear in as-of dates.
6. **Needs-review has no reason** — every `⚠ Needs review` flag has no explanation text.
7. **MERID-DE CIT discrepancy** — brief shows ~HKD 300,873; EXPECTED.md says HKD 47,673 (ISSUE-027). Likely pre-loss-relief base being displayed.
8. **No FX rate context** — non-HK briefs contain no indication of what EUR/HKD rate was applied.

### Tasks (execute in this order — avoids rework)

- [ ] **W7a.4** — `brief/assembler.py` + `brief/renderer.py`: load `data/golden/fx_rates.json`; build jurisdiction → `(local_currency, fx_rate)` mapping; extend `render_brief_markdown` signature to accept `local_currency: str` and `fx_rate: Decimal`. Mapping: HK → HKD (rate 1.0), DE → EUR (8.50), FR → EUR (8.50). Make data-driven from fx_rates.json, not hardcoded.
- [ ] **W7a.0** — investigate and fix ISSUE-027: step through `engine/entity_run.py` for MERID-DE and confirm whether loss-ledger is applied before or after `ObligationResult` is assembled. Fix in the responsible file. Add regression test in `tests/integration/test_engine_golden.py` asserting CIT = HKD 47,673 for MERID-DE.
- [ ] **W7a.1** — `brief/renderer.py`: replace `_fmt_hkd()` with `_fmt_amount(amount, currency)` that takes the local currency code. Add `_fmt_local(amount_hkd, fx_rate, currency)` for converting from HKD internal representation. Use the local currency + FX rate passed in from W7a.4.
- [ ] **W7a.2** — `brief/renderer.py` + `common/models_engine.py`: add `unit: str = "HKD"` to `ThresholdResult`. Set `unit = "days"` in `engine/pe.py` for service_pe_days thresholds. Renderer branches on `unit` — "days" renders as `"{value} days"`, otherwise uses `_fmt_local`.
- [ ] **W7a.3** — `brief/renderer.py`: fix WHT section. Show: `Statutory WHT: {gross} | Treaty relief: -{treaty_relief} | Net obligation: {net}`. Only show the statutory rate from the rule, not the post-treaty effective rate. Verify `ObligationResult` carries `gross_amount_hkd` and `treaty_relief_hkd`; add to `common/models_engine.py` if missing.
- [ ] **W7a.5** — `brief/renderer.py`: filter `brief.as_of_dates` to only include rule IDs that appear in obligation `rule_id` fields in that brief's sections.
- [ ] **W7a.7** — `brief/renderer.py`: add FX rate footnote to brief header for non-HKD jurisdictions: `*Amounts shown in EUR at EUR/HKD = 8.50 (ECB reference, 2025-01-01)*`.
- [ ] **W7a.9** — `common/models_engine.py` + relevant engine files + `brief/renderer.py`: add `review_reason: str | None` to `ObligationResult`. Populate from `engine/vat_engine.py`, `engine/pe.py`, `engine/attribution_stub.py` using the reasons documented in `data/golden/EXPECTED.md` section 8. Render as explanatory text after the `⚠ Needs review` flag.
- [ ] **W7a.6** — `engine/cli.py` + `brief/assembler.py`: wire AI narrator — construct `BriefNarrator` using `ai/adapter.py` Claude adapter (not "the engine's client" — the engine has no AI client). Inject via `BriefAssembler(narrator=BriefNarrator(client=...))`. Gate behind `TRIBUTARY_AI_ENABLED` env flag (default off) so `make demo` runs offline.
- [ ] **W7a.8** — regression tests in `tests/unit/test_renderer.py` (new file): DE brief renders EUR amounts; FR brief renders EUR amounts; HK brief renders HKD; PE days threshold renders "185 days vs limit 183 days" with no currency label; WHT section shows gross → relief → net structure; narrator output is non-empty string for each section when AI enabled.

---

## Wave 7b — VAT obligation sections

**Owner:** engine owner
**Deliverable:** When a VAT registration threshold is breached, the brief contains a `[VAT]` obligation section (filing obligation + deadline), not just an open question.

**Entry:** Wave 7a complete
**Exit gate:** MERID-FR brief contains a `[VAT]` section citing `FR-VAT-THRESHOLD` and `FR-VAT-FILING`; the section states the threshold breach and the quarterly filing obligation with deadline; no net VAT arithmetic is computed.

### Tasks

- [ ] **W7b.1** — `engine/vat_engine.py`: when `vat_threshold_check` is breached, also emit an `ObligationResult(obligation_type=VAT)` with `taxable_base_hkd = actual_turnover`, `rate = Decimal("0")`, `net_amount_hkd = Decimal("0")`, `needs_review = True`, `review_reason = "VAT net arithmetic not modelled; filing obligation requires quarterly returns."`.
- [ ] **W7b.2** — `engine/entity_run.py`: wire `vat_engine` VAT obligation output through into the `EngineRunResult.obligations` list.
- [ ] **W7b.3** — `brief/renderer.py`: render VAT sections with: `Registration threshold breached — quarterly VAT returns required. Net VAT arithmetic not modelled (scope: Wave 7b+).`
- [ ] **W7b.4** — unit tests: FR entity above VAT threshold → `ObligationResult(obligation_type=VAT)` emitted; DE entity below threshold → no VAT obligation; brief renderer includes `[VAT]` section for FR.

---

## Wave 7c — Golden scenario alignment

**Owner:** any
**Deliverable:** CLAUDE.md updated; jurisdiction literals in non-data code files eliminated; HKD-branded utilities renamed.

**Entry:** DEC-023 documented ✅ (done in pre-wave housekeeping)
**Exit gate:** `grep -rn "FR\|DE\|HK" src/` returns only: (a) `common/jurisdictions.py` EU list, (b) no literals in engine/brief/ai Python logic code. CLAUDE.md header matches entities.json (HK + DE + FR + US).

### Tasks

- [ ] **W7c.1** — Confirm DEC-023 is logged in DECISIONS.md (done ✅ in pre-wave). No further action.
- [ ] **W7c.2** — Update `CLAUDE.md` "Jurisdictions" table to list HK + DE + FR + US (US added per DEC-023; Wave 7d adds MERID-US to entities.json).
- [ ] **W7c.3** — Audit for jurisdiction literals in Python source: `grep -rn '"HK"\|"DE"\|"FR"\|"US"' src/tributary/`. Classify each hit as: (a) reference data (acceptable), (b) config constant (move to settings), (c) logic hardcode (must fix). Log any fixes needed as ISSUES.
- [ ] **W7c.4** — `engine/money.py`: rename `round_hkd` → `round_amount` and `_HKD_QUANTUM` → `_UNIT_QUANTUM`. Update all callers. Document in ISSUES.md that only renamed, not changed in behaviour.
- [ ] **W7c.5** — `engine/runner.py`: document why `_BASE_CURRENCY = "HKD"` in DECISIONS.md as DEC-025. Keep value unchanged.

---

## Wave 7d — USA as 4th entity

**Owner:** engine owner
**Deliverable:** Meridian Group expanded to 4 entities (MERID-HK, MERID-DE, MERID-FR, MERID-US). `make run-golden` produces 4 briefs.

**Entry:** Wave 7b complete (brief structure stable before adding a 4th entity)
**Exit gate:** `make run-golden` produces 4 briefs (HK, DE, FR, US); US obligations match EXPECTED.md; all existing 245+ tests still pass.

### Tasks

- [ ] **W7d.1** — `data/golden/entities.json`: add MERID-US as a US subsidiary. Resident jurisdiction: `US`. Fiscal year: Jan–Dec 2025. Relationship: subsidiary of MERID-HK or MERID-DE (decide at implementation time based on golden narrative fit).
- [ ] **W7d.2** — `data/golden/transactions.json`: add at least one US-touching flow — a dividend from MERID-US upward (to MERID-HK or MERID-DE) and optionally an intercompany service fee.
- [ ] **W7d.3** — `data/rules/us.json`: federal CIT rate 21% (IRC §11), outbound WHT on dividends 30% domestic (IRC §881), FDII deduction flagged `needs_review=True`, GILTI inclusion flagged `needs_review=True`, filing deadline April 15 / extended October 15 (IRC §6072). Source every rule to IRC section.
- [ ] **W7d.4** — `data/rules/treaties/`: author the applicable DTA for the US flows (e.g. `hk_us.json` for MERID-HK as parent — note: HK-US DTA does not exist; flag as `needs_review=True` with reason "No HK-US DTA in force; domestic 30% WHT applies unless restructured via third country"). If MERID-US is a subsidiary of MERID-DE, author `de_us.json` instead.
- [ ] **W7d.5** — `data/golden/EXPECTED.md`: hand-compute US obligations (CIT on taxable income, WHT on dividend upward). Mark FDII/GILTI as needs_review. Update totals section.
- [ ] **W7d.6** — `common/jurisdictions.py`: add `US` constant. Update `CLAUDE.md` jurisdictions table to HK + DE + FR + US.
- [ ] **W7d.7** — run `make run-golden`; verify 4 briefs generated; fix any engine issues surfaced by MERID-US (all values must match EXPECTED.md).
- [ ] **W7d.8** — tests: `tests/integration/test_engine_golden.py` — US entity produces expected CIT obligation; US WHT payable correct; golden run produces 4 briefs including conflict report.

---

## Wave 8 — Demo hardening

**Owner:** both
**Deliverable:** Cached AI outputs; `make demo` runs offline-safe; briefs readable end-to-end; rehearsed demo.

**Entry:** Waves 7a + 7b + 7d complete
**Exit gate:** `make demo` runs without live Claude API; briefs show correct local currencies; PE Triangle conflict highlighted; 4 entity briefs present; rehearsed Q&A documented.

### Tasks

- [ ] **W8.1** — snapshot AI outputs for golden dataset to `data/golden/ai_cache/`
- [ ] **W8.2** — `make demo` runs entirely on cached AI (never hits Claude live)
- [ ] **W8.3** — terminal brief output: `make run-golden` output is clean and readable end-to-end in the terminal. No web UI development (terminal is sufficient for demo).
- [ ] **W8.4** — graph view: document in `DEMO_SCRIPT.md` how to open Neo4j Browser at `localhost:7474` to show entity ownership and fund flows (T001–T009). No new frontend code.
- [ ] **W8.5** — rehearse demo; document Q&A in `project-harness/DEMO_SCRIPT.md`

---

## Wave 9 — RAG rule extraction (next session after demo)

**Owner:** AI layer owner
**Deliverable:** AI extracts applicable rates, thresholds, and deadlines from a corpus of tax documents, replacing static JSON pack lookup for at least one jurisdiction. `ai/rag_retriever.py` and `ai/retrieval_db.py` provide partial infrastructure.

**Entry:** Wave 8 complete (demo hardened; ground-truth JSON packs available for evaluation)
**Exit gate:** RAG-extracted rules for one jurisdiction match JSON pack ground truth within ±0.5pp for all rate fields; hallucination guard emits `needs_review=True` on any divergence; eval harness passing.

### Planned scope (detail in next session's planning wave)

- Ingest HK IRO / German KStG / FR CGI text into the retrieval DB
- `ai/service.py` routes `get_rules(jurisdiction, flow_type)` through RAG retriever
- Evaluation harness: compare RAG-extracted rules against `data/rules/*.json` ground truth
- Hallucination guard: any extracted rate that differs from the JSON pack by >0.5pp emits `needs_review=True` with both values shown

---

## Expansion roadmap (post-hackathon, reference only)

| Code | Expansion | Notes |
|------|-----------|-------|
| E1 | Statutory form filling | Brief fields → country statutory forms (HK BIR51 first). Scope-explosion zone. |
| E2 | Real licensed rule data | IBFD / Bloomberg Tax behind existing pack interface |
| E3 | Real ingestion connectors | Xero / QuickBooks / ERP; Open APIs |
| E4 | New jurisdictions (SG, UK) | New JSON packs only, zero engine code change (DEC-006) |
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
| 6 | 2026-06-06 | 6b+audit | W6b.1–W6b.3, W6b.6 done (GroupReliefOpportunity model, GROUP_RELIEF rule category); full codebase audit — 13 P1s, 17 P2s, 12 nits logged in REVIEW.md | 208 tests green; Wave 6c (remediation) written and queued before Wave 7 |
| 7 | 2026-06-06 | 6c | All Wave 6c P1 + P2 audit remediations complete | 245 tests green, coverage ≥80%, ruff 0 hits |
| 8 | 2026-06-07 | analysis | Output analysis: identified 8 bugs in brief renderer + missing VAT sections + AI narrator disabled; FR vs USA discrepancy flagged; AI-role question raised; roadmap rewritten | Roadmap updated; no code changed |
| 9 | 2026-06-07 | planning | Roadmap review: 10 flaws identified; DEC-023 (USA 4th entity), DEC-024 (JSON+RAG plan) written; ISSUE-027 (CIT discrepancy) filed; W7a re-ordered; Wave 7d (US entity) and Wave 9 (RAG) added | DECISIONS.md + ISSUES.md + ROADMAP.md updated; no code changed |
| 10 | 2026-06-07 | 7a–8 | W7a (renderer rewrite, FX, WHT, VAT, narrator wiring), W7b (VAT obligations), W7c (round_amount rename, DEC-025), W7d (MERID-US 4th entity, us.json, T010/T011), W8 (CachedNarratorClient, offline demo, DEMO_SCRIPT.md) | 279 tests green; 4-entity golden scenario complete; demo runs offline |
