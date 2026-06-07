# Session Handoff

**Branch:** `main`
**Last completed:** Wave 8 — demo hardened; cached AI narrator; offline demo ready
**Test status:** 279 passed — `make test` green
**Status:** All waves 1–8 complete. Next planned: Wave 9 (RAG rule extraction).

---

## Next session

### Wave 9 — RAG rule extraction

Planned scope (detail at session start):
- Ingest HK IRO / German KStG / FR CGI text into the retrieval DB
- `ai/service.py` routes `get_rules(jurisdiction, flow_type)` through RAG retriever
- Evaluation harness: compare RAG-extracted rules against `data/rules/*.json` ground truth
- Hallucination guard: any extracted rate that differs from the JSON pack by >0.5pp emits `needs_review=True` with both values shown

Infrastructure already in place: `ai/rag_retriever.py` and `ai/retrieval_db.py`.

---

## Key facts to remember

- **Next ISSUE id:** ISSUE-028. **Next DEC id:** DEC-026.
- **Layer rule:** `engine/` never imports from `ai/`. Protocols live in `common/`.
- **DEC-002:** AI emits no figures — all amounts in engine outputs are engine-computed.
- **Lenovo data source:** `data/raw/lenovo_consolidated_*.csv` — 4 fiscal years (FY2022–FY2025, March year-end). Normaliser uses `_LATEST_PERIOD = "2025-03-31"`.
- **Engine reference year:** `_GOLDEN_REFERENCE_YEAR = 2025` in `engine/cli.py` → fiscal periods are calendar 2025 (DE/US) and Apr 2025–Mar 2026 (HK).
- **Entities:** LENOVO-HK (HK), LENOVO-DE (DE), LENOVO-US (US) — 3 entities from Lenovo CSVs.
- **EXPECTED.md canonical figures (Lenovo data):** DE CIT HKD 429,541; DE Trade Tax HKD 380,005; US CIT HKD 682,671.

---

## Where things live

- Forward roadmap: `project-harness/ROADMAP.md`
- Decisions: `project-harness/DECISIONS.md`
- Issues: `project-harness/ISSUES.md` (next: ISSUE-028)
- Working rules: `project-harness/CLAUDE.md`
