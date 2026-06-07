# HONESTY.md

> Mandatory disclosure for the hackathon. This file lives at the root of the repository. Judges cross-check it against the code and the technical video.
>
> **The deal:** disclosed shortcuts are **not** penalized. Hidden ones are. Undisclosed pre-built code is heavily penalized, each undisclosed mock carries a small penalty, and a faked demo is heavily penalized. Telling the truth here costs nothing.

---

## 1. Team — who did what

Verified against `git shortlog -sn --no-merges`.

| Member | GitHub handle | Main contributions |
|---|---|---|
| Lohann Colle | @Loan-Coal | Architecture, engine orchestration, brief layer, wave coordination |
| Zeyu Chen | @ZeyuuuChen | AI layer, RAG + classification |
| Shruti Singh | @SinghShruti8 | Neo4j graph layer, report output |
| Rishabh Gupta | @RishabhGupta07 | Data retrieval, data normalization |

---

## 2. What is fully working

Features that run end-to-end on the live app with real logic.

- **Multi-jurisdiction tax engine** — CIT, WHT, VAT threshold check, and German Trade Tax computed deterministically from JSON rule packs for HK, DE, FR, and US. All figures match hand-computed golden values in `data/golden/EXPECTED.md`.
- **PE Triangle conflict detection** — MERID-DE's 185-day employee presence in France triggers a service permanent establishment (DE-FR DTA Art.5, >183-day threshold). The engine detects the double-tax conflict, applies the DTA exemption method (Art.23), and flags residual exposure. Zero jurisdiction-specific logic in engine code — all from the rule pack.
- **WHT exposure scanner** — scans all withholding obligations and flags over-withholding vs. treaty entitlement (e.g. applied rate exceeds treaty-reduced rate).
- **Loss carryforward** — MERID-DE FY2024 prior loss offset against FY2025 CIT base using German Mindestbesteuerung rules (full offset up to €1M equivalent, then 60% cap).
- **Ingestion pipeline** — ingests GL/bank CSV/JSON exports, normalises amounts to internal HKD base using FX rates, writes to Neo4j graph.
- **Neo4j knowledge graph** — entity ownership, transactions, counterparties, presence records stored and queried via parameterised Cypher. No f-string query interpolation.
- **4 cited filing briefs** — one per jurisdiction (HK, DE, FR, US), rendered to terminal Markdown. Every figure cites source transaction(s) and the applicable rule (id + as_of_date + statute reference).
- **Cross-border conflict report** — summarises all detected conflicts with treaty resolution notes and residual exposure flags.
- **AI narrative layer** — Claude generates prose narrative for each brief section, grounded by engine-filled numbers. The AI receives no raw financial data; it only wraps pre-computed figures.
- **Offline demo mode** — `make demo` runs on cached AI outputs and never hits the Claude API. Safe for any demo environment with no API key required.
- **279 passing tests**, >80% coverage, enforced by `make test`.

---

## 3. What is mocked, stubbed, or hardcoded

Every shortcut. Disclosed here = no penalty.

| What is faked | Where (file or folder) | Why we mocked it | What the real version would do |
|---|---|---|---|
| Test transaction data for France | `data/golden/transactions.json` | Golden demo scenario — demo data available to show the complication that might arise when the company is present in multiple countries |
 

---

## 4. External APIs, services & data sources

| Service / API / dataset | Used for | Real call or mocked? | Auth |
|---|---|---|---|
| Anthropic Claude API | Brief narrative prose, flow classification, jurisdiction attribution | Real call in live mode; cached JSON responses in demo mode | API key via `ANTHROPIC_API_KEY` env var |
| Neo4j 5 (Docker) | Knowledge graph — entities, transactions, ownership, presence records | Real — local Docker instance | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` env vars |
| ECB / FX rate provider | Live FX rates | Mocked in demo (static `data/golden/fx_rates.json`); `engine/fx_provider.py` exists for live calls | None required for demo |
| HK IRO, German KStG, French CGI, US IRC | Source of all tax rules encoded in rule packs | Mocked as hand-authored JSON files (`data/rules/`) — human-read and transcribed from authoritative public statutes | n/a — public statutes |

---

## 5. Pre-existing code

Anything written before kickoff brought into this project.

| Item | Source | Roughly how much | License |
|---|---|---|---|
| Project harness structure (ROADMAP.md format, CLAUDE.md template, ISSUES/DECISIONS log format) | Adapted from a prior personal hackathon harness (NPCSystem project) by Lohann Colle | ~100 lines of markdown template structure | Personal work, no external licence |

All Python source code in  `graph/`, `seed/`, `src/tributary/` was written during the hackathon window.
All rule pack JSON files in `data/rules/` were authored during the hackathon window.
All test files in `tests/` were written during the hackathon window.

---

## 6. Known limitations & next steps

Naming these honestly is a strength, not a flaw.

- **No statutory form filling** — briefs are advisor-ready cited summaries, not machine-filled BIR51/K1/2042 forms. Explicit out-of-scope decision for the demo.
- **VAT net arithmetic not modelled** — the engine flags VAT registration obligations and filing deadlines; it does not compute input-vs-output VAT netting (requires invoice-level data not in golden fixture).
- **FDII/GILTI require professional input** — US regime elections flagged `needs_review`; engine does not attempt computation.
- **Static rule packs** — rates and thresholds are human-authored from public statutes with `as_of_date` on every rule. Wave 9 (planned) adds RAG extraction from statute PDFs, evaluated against golden hand-computed values before replacing the hand-authored packs.
- **Single-tenant local Neo4j** — demo runs on a local Docker instance; production would require multi-tenant graph partitioning and cloud deployment.
