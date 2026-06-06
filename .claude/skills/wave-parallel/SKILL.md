---
name: wave-parallel
description: >
  Advance the Tributary build by finding the current in-progress wave, detecting
  which tasks are conflict-free and owned by the engine owner, creating scoped
  brief files, dispatching agents in parallel, and updating the roadmap state.
  Use when you want to make progress on the build without manually picking tasks.
---

# /wave-parallel — Tributary Execution Driver

Reads `project-harness/ROADMAP.md`, identifies the active wave, selects the
largest conflict-free batch of tasks (respecting collaborator ownership),
creates brief files, dispatches coding agents in parallel, and updates
carry-forward notes afterward.

---

## Step 0 — Load project state

Read all of these before doing anything else:

- `project-harness/ROADMAP.md` — wave checklist + carry-forward notes
- `project-harness/DECISIONS.md` — architecture decisions
- `project-harness/API_ENGINE_AI.md` — AI layer contract
- `project-harness/API_ENGINE_GRAPH.md` — graph layer contract
- `project-harness/ISSUES.md` — open issues (avoid duplicating them)

CLAUDE.md rules are already loaded. Do not re-read them.

---

## Step 1 — Identify the active wave

**Active wave** = first wave in ROADMAP.md where at least one task is `[ ]`
AND the previous wave's exit gate is satisfied (announced in carry-forward notes,
session log, or verified by checking that its tasks are all `[x]`).

Wave 1 has no prior gate.

If all waves are complete: report "All waves complete — see expansion roadmap."

If carry-forward notes say a prior wave is blocked on a collaborator handoff,
check Wave N+1 for tasks explicitly independent of that handoff (see conflict map
in Step 4) before giving up.

---

## Step 2 — Collaborator gating

Each wave header has `**Owner:**`. Roles:

| Tag | Who | Policy |
|-----|-----|--------|
| `engine owner` | You (user) | Fully dispatchable |
| `graph colleague` | Collaborator | Do NOT dispatch. Flag as blocked. |
| `AI colleague` | Collaborator | Do NOT dispatch. Flag as blocked. |
| `both` | Mixed | Dispatch only tasks annotated as engine-owner work in the conflict map (Step 4) |

When the active wave is blocked on a collaborator, output:

```
BLOCKED: Wave N — [title] is owned by [collaborator].
Waiting on: [exit gate]

Work you CAN do now: [list any engine-owner tasks from a later wave that are
independent of this handoff, per the conflict map below, or "none identified"]
```

---

## Step 3 — Extract and classify dispatchable tasks

From the active wave, collect all `[ ]` tasks owned by engine owner. For each:

1. Note the task ID (e.g., `W3.4`) and the primary files it creates or edits
   (extractable from the task description — look for backtick file paths).
2. Note any explicit intra-wave dependency (e.g., "W4a.3 depends on W4a.1").

**Conflict rules:**

- Two tasks conflict if they edit the **same file** or if one requires the
  **output** of the other (e.g., a test task needs the module it tests).
- Two tasks creating **different new files** in the same directory do NOT
  conflict (e.g., `hk.json` and `de.json` are separate).
- Test-sweep tasks (typically the last numbered task in a wave) always conflict
  with their implementation tasks — run tests after implementation batch.

---

## Step 4 — Conflict map (pre-computed per wave)

Use this to avoid re-deriving conflicts each session. Update it if the roadmap changes.

### Wave 1 (engine owner — solo)
- **Parallel batch A**: W1.1 (scaffold), W1.2 (models), W1.4 (golden data files — all
  different JSON files so conflict-free within W1.4 subtasks), W1.5 (EXPECTED.md)
- **Sequential after A**: W1.3 (DECISIONS.md update — after W1.2 models stable),
  W1.6 (Neo4j seed — after W1.4 data authored)

### Wave 2 (graph colleague primary — engine owner reviews)
- Engine owner tasks: review W2.4 (`GraphReader` impl) and W2.5 (`GraphWriter` impl)
  against `API_ENGINE_GRAPH.md`. Dispatch a review agent when those PRs are ready.
- Do NOT dispatch W2.1–W2.3 or W2.6 (graph colleague owns them).

### Wave 3 (engine owner — solo)
- **Parallel batch A**: W3.1 (`rules/models.py`), W3.2 (`rules/loader.py`) — no conflict
- **Parallel batch B** (can overlap with A): W3.3 (`hk.json`), W3.4 (`de.json`),
  W3.5 (`fr.json`), W3.6 (`hk_de.json`), W3.7 (`de_fr.json`) — all different files
- **Sequential after A+B**: W3.8 (unit tests — depends on all prior tasks)

### Wave 4a (engine owner — solo)
- **Parallel batch A**: W4a.1 (`ai/protocol.py` + models), W4a.2 (stub JSON) — no conflict
- **Sequential after W4a.1**: W4a.3 (`AttributionStub`), W4a.4 (`aggregator.py`),
  W4a.5 (`runner.py`) — but W4a.3 and W4a.4 do NOT conflict with each other
- **Parallel batch B**: W4a.3 + W4a.4 (after W4a.1 done)
- **Sequential after B**: W4a.5 (runner needs both), W4a.6 (tests — after all)

### Wave 4b (engine owner — solo)
- **Parallel batch A**: W4b.1 (`triggers.py`), W4b.2 (`thresholds.py`),
  W4b.3 (`cit_engine.py`), W4b.4 (`wht_engine.py`), W4b.5 (`vat_engine.py`),
  W4b.6 (`trade_tax_engine.py`), W4b.7 (`deadlines.py`) — all new files, no conflict
- **Sequential after A**: W4b.8 (`loss_ledger.py` — W4b.3 CIT engine calls it;
  write loss ledger first or in the same batch, then update W4b.3 to call it)
  - Practical order: include W4b.8 in batch A; W4b.3 agent stubs the loss_ledger call
    and a follow-up pass wires it once W4b.8 is done.
- **Sequential after all modules**: W4b.9 (unit tests), W4b.10 (integration test)

### Wave 5 (AI colleague primary — engine owner reviews)
- Engine owner tasks: W5.5 (`mock_adapter.py`), W5.6 (swap stub in runner),
  W5.7 (integration test). Dispatchable only after AI colleague delivers W5.1–W5.4.
- Do NOT dispatch W5.1–W5.4 (AI colleague owns them).

### Wave 6 (engine owner — solo)
- **Parallel batch A**: W6.1 (`conflict.py`), W6.5 (`ConflictFlag` model in
  `common/models.py`) — no conflict (different files/layers)
- **Parallel batch B** (can overlap A): W6.2 (PE attribution full compute),
  W6.4 (WHT exposure flag) — both new logic in `engine/` but different functions
- **Sequential after A+B**: W6.3 (double-tax flag — needs W6.1+W6.2),
  W6.6 (treaty pointer lookup — needs W6.3)
- **Sequential last**: W6.7 (unit tests — after all)

### Wave 7 (both — mixed)
- Engine owner tasks: W7.1 (`brief/template.py`), W7.4 (`brief/report.py`),
  W7.6 (`make run-golden` output), W7.7 (integration test)
- AI colleague tasks: W7.2 (`brief/narrator.py`), W7.3 (`brief/assembler.py`),
  W7.5 (`prompts/brief_narrative.yaml`)
- **Parallel batch A (engine owner)**: W7.1, W7.4 — no conflict
- **Sequential after AI colleague delivers W7.2+W7.3**: W7.6, W7.7

### Wave 8 (both — mixed)
- **Parallel batch A**: W8.1 (AI cache snapshot), W8.3 (brief UI), W8.4 (Neo4j view)
- **Sequential after W8.1**: W8.2 (`make demo` offline)
- **Sequential last**: W8.5 (rehearsal + DEMO_SCRIPT.md)

---

## Step 5 — Announce the batch

Before dispatching, always print:

```
Active wave: Wave N — [title]
Dispatching [k] tasks in parallel: W_N.x, W_N.y, W_N.z
  Holding — depends on W_N.a (not yet done): W_N.b
  Holding — collaborator owned: W_N.c
  Holding — conflicts with W_N.x: W_N.d (test sweep — runs after batch)
```

---

## Step 6 — Create brief files

For each task in the batch, check whether
`project-harness/briefs/W[N].[M]-<slug>.md` already exists. If not, create it
before dispatching the agent.

### Brief file format

```markdown
# Brief: W[N].[M] — [task title]

**Wave:** [N] — [wave title]
**Status:** [ ] not started
**Owner:** engine owner
**Depends on:** [prior tasks required, or "none within this wave"]
**Touches:** [primary file(s) or module(s) created or edited]

## Objective

[One paragraph: what this task produces and why it fits into the wave's exit gate.]

## Acceptance criteria

- [ ] [Specific output 1 — e.g., "loader returns correct rules for HK/DE/FR"]
- [ ] [Specific output 2]
- [ ] Every new file has a module docstring (layer, purpose, deps, used-by)
- [ ] Every public function: type annotations + docstring (summary, Args, Returns, Raises)
- [ ] Unit tests: at least one happy-path + one failure test per public function
- [ ] `make test` green after this task

## Context

[Paste the relevant task description from ROADMAP.md verbatim.
Add any applicable DECISIONS.md entry numbers and one-line summaries.]

## Layer and constraints

- **Layer:** [which layer — engine | rules | graph | ai | brief | ingestion | common]
- **Hard limits:** no file > 300 lines; no function > 40 lines; nesting ≤ 3 levels
- **Data boundaries:** all cross-module data = Pydantic v2 BaseModel, no raw dict
- **TDD:** write the failing test before the implementation
- **No AI calls in engine/; no figures in ai/; no Neo4j outside graph/**
```

Mark the brief status `[x] done` when the agent completes.

---

## Step 7 — Dispatch agents in parallel

Spawn one agent per task in the batch. All agents go out in a **single message**
(parallel dispatch). Each agent prompt must be self-contained and include:

1. The full brief file content for that task
2. The relevant DECISIONS.md entries for that layer (quote the decision heading
   and "Decision:" line — don't paste the whole file)
3. The relevant API contract section (from `API_ENGINE_AI.md` or
   `API_ENGINE_GRAPH.md`) if the task touches those interfaces
4. The current carry-forward notes from ROADMAP.md
5. These constraints (copy verbatim into every agent prompt):

```
CONSTRAINTS — non-negotiable:
- TDD: write failing test first, confirm it fails, then implement.
- No file > 300 lines (non-test). Split if needed; add DECISIONS.md entry.
- No function > 40 lines. Extract inner blocks.
- Nesting ≤ 3 levels.
- All cross-module data: Pydantic v2 BaseModel. No raw dict.
- Module docstring on every new file (Module, Layer, Purpose, Dependencies, Used by).
- Public function docstring on every public function.
- Structured logging via common/logging.py. Never print().
- Every engine output: rule_id + as_of_date + source_citation.
- engine/ → NO AI calls. ai/ → NO figures. graph/ → only graph/ does Neo4j.
- Deferred issues → project-harness/ISSUES.md (format: ISSUE-NNN).
- Non-obvious choices → project-harness/DECISIONS.md (format: DEC-NNN).
- When done: update project-harness/briefs/<task-brief>.md Status to [x] done.
```

Use `subagent_type: "claude"` for most tasks. Use `subagent_type: "python-reviewer"`
for code review passes on completed modules.

---

## Step 8 — After agents complete

For each completed task:

1. Tick the checkbox in `project-harness/ROADMAP.md`: `- [ ]` → `- [x]`
2. Update the brief file: `**Status:** [ ] not started` → `**Status:** [x] done`
3. Scan the agent's output for new issues → append to `project-harness/ISSUES.md`
4. Scan for new decisions → append to `project-harness/DECISIONS.md`

Run `make test` (or `make test-engine` for engine-only tasks). If it fails,
do NOT mark the wave exit gate as met. Open an ISSUE and dispatch a
`build-error-resolver` agent before continuing.

---

## Step 9 — Update carry-forward notes

The `## Carry-forward notes` section lives at the top of ROADMAP.md, after the
architecture constraints block and before Wave 1. Maintain it like a rolling log:

- Add a line when a task completes and its output unblocks a later task.
- Add a line for any reusable pattern discovered (link to DECISIONS.md entry).
- Delete lines that have been consumed (the thing they described is now done).
- Keep it under ~15 lines.

Template for a new line:

```
- **Wave N progress**: [W_N.x, W_N.y] done. Next batch: [W_N.z]. Blocked on: [if any].
- **[Pattern]**: [One-line description]. See DEC-NNN.
- **Gate**: `make test` green as of [date]. `make test-engine` green as of [date].
```

---

## Step 10 — Report to user

```
Wave N — [title]
  ✓ Dispatched this run:  W_N.x — [title], W_N.y — [title]
  ✓ Previously complete:  W_N.a, W_N.b
  ◌ Pending next run:     W_N.z (depends on W_N.x finishing)
  ✗ Blocked (collaborator): W_N.c — waiting on graph colleague W2 handoff

Exit gate progress: [N of M tasks complete]
Next /wave-parallel will dispatch: [list]
```

---

## Quality gates (enforced every dispatch)

Every agent must satisfy before marking its task done:

```
Pre-merge checklist
  [ ] All new tests pass
  [ ] All existing tests pass
  [ ] No file > 300 lines of non-test code
  [ ] Every new file has module docstring
  [ ] Every public function: docstring + type annotations
  [ ] No prompt strings outside prompts/
  [ ] No layer violations (engine=no-AI, ai=no-figures, graph=only-graph-does-Neo4j)
  [ ] AI emits no figures
  [ ] Every AI recommendation cites rule (id + as_of_date + source_citation)
  [ ] Deferred work → ISSUES.md
  [ ] Non-obvious choices → DECISIONS.md
```

---

## Args

`/wave-parallel` — picks up from current carry-forward state, dispatches next batch.

`/wave-parallel --wave N` — override: force active wave to Wave N (use when you want
to jump ahead or re-run a specific wave after a collaborator handoff).

`/wave-parallel --review` — skip dispatch; instead run a `python-reviewer` agent
over all files touched in the most recently completed batch.

`/wave-parallel --status` — report wave progress without dispatching anything.
