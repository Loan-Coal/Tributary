---
name: audit
description: >
  Full-codebase read-only review of Tributary. Runs a cheap deterministic gate
  (check-layers + ruff + vulture + tests), then fans out one review agent per
  layer to judge code quality, dead code, simplification, architectural
  correctness, and the checkable parts of business correctness (citations,
  no-figures-in-ai, golden matches EXPECTED). Merges findings into a prioritized
  project-harness/REVIEW.md and logs P1/P2 findings into ISSUES.md. Applies NO
  fixes — remediation is handed off to /iterate or refactor-cleaner. Use for a
  periodic whole-repo health check, not for reviewing a single diff (use
  /code-review for that).
---

# /audit — Full-Codebase Read-Only Review

One invocation = one complete audit of the whole repository, start to durable
report, **with zero code mutation**.

**Design contract (why this exists, and why it's shaped the opposite of `/iterate`):**

- **Read-only.** This skill never edits source, never deletes a file, never
  commits. Its only writes are to `project-harness/REVIEW.md` and `ISSUES.md`.
  Fixes are a separate, gated step (Step 6). A review that mutates produces an
  unreviewable diff and can violate the project's TDD/regression rule — so it
  doesn't.
- **Fan-out, not inline.** A 53-file repo cannot be held in one warm context
  without compaction. So the orchestrator (you) dispatches **one review agent per
  layer**; each agent reads its slice and returns **only structured findings** —
  never file contents. This is deliberately the inverse of `/iterate`, which
  stays inline precisely because it touches one bounded unit. Different problem,
  different shape.
- **Mechanical gate first, model judgment second.** Half of "code quality" is
  already numeric law in CLAUDE.md (300 lines/file, 40 lines/function, nesting ≤ 3)
  or enforced by tooling (`check-layers`, `ruff`, `vulture`). Run those first;
  they are deterministic and nearly free. Spend agent tokens only on what tools
  cannot see: naming, cohesion, logic, architectural intent, domain correctness.
- **Honest about the tax boundary.** The skill CANNOT certify that the tax math
  matches statute. Its only oracle is `EXPECTED.md` + the golden test. Where it
  cannot verify, it emits a `needs human tax-expert review` flag — it never
  blesses tax correctness it can't check.
- **Resumable + durable.** Findings stream into `REVIEW.md` as each layer agent
  returns, so a crash or compaction never loses completed work.

---

## Step 0 — Load state (ONCE, bounded)

Read exactly these, then stop reading broadly:

1. `project-harness/ROADMAP.md` — wave checklists + carry-forward. **Load-bearing:**
   the dead-code verdict depends on it (scaffolding planned by a later wave is NOT
   dead). Note which layers/files upcoming waves still wire.
2. `project-harness/ISSUES.md` — open issues + **next ISSUE id**. Don't re-report
   anything already logged; reference the existing id instead.
3. `project-harness/DECISIONS.md` — the architectural decisions a finding must not
   contradict (e.g. DEC-002 AI emits no figures, DEC-006 engine country-agnostic).
4. `data/golden/EXPECTED.md` — the canonical hand-computed figures (the business
   oracle).

CLAUDE.md project rules are already loaded — do not re-read them.

---

## Step 1 — Mechanical gate (deterministic, run before any agent)

Run and capture output:

```bash
make check-layers      # layer-dependency violations
make lint              # ruff: unused imports, simplifiable code, bugbear smells
make deadcode          # vulture: candidate dead code (confidence ≥ 80)
make test              # full suite + coverage; capture the coverage table
```

Plus two scans tools don't cover, over `src/tributary/**.py` (exclude tests):

- **Size limits** — flag any file > 300 non-test lines, any function/method > 40
  lines, any control-flow nesting > 3. These are hard CLAUDE.md limits → P2.
- **Forbidden patterns** — `print(` in non-CLI source (use `common/logging`);
  prompt string literals outside `prompts/`; f-string interpolation into Cypher;
  raw numeric thresholds/rates in `engine/` logic (must come from rule packs).

Record every mechanical hit straight into the REVIEW.md draft (Step 4 schema)
with its severity. **Cross-check every `vulture` hit against ROADMAP**: if an
upcoming wave wires that symbol, downgrade it to a `pending-wiring` note, not a
dead-code finding. Coverage gaps on a layer point the agents at risk areas — pass
them along in Step 2.

If `make` is unavailable, run the underlying commands directly
(`python scripts/check_layers.py`, `ruff check src/ tests/`, `vulture`,
`pytest ... --cov`).

---

## Step 2 — Fan out: one read-only review agent per layer

Dispatch agents **in parallel** (one message, multiple Agent calls). Cover every
non-empty layer. Suggested mapping:

| Agent | subagent_type | Scope |
|---|---|---|
| Engine review | `python-reviewer` | `src/tributary/engine/` |
| AI-layer review | `python-reviewer` | `src/tributary/ai/` |
| Rules + ingestion | `python-reviewer` | `src/tributary/rules/`, `src/tributary/ingestion/` |
| Common + config | `python-reviewer` | `src/tributary/common/`, `src/tributary/config/`, `src/tributary/prompts/` |
| Architecture sweep | `architect` | whole `src/` tree — layer intent, SOLID, OCP-by-new-file, protocol/DIP usage |

Skip empty scaffolds (`api/`, `brief/`, `graph/` if still bare) — note them as
`pending-wiring`, don't review absent code.

**Every agent prompt MUST end with the same contract** (paste verbatim, fill the
scope):

```
You are reviewing ONLY: <scope paths>. READ-ONLY — do not edit, delete, or
suggest running anything. Return ONLY a findings list, never file contents.

For each finding output exactly:
  SEVERITY | LAYER | file:line | category | one-line problem | suggested fix (≤1 line)

SEVERITY = P1 (correctness bug, layer violation, an AI-emitted figure, a missing
rule citation, golden/EXPECTED mismatch) | P2 (CLAUDE.md limit breach, dead code
confirmed unused, real maintainability problem) | P3 (nit, naming, micro-simplify).

category ∈ {quality, dead-code, simplify, architecture, business}.

Tributary-specific checks you MUST apply:
  - engine/ makes NO AI calls; ai/ emits NO figures (amounts/rates/thresholds/
    deadlines); only graph/ touches Neo4j; no prompt strings outside prompts/.
  - every engine ObligationResult carries rule_id + as_of_date + source_citation;
    every obligation traces to source_flow_ids.
  - no jurisdiction-specific if-statements in engine/ (DEC-006); country values
    come from rule packs only.
  - all cross-module data is a Pydantic v2 model — flag any raw dict over a boundary.
  - custom exceptions from common/errors.py — flag bare raise Exception / silent except.
For any tax-math correctness you cannot verify against EXPECTED.md, emit a P2
'business | needs human tax-expert review' finding — do NOT assert it is correct.
Return at most your 25 highest-severity findings; do not pad with nits.
```

As each agent returns, append its findings to the REVIEW.md draft immediately
(resumability). If an agent fails, note it and continue — partial is fine.

---

## Step 3 — Merge, dedupe, prioritize

- Combine mechanical findings (Step 1) + all agent findings.
- **Dedupe:** a vulture dead-code hit and an agent's dead-code note on the same
  symbol are one finding. Mechanical wins on severity ties (it's deterministic).
- **Drop** anything already tracked in ISSUES.md — reference the id instead.
- **Sort** P1 → P2 → P3, then by layer.
- **Sanity-cap:** if a layer produced > 25 findings, keep the top P1/P2 and roll
  the P3 tail into a single "P3 nits (N)" summary line. The report is a decision
  tool, not a dump.

---

## Step 4 — Write `project-harness/REVIEW.md`

Overwrite (it's a point-in-time snapshot; prior runs live in git history). Schema:

```markdown
# Codebase Audit — <YYYY-MM-DD>

**Branch:** <branch> · **Commit:** <short-hash> · **Files reviewed:** <n>
**Mechanical gate:** check-layers <pass/fail> · ruff <n> · vulture <n> · tests <pass/fail>, coverage <pct>

## Summary
<3–5 lines: overall health, the single most important thing to fix, and the
explicit tax-correctness caveat (what was NOT verifiable here).>

## P1 — must fix
| Layer | Location | Category | Problem | Suggested fix |
|---|---|---|---|---|
...

## P2 — should fix
(same columns)

## P3 — nits
(same columns, or a rolled-up count per layer)

## Pending-wiring (NOT dead code)
<symbols vulture/agents flagged that an upcoming wave wires — with the wave id.>

## Needs human review
<business/tax-correctness items the skill cannot certify.>

## Remediation routing
<which findings go to /iterate (need a regression test) vs refactor-cleaner /
/simplify (mechanical), grouped by file so a fix pass is one warm unit.>
```

---

## Step 5 — Log durable findings into `ISSUES.md`

For each **P1 and P2** finding not already tracked, append an entry in the
project's existing format (monotonic id from Step 0; bump the "Next ID to use"
line):

```markdown
## ISSUE-NNN: <short title>
**Found:** <YYYY-MM-DD>, during /audit
**Severity:** P1 | P2
**Where:** <file:line / component>
**Description:** <what is wrong>
**Why deferred:** Surfaced by full-codebase audit; remediation is a separate gated step.
**To fix:** <the suggested fix; route via /iterate if it needs a regression test>
```

P3 nits stay in REVIEW.md only — don't flood the issue log.

---

## Step 6 — Report and hand off (NO fixes here)

```
✓ /audit complete — read-only
  Gate:    check-layers <…> · ruff <n> · vulture <n> · tests <…> cov <pct>
  Findings: P1 <n> · P2 <n> · P3 <n>   (pending-wiring <n>, needs-review <n>)
  Report:  project-harness/REVIEW.md
  Logged:  ISSUE-NNN..ISSUE-MMM appended

Top P1: <one line>
Remediate with:  /iterate --unit <id>   (anything needing a regression test)
                 refactor-cleaner / /simplify  (mechanical cleanup, per flagged file)
```

Then **stop.** Do not fix anything. The audit's job is to find and prioritize;
fixing is a separate, test-gated decision the user drives.

---

## Args

- `/audit` — full repo: mechanical gate + per-layer fan-out + REVIEW.md + ISSUEs.
- `/audit --layer <name>` — audit ONE layer inline (warm, no fan-out). Cheaper;
  writes a scoped section of REVIEW.md, logs its ISSUEs. Use to re-check a layer
  after remediation.
- `/audit --mechanical` — Step 1 only: run the deterministic gate and print
  results. No agents, no report file. Fast pre-commit health pulse.
- `/audit --dry-run` — Steps 0–2 plan only: print the gate results and the agent
  dispatch plan (which agent gets which scope). No agents dispatched, no writes.

---

## Anti-patterns (do not do these)

| Don't | Do |
|---|---|
| Edit/delete/commit during the audit | Read-only; route fixes to /iterate or refactor-cleaner |
| Read all 53 files inline yourself | Fan out; agents return findings, not file dumps |
| Let an agent paste source back | Enforce the "findings only" contract in every prompt |
| Flag scaffolding as dead code | Cross-check vulture/agent hits against ROADMAP first |
| Certify tax math is correct | Verify vs EXPECTED.md only; else "needs human review" |
| Re-file an existing ISSUE | Reference its id; only log genuinely new P1/P2 |
| Dump 200 nits | Cap per layer; roll P3 tail into a count |
| Spend tokens on what ruff/check-layers already catch | Mechanical gate first, model judgment second |
```
