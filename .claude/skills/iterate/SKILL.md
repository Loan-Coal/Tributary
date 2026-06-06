---
name: iterate
description: >
  Advance the Tributary roadmap by exactly ONE right-sized unit of work, executed
  inline (no agent spawning) so context stays warm and never needs compaction.
  Loads project state once, picks the next coherent task slice, does it TDD-style,
  verifies with make test, updates the harness docs, commits, and stops. Use for
  steady solo progress between sessions — the lightweight counterpart to /wave-parallel.
---

# /iterate — Single-Unit Roadmap Driver

One invocation = one unit of work, start to finish, in this conversation.

**Design contract (why this exists):**
- **No compaction within an iteration.** The unit is sized to fit a single context
  window. Load context once, do the work, commit, STOP. Start the next iteration
  in a fresh conversation.
- **Minimize context fetching.** Read a fixed, bounded set of state files at the
  start, then read *only* the files the chosen unit touches. Never broad-sweep.
- **Inline, not dispatched.** Do NOT spawn sub-agents. Spawning re-derives context
  cold and is the expensive path. The whole point is to reuse the warm context you
  already have. (This is the opposite of `/wave-parallel`, which fans out.)

If at any point you sense context is getting large (long file reads, many edits,
debugging spiral), finish the current unit if you can, commit, and tell the user to
re-run `/iterate` fresh. Do not push through into a compaction.

---

## Step 0 — Load state (ONCE, bounded)

Read exactly these, in order, and nothing else yet:

1. `project-harness/ROADMAP.md` — wave checklists + carry-forward notes (source of truth)
2. `project-harness/ISSUES.md` — open issues + next ISSUE id
3. `project-harness/NEXT_SESSION.md` — handoff hints (treat as a HINT, may be stale)

CLAUDE.md project rules are already loaded — do not re-read them.

**Trust order:** ROADMAP checkboxes > actual repo state > NEXT_SESSION. If
NEXT_SESSION disagrees with ROADMAP (e.g. says "no code written" but tasks are
ticked), trust ROADMAP and note the staleness — you'll fix NEXT_SESSION in Step 6.

---

## Step 1 — Find the active wave

**Active wave** = the first wave in ROADMAP.md with at least one unchecked `[ ]`
task whose owner is **engine owner** (or **both**, engine-owner slice), and whose
prior wave's exit gate is met.

Skip waves owned solely by a collaborator (`graph colleague`, `AI colleague`) —
those are not yours to dispatch. If the only open work is collaborator-owned,
report that and stop.

If a wave's checkboxes look out of sync with reality (docs were reverted, or work
was done without ticking), do a 30-second reality check: glob the files the wave's
tasks create and see what already exists. Trust the filesystem.

---

## Step 2 — Select ONE unit and size it

From the active wave's open tasks, pick the next one in roadmap order that is not
blocked by an unfinished sibling. A P1 issue in ISSUES.md that blocks the wave
jumps the queue.

**Sizing rubric — a single unit is AT MOST:**
- 1–3 implementation files created or edited, **and**
- ~250 new non-test lines total, **and**
- their accompanying tests, **and**
- one coherent acceptance criterion you can state in a sentence.

**If the chosen task is bigger than that, slice it:**
- Take only the first cohesive slice (e.g. for "W6b: 7 tasks", take W6b.1 model +
  W6b.3 enum only — the data-shape slice — and leave the engine module for the
  next iteration).
- A natural slice boundary: model/contract first, then the logic that uses it,
  then the wiring, then the integration test — each a separate iteration.

Name the unit precisely: its task id(s), the files it touches, and the one-sentence
acceptance criterion.

---

## Step 3 — Announce, then read only what the unit touches

Print this and proceed (auto mode — don't wait for approval unless the unit forces
a decision only the user can make, e.g. changing a public interface or rule-pack
contract — those require a stop-and-ask per CLAUDE.md):

```
/iterate → Wave N — [wave title]
Unit: [task id(s)] — [one-sentence acceptance criterion]
Touches: [file paths]
Reading: [the files above + 1 sibling for pattern reference]
```

Now read **only**:
- The file(s) the unit edits (if they exist).
- **One** nearby sibling of the same kind as a pattern reference (e.g. if writing
  `engine/wht_exposure.py`, read `engine/conflict.py` once for the module shape).
- The specific DECISIONS.md entries relevant to this unit, if any (you already have
  the file in context from Step 0 — just re-quote the relevant DEC; don't re-read).

Do not read the whole engine, the whole test suite, or unrelated layers.

---

## Step 4 — Execute TDD, inline

Follow CLAUDE.md TDD discipline:

1. Write the failing test first. Run it. Confirm it fails for the right reason.
2. Write the minimum implementation to pass.
3. Run the test. Green.
4. Refactor if needed, tests still green.

Hard constraints (from CLAUDE.md — enforce as you write, not after):
- No file > 300 non-test lines. No function > 40 lines. Nesting ≤ 3.
- All cross-module data is a Pydantic v2 model — no raw dict over a boundary.
- Module docstring (Module/Layer/Purpose/Dependencies/Used by) on every new file.
- Public-function docstrings with Args/Returns/Raises.
- Structured logging via `common/logging.py`; never `print()`.
- Layer rules: `engine/` makes no AI calls; `ai/` emits no figures; only `graph/`
  touches Neo4j; no prompt strings outside `prompts/`.
- Every engine output carries rule_id + as_of_date + source_citation.

---

## Step 5 — Verify

Run the narrowest sufficient gate:
- Engine/rules/common units → `make test-engine` (faster), then `make test` if the
  unit could affect other layers.
- AI / brief / cross-layer units → `make test`.

If red: fix inline. If you can't get green in a couple of focused attempts, STOP —
revert the unit's changes or open an ISSUE describing the blocker, update docs to
reflect the partial state, and report. Do not spiral.

If `make` is unavailable on the platform, run the equivalent `pytest` invocation
the Makefile target wraps.

---

## Step 6 — Update the harness (always, even on partial completion)

1. **ROADMAP.md** — tick the unit's checkbox `[ ]` → `[x]`. If you sliced a larger
   task, leave the parent partially ticked and note the remaining slice in
   carry-forward.
2. **Carry-forward notes** (top of ROADMAP) — add one line for what just got
   unblocked; delete any line now consumed; keep under ~15 lines. Update the
   "Next ISSUE id" / "Next DEC id" counters if you used one.
3. **ISSUES.md** — append any deferred work as `ISSUE-NNN` (use the next id, then
   bump the "Next ID to use" line). Never reuse ids.
4. **DECISIONS.md** — append any non-obvious choice as `DEC-NNN` (Context / Options /
   Decision / Why).
5. **FEATURES.md** — flip the affected capability's status if this unit changed it.
6. **NEXT_SESSION.md** — rewrite the "next task" list so the very next `/iterate`
   knows the new top of queue without re-deriving. Keep it short: branch, what just
   landed, ordered next 2–3 units, and the next ISSUE/DEC ids.

---

## Step 7 — Commit

Single conventional commit for the unit (code + tests + doc updates together):

```
<type>(<scope>): <imperative summary>

<what and why, 1–3 lines>
```

Types: feat, fix, refactor, test, docs, chore. Scope = the layer (ai, engine,
rules, brief, config) or `build`/`docs`. No Claude/AI attribution in the message
(project convention). Commit on the current feature branch; if on `main`, branch
first.

---

## Step 8 — Report and hand off

```
✓ /iterate complete — Wave N
  Unit:        [task id(s)] — [acceptance criterion]  → tests green
  Files:       [created / edited]
  Harness:     ROADMAP ticked · NEXT_SESSION updated · [ISSUE-NNN opened | DEC-NNN added | none]
  Commit:      <hash> <type>(<scope>): <summary>

Next unit queued: [task id — one line]
Context is warm but growing — start the next iteration in a FRESH conversation
with /iterate to avoid compaction.
```

Then stop. Do not roll straight into the next unit unless the user asks — the
fresh-context boundary is the whole point.

---

## Args

- `/iterate` — pick the next unit, execute it end-to-end, commit, stop.
- `/iterate --plan` — Steps 0–3 only: load state, pick and size the next unit,
  print the plan and the files it would touch. No edits, no commit. Use to sanity-
  check the selection before spending context on it.
- `/iterate --unit <task-id>` — override selection; force a specific task/slice
  (still size-checked in Step 2; sliced if too big).
- `/iterate --status` — print active wave, ticked vs open tasks, and the next 3
  queued units. No work.

---

## Anti-patterns (do not do these)

| Don't | Do |
|---|---|
| Spawn agents to "parallelize" the unit | Execute inline — context is already warm |
| Read the whole engine/test suite "for context" | Read only the unit's files + one sibling |
| Take on a whole wave in one invocation | One sized unit, then stop |
| Push through when context balloons | Finish/commit the unit, hand off fresh |
| Trust NEXT_SESSION over ROADMAP | ROADMAP checkboxes + filesystem are truth |
| Skip doc updates "to save time" | Harness update is part of the unit, every time |
| Mark a wave gate met with red tests | Gate requires green `make test` |
