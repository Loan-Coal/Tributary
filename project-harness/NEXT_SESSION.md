# Session Handoff

**Branch:** `conflict-detection`
**Last completed:** W6.4 — `engine/wht_exposure.py` + 14 unit tests; W5.1–W5.7 ticked
**Test status:** 197 passed, 6 skipped (Neo4j integration) — `make test` green
**Status:** Waves 1, 3, 4a, 4b, 5 complete. Wave 6: W6.1–W6.6 done; W6.7 pending.

---

## Immediate next tasks (in order)

### 1. Wave 6 — W6.7 PE Triangle golden integration test (~45 min)
New file: `tests/integration/test_conflict_golden.py`
- Full engine run → assert PE Triangle fires with:
  - `attributed_income ≈ HKD 1,023,750`
  - `residual_double_tax = 0` (exemption method)
  - `treaty_rule_id = "DEFR-DTA-ELIMINATION"`
  - `relief_mechanism = EXEMPTION`
- Assert DE entity's CIT base reduced by PE attribution
- Assert FR entity's CIT base includes PE attribution
- Also assert zero WHT_OVER_WITHHELD flags (regression guard on W6.4)
This closes Wave 6 entirely.

### 2. Wave 6b — Group profit redistribution (~2–3 hours)
See Wave 6b section in ROADMAP.md. 7 tasks (W6b.1–W6b.7).
Implementation order: models → rule category → engine module → runner wiring → rule packs → tests.

### 3. Wave 7 — Brief assembly
Entry gate: Wave 6 complete. See ROADMAP.md Wave 7 tasks.

---

## Key facts to remember

- **Layer rule:** `engine/` never imports from `ai/`. Protocols live in `common/`.
- **DEC-002:** AI emits no figures — all amounts in engine outputs are engine-computed.
- **Golden figures (EXPECTED.md):** HK HKD 445,500; DE CIT HKD 47,673; DE Trade Tax HKD 42,175; FR CIT HKD 1,030,938.
- **PE Triangle:** 185 days → PE triggered; exemption method → DE exempts attributed income; France taxes it alone; residual double-tax = 0.
- **WHT exposure:** scanner in `engine/wht_exposure.py`; golden scenario produces ZERO WHT_OVER_WITHHELD flags (all treaty rates correctly applied).
- **get_treaty_rate** is now a public function in `engine/wht_engine.py` (renamed from `_treaty_rate`).
- **Next ISSUE id:** ISSUE-009. **Next DEC id:** DEC-021.

---

## Where things live

- Forward roadmap: `project-harness/ROADMAP.md`
- Decisions: `project-harness/DECISIONS.md` (DEC-001–DEC-020)
- Issues: `project-harness/ISSUES.md` (next: ISSUE-009)
- Features tracker: `project-harness/FEATURES.md`
- Working rules: `project-harness/CLAUDE.md`
