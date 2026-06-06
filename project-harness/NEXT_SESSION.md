# Session Handoff

**Branch:** `main`
**Last completed:** Harness setup (copied from NPCSystem, stripped NPC content, rewritten for Tributary).
**Status:** No code written yet. Harness is ready. Ready to begin Phase 0.

---

## Next task — Phase 0: Foundations & golden scenario

See `ROADMAP.md` Phase 0 for the full task list. Recommended starting order:

1. **P0.1** — scaffold repo structure + Docker Compose (Neo4j) + Makefile skeleton
2. **P0.3** — decide final jurisdiction set; record in `DECISIONS.md`
3. **P0.2** — define normalized data schema (Pydantic models in `common/models.py`)
4. **P0.4 + P0.5** — author golden mock files + hand-compute expected values
5. **P0.6** — document the planted cross-border conflict design
6. **P0.7** — seed graph; verify traversal

**Decision needed before P0.4:** Which 4 jurisdictions? Suggested: HK, Germany (EU), US, Singapore.
This affects what the golden scenario includes and what rule packs are authored in Phase 2.

## Key design constraints (do not forget)

- AI emits no figures. Engine owns all numbers.
- Every rule application cites: rule id + as_of_date + source_citation.
- as_of_date always surfaced in output.
- Build engine and test it against hand-computed values BEFORE wiring AI (Phase 4).
- Freeze/cache AI outputs for the demo golden dataset (Phase 7).

## Where things live

- Forward roadmap: `project-harness/ROADMAP.md`
- Decisions: `project-harness/DECISIONS.md`
- Issues: `project-harness/ISSUES.md` (next issue ID: ISSUE-001)
- Features tracker: `project-harness/FEATURES.md`
- Working rules: `project-harness/CLAUDE.md`
