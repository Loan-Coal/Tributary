# Session Handoff

**Branch:** `conflict-detection`
**Last completed:** W6c.5 — runner._cit_rule() guarded; EngineError on missing CIT rule; 220 tests green
**Test status:** 220 passed, 6 skipped — `make test` green
**Status:** Wave 6c active. W6c.1–W6c.5 ticked. Next: W6c.6 (fabricated adapter-placeholder citation).

---

## Immediate next tasks (in order)

### 1. Wave 6c — W6c.6: fabricated adapter-placeholder citation (~20 min)
Files:
- `src/tributary/ai/adapter.py` (edit — `_to_attribution()`, lines ~139-142)
- `tests/unit/test_ai_adapter.py` (add — no RuleCitation with "placeholder" in rule_id)

Fix: replace `RuleCitation(rule_id="adapter-placeholder", ...)` with `abstain=True, needs_human_review=True`
and empty `rule_citations=[]`; no synthetic citation should ever enter a brief.

### 2. Wave 6c — W6c.7: service.py in-place Pydantic mutation (~10 min)
Files:
- `src/tributary/ai/service.py` (edit — line ~42, replace in-place mutation with model_copy)
- related test file (add — mismatched transaction ID raises AILayerError or logs warning)

### 3. Wave 6c — W6c.8: common/__init__.py missing GroupRelief exports (~5 min)
Files:
- `src/tributary/common/__init__.py` (edit — add GroupReliefOpportunity + GroupReliefMechanism to imports and __all__)

---

## Key facts to remember

- **Next ISSUE id:** ISSUE-027. **Next DEC id:** DEC-021.
- **Layer rule:** `engine/` never imports from `ai/`. Protocols live in `common/`.
- **DEC-002:** AI emits no figures — all amounts in engine outputs are engine-computed.
- **Golden figures (EXPECTED.md):** HK HKD 445,500; DE CIT HKD 47,673; DE Trade Tax HKD 42,175; FR CIT HKD 1,030,938.
- **W6c P1 priority:** fabricated `adapter-placeholder` citations (W6c.6) and `rules/db.py` layer violation (W6c.9) are the highest-impact remaining fixes.
- **W6c.9 (rules/db.py move) is risky** — it deletes a file and touches all its callers. Do not attempt in a long context; start it fresh.
- **W6b entry gate updated:** Wave 6b remaining tasks (W6b.4+W6b.5+W6b.7) require Wave 6c complete first.
- **conflict_id format (updated):** `f"PE-{pe.entity_id}-{pe.residence_jurisdiction}-{conflict_year}"` (e.g. `PE-MERID-DE-DE-2025`)

---

## Wave 6c task queue (full ordered list)

**P1a — business integrity (regression test first each time):**
- [x] W6c.1 — wht_engine.py:98 silent 0% WHT bug
- [x] W6c.2 — EU_MEMBER_JURISDICTIONS out of engine/
- [x] W6c.3 — Zinsschranke negative EBITDA clamp
- [x] W6c.4 — conflict_id collision (include entity_id)
- [x] W6c.5 — runner.py unguarded [0] index
- [ ] W6c.6 — adapter.py fabricated adapter-placeholder citation
- [ ] W6c.7 — service.py in-place Pydantic mutation
- [ ] W6c.8 — common/__init__.py missing GroupRelief exports

**P1b — architecture violations:**
- [ ] W6c.9+10+11 — rules/db.py → ai/retrieval_db.py (move, typed models, error logging — do as one unit)
- [ ] W6c.12 — ai/protocols.py delete; import from common
- [ ] W6c.13 — adapter.py _map_citation isinstance guard

**P2 — quality:**
- [ ] W6c.14 — function extractions (8 engine functions over 40 lines)
- [ ] W6c.15 — loss_ledger limitation_rule_id audit trail
- [ ] W6c.16 — runner PE multi-entity limitation (ISSUES.md note or fix)
- [ ] W6c.17 — qwen_client.py torch import guard
- [ ] W6c.18 — client.py temperature not passed
- [ ] W6c.19 — LLMClientProtocol definition
- [ ] W6c.20 — TransactionContext extra="forbid"
- [ ] W6c.21 — rag_retriever.py docstring + signature align
- [ ] W6c.22 — adapter.py rule_type="unknown" magic string
- [ ] W6c.23 — loader.py broad except Exception
- [ ] W6c.24 — logging.py merge conflict marker
- [ ] W6c.25 — FiscalCalendar cross-field date validator
- [ ] W6c.26 — PromptLoaderError inheritance fix
- [ ] W6c.27 — ConfigurationError in common/errors.py
- [ ] W6c.28 — deferred imports hoist (cit_engine, deadlines)
- [ ] W6c.29 — ruff --fix sweep
- [ ] W6c.30 — test coverage push to >=80%

---

## Where things live

- Forward roadmap: `project-harness/ROADMAP.md`
- Audit findings: `project-harness/REVIEW.md`
- Decisions: `project-harness/DECISIONS.md` (DEC-001–DEC-020)
- Issues: `project-harness/ISSUES.md` (next: ISSUE-027)
- Features tracker: `project-harness/FEATURES.md`
- Working rules: `project-harness/CLAUDE.md`
