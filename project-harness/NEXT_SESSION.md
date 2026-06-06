# Session Handoff

**Branch:** `conflict-detection`
**Last completed:** ISSUE-008 fixed — ClaudeClient migrated to messages API; 183 tests green
**Test status:** 183 passed, 6 skipped (Neo4j integration) — `make test` green
**Status:** Waves 1, 3, 4a, 4b complete. Wave 5 ~85%. Wave 6 engine-side built. Wave 6b designed.

---

## Immediate next tasks (in order)

### 1. Wave 5 — W5.7 integration test (~45 min)
Write `tests/integration/test_engine_ai_pipeline.py`:
- Wire `AILayerAdapter(FakeClaudeClient(), loader)` → `EngineRunner`
- Run on golden scenario mock data (using `FakeGraphReader`)
- Assert all three entities produce `EngineRunResult` with non-empty obligations
- Assert no unexpected exceptions; assert PE Triangle conflict appears

### 2. Wave 6 — W6.4 WHT exposure flag (~1 hour)
New file: `engine/wht_exposure.py`.
- Scan each `ObligationResult` of type WHT
- Compare applied rate vs treaty-reduced rate from rule pack
- Emit `ConflictFlag(conflict_type=WHT_OVER_WITHHELD)` when rate exceeds entitlement
- Wire into runner; unit tests against T005 (DE→HK dividend: 25% statutory, 5% treaty → flag)

### 3. Wave 6 — W6.7 golden integration test (~45 min)
`tests/integration/test_conflict_golden.py`
- Full run → assert PE Triangle fires with: `attributed_income ≈ HKD 1,400,000`, `residual_double_tax = 0` (exemption method), `treaty_rule_id = "DE-FR-ART23-ELIMINATION"`
- Assert DE entity's CIT base is reduced by PE attribution
- Assert FR entity's CIT base includes PE attribution

### 4. Wave 6b — Group profit redistribution (~2–3 hours)
See Wave 6b section in ROADMAP.md. 7 tasks (W6b.1–W6b.7).
Implementation order: models → rule category → engine module → runner wiring → rule packs → tests.

---

## Key facts to remember

- **Layer rule:** `engine/` never imports from `ai/`. Protocols live in `common/`.
- **DEC-002:** AI emits no figures — all amounts in `GroupReliefOpportunity` are engine-computed.
- **Golden figures (EXPECTED.md):** HK HKD 445,500; DE CIT HKD 47,673; DE Trade Tax HKD 42,175; FR CIT HKD 1,030,938.
- **PE Triangle:** 185 days → PE triggered; exemption method → DE exempts attributed income; France taxes it alone; residual double-tax = 0.
- **ClaudeClient is fixed** — uses `messages.create()` with model from `settings.CLAUDE_MODEL` (default: `claude-haiku-4-5-20251001`).
- **Next ISSUE id:** ISSUE-009. **Next DEC id:** DEC-021.

---

## Where things live

- Forward roadmap: `project-harness/ROADMAP.md`
- Decisions: `project-harness/DECISIONS.md` (DEC-001–DEC-020)
- Issues: `project-harness/ISSUES.md` (next: ISSUE-009)
- Features tracker: `project-harness/FEATURES.md` (up to date as of this session)
- Working rules: `project-harness/CLAUDE.md`
