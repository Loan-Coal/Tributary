# Session Handoff

**Branch:** `conflict-detection`
**Last completed:** W6.7 — PE Triangle integration test complete (3 new guard assertions); Wave 6 fully closed
**Test status:** 200 passed, 6 skipped (Neo4j integration) — `make test` green
**Status:** Waves 1, 3, 4a, 4b, 5, 6 complete. Next: Wave 6b (group relief detection).

---

## Immediate next tasks (in order)

### 1. Wave 6b — W6b.1+W6b.2: Models slice (~30 min)
Files: `src/tributary/common/models_engine.py`, `tests/unit/test_models_engine.py`
- Add `GroupReliefOpportunity` Pydantic model with all fields per ROADMAP W6b.1
- Extend `EngineRunResult` with `group_relief_opportunities: list[GroupReliefOpportunity] = []` (W6b.2)
- Unit tests: model instantiation, field validation, `needs_review` defaults to True

### 2. Wave 6b — W6b.3+W6b.6: Rule category + rule pack updates (~20 min)
Files: `src/tributary/rules/models.py`, `data/rules/hk.json`, `data/rules/de.json`, `data/rules/fr.json`
- Add `GROUP_RELIEF` to `RuleCategory` enum (W6b.3)
- Golden scenario (HK/DE/FR) correctly has NO bilateral group relief rules — zero rules to add, but verify loader handles missing category cleanly

### 3. Wave 6b — W6b.4+W6b.5+W6b.7: Engine module + wiring + tests (~60 min)
Files: `src/tributary/engine/group_relief.py` (new), `src/tributary/engine/runner.py`, `tests/unit/test_group_relief.py`
- `scan_group_relief(bases, entities, loader)` cross-entity scanner
- Wire into `runner.py` after `_assemble_results`
- Unit tests: income+loss pair WITH GROUP_RELIEF rule → opportunity emitted; WITHOUT → nothing; golden → zero opportunities

---

## Key facts to remember

- **Layer rule:** `engine/` never imports from `ai/`. Protocols live in `common/`.
- **DEC-002:** AI emits no figures — all amounts in engine outputs are engine-computed.
- **Golden figures (EXPECTED.md):** HK HKD 445,500; DE CIT HKD 47,673; DE Trade Tax HKD 42,175; FR CIT HKD 1,030,938.
- **PE Triangle:** 185 days → PE triggered; exemption method → residual double-tax = 0. Fully verified in `TestPeTriangleConflict` (test_engine_golden.py).
- **WHT exposure:** golden produces ZERO WHT_OVER_WITHHELD flags — verified by `TestWhtExposureRegressionGuard`.
- **Next ISSUE id:** ISSUE-009. **Next DEC id:** DEC-021.
- **W6b exit gate:** golden scenario produces ZERO GroupReliefOpportunities (HK/DE/FR have no bilateral group relief).

---

## Where things live

- Forward roadmap: `project-harness/ROADMAP.md`
- Decisions: `project-harness/DECISIONS.md` (DEC-001–DEC-020)
- Issues: `project-harness/ISSUES.md` (next: ISSUE-009)
- Features tracker: `project-harness/FEATURES.md`
- Working rules: `project-harness/CLAUDE.md`
