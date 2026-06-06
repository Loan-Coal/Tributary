# Session Handoff

**Branch:** `conflict-detection`
**Last completed:** W6b.1+W6b.2+W6b.3+W6b.6 — GroupReliefOpportunity model, EngineRunResult extension, GROUP_RELIEF rule category; golden pack absence verified
**Test status:** 208 passed, 6 skipped (Neo4j integration) — `make test` green
**Status:** Waves 1, 3, 4a, 4b, 5, 6 complete. Wave 6b: data contract done; W6b.4+W6b.5+W6b.7 pending.

---

## Immediate next tasks (in order)

### 1. Wave 6b — W6b.4+W6b.5+W6b.7: Engine scanner + wiring + tests (~60 min)
Files:
- `src/tributary/engine/group_relief.py` (new)
- `src/tributary/engine/runner.py` (edit — wire scanner after `_assemble_results`)
- `tests/unit/test_group_relief.py` (new)
- `tests/integration/test_engine_golden.py` (edit — add zero-opportunities guard)

Engine scanner spec (ROADMAP W6b.4):
- `scan_group_relief(bases, entities, loader)` → `list[GroupReliefOpportunity]`
- For each ordered pair (A has `net_income_hkd > 0`, B has unused losses):
  - Check if `GROUP_RELIEF` rule exists for the pair's jurisdictions
  - If yes: emit one `GroupReliefOpportunity` per eligible pair
  - If no: emit nothing (correct)
- `EntityBase` is in `engine/aggregator.py` — check its fields for `net_income_hkd` and `total_unused_losses_hkd`
- `entities` parameter provides `EntityRecord` list for entity metadata

Wiring (W6b.5):
- Call `scan_group_relief(bases, entities, loader)` in `EngineRunner._assemble_results`
- Result is a flat list; distribute to each `EntityRecord` whose `entity_id` == `opportunity.income_entity_id`
- Attach to `EngineRunResult.group_relief_opportunities`

Unit tests (W6b.7):
- Pair with GROUP_RELIEF rule → opportunity emitted (use fake entities + fake loader)
- Pair without rule → no opportunity (correct negative case)
- Golden scenario integration: zero opportunities (add to test_engine_golden.py)

### 2. Wave 7 — Brief assembly
Entry gate: Wave 6b complete. See ROADMAP.md Wave 7 tasks.

---

## Key facts to remember

- **Layer rule:** `engine/` never imports from `ai/`. Protocols live in `common/`.
- **DEC-002:** AI emits no figures — all amounts in engine outputs are engine-computed.
- **Golden figures (EXPECTED.md):** HK HKD 445,500; DE CIT HKD 47,673; DE Trade Tax HKD 42,175; FR CIT HKD 1,030,938.
- **GroupReliefMechanism** enum: GROUP_RELIEF | ORGANSCHAFT | INTEGRATION_FISCALE | TRANSFER_PRICING_NOTE
- **EngineRunResult.group_relief_opportunities** defaults to `[]` — already in place.
- **W6b exit gate:** golden scenario produces ZERO GroupReliefOpportunities (HK/DE/FR no bilateral group relief).
- **EntityBase** — check `engine/aggregator.py` for `net_income_hkd` field name before coding.
- **Next ISSUE id:** ISSUE-009. **Next DEC id:** DEC-021.

---

## Where things live

- Forward roadmap: `project-harness/ROADMAP.md`
- Decisions: `project-harness/DECISIONS.md` (DEC-001–DEC-020)
- Issues: `project-harness/ISSUES.md` (next: ISSUE-009)
- Features tracker: `project-harness/FEATURES.md`
- Working rules: `project-harness/CLAUDE.md`
