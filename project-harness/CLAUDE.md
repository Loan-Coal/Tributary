# Tributary — Working Rules

This file is auto-loaded via the root `CLAUDE.md` @-import. These rules are not
suggestions. Violating them is a bug.

---

## Orientation

**What is this:** Tributary is a cross-border tax copilot that produces per-jurisdiction,
fully cited **filing briefs** for a lawyer or tax professional to review. It ingests
multi-country GL/bank exports, stores entities and transactions in a Neo4j graph, runs a
deterministic tax engine, and wraps engine-filled numbers with AI narrative. The AI never
emits figures; all numbers originate in the engine.

**Hackathon deliverable:** End-to-end run on a golden multinational → 3–4 cited briefs +
cross-border conflict report. Statutory form filling is out of scope for the demo.

**Current phase:** Phase 0 — Foundations & golden scenario. See `ROADMAP.md`.

### Stack

| Component | Technology |
|-----------|-----------|
| API / orchestration | FastAPI + Uvicorn |
| Graph store | Neo4j 5 (Docker) |
| Rule packs | Versioned JSON files behind a pluggable loader interface |
| Deterministic engine | Pure Python — no AI calls |
| AI layer | Anthropic Claude (grounded retrieval + brief narrative only) |
| Tests | pytest |

### Key commands

```bash
docker-compose up -d          # start Neo4j + backend
make ingest                   # ingest golden scenario mock files
make test                     # full unit suite
make test-engine              # deterministic engine tests only
make run-golden               # end-to-end run on the golden company
make demo                     # cached demo run (never hits live AI)
```

### Key file locations

| Path | What it is |
|------|-----------|
| `src/tributary/ingestion/` | Ingest & normalize GL/bank exports |
| `src/tributary/graph/` | Neo4j write operations |
| `src/tributary/rules/` | Rule-pack loader + country pack JSON files |
| `src/tributary/engine/` | Deterministic tax engine (triggers, thresholds, rates, deadlines, conflict) |
| `src/tributary/ai/` | Grounded AI layer (classification, attribution, retrieval, brief narrative) |
| `src/tributary/brief/` | Brief assembly (per-jurisdiction briefs + cross-border flag report) |
| `src/tributary/prompts/` | All LLM prompt YAML files — no prompt strings in Python |
| `data/golden/` | Golden multinational mock files + hand-computed expected values |
| `data/rules/` | Country rule pack JSON files (HK, EU, US, SG/UK) |
| `project-harness/ROADMAP.md` | Phase plan |
| `project-harness/ISSUES.md` | Persistent issue log (canonical) |
| `project-harness/DECISIONS.md` | Architecture decisions log (canonical) |

### Jurisdictions (demo set)

| Jurisdiction | Why chosen |
|---|---|
| Hong Kong | Territorial, no VAT, simple — good baseline |
| One EU member (e.g. Germany) | VAT-heavy, worldwide-ish, dense treaty network |
| United States | Worldwide, state-level complexity, no federal VAT |
| Singapore or UK | Second Asia/EMEA hub |

---

## Architecture

### Layer model

Services belong to exactly one layer. Dependencies point downward only.

```
api/           → HTTP routes, request/response models
ingestion/     → source-agnostic ingest; currency normalization with rate-date
graph/         → Neo4j write operations, schema enforcement
rules/         → rule-pack loader interface + country pack readers (no AI, no graph)
engine/        → deterministic tax engine: triggers, thresholds, aggregation, rates,
                  deadlines, conflict detection — NO AI calls anywhere in this layer
ai/            → grounded AI layer: flow classification, jurisdiction attribution,
                  rule retrieval + citation, confidence, abstention, brief narrative
brief/         → brief assembly: engine-filled templates + AI narrative wrappers
prompts/       → versioned YAML prompt files (no strings outside this layer)
config/        → settings, environment
common/        → zero-dep shared utilities, data models, exception hierarchy
```

Allowed dependencies (enforced by `make check-layers`):

- `api` → all layers below
- `brief` → engine, ai, rules, graph, config, common
- `ai` → rules, graph, config, common
- `engine` → rules, graph, config, common
- `ingestion` → graph, config, common
- `rules` → config, common
- `graph` → config, common
- `config/common` → nothing

### Forbidden cross-layer patterns

- **No AI calls in `engine/`.** The engine is purely deterministic.
- **No engine computation in `ai/`.** The AI emits no figures.
- **No Neo4j queries outside `graph/`.** Engine and AI call `graph/` readers.
- **No prompt strings outside `prompts/`.** Anything passed to Claude lives in versioned YAML.
- **The AI never free-types amounts, rates, thresholds, or deadlines.** Those slots are filled
  by the engine before the AI touches the brief template.
- **Every AI recommendation cites a rule** (id + as_of_date + source_citation), or it is
  emitted as a "needs review" flag — never an uncited assertion.

If you need to violate a layer rule, stop and write a `DECISIONS.md` entry proposing the
change. Wait for human approval.

---

## Code style

### Files

- Hard limit: **300 lines of non-test code per file.** Split before merging. If a split
  would be artificial, write a justifying comment at the top and add an entry to `DECISIONS.md`.
- One class or one cohesive set of functions per module.
- Module-level docstring on every module (see `documentation` section below).

### Naming

- `snake_case` for files, modules, functions, variables.
- `PascalCase` for classes.
- `UPPER_SNAKE` for constants.
- No abbreviations except well-known ones (`id`, `db`, `fx`, `vat`, `pe`).
- Test files: `test_<module_name>.py`.

### Type annotations

- Every public function has type annotations on parameters and return value.
- Every public class attribute has a type annotation.
- Use `from __future__ import annotations` at the top of every module.
- Use `TYPE_CHECKING` blocks for import-cycle resolution.

### Imports

- Standard library, then third-party, then first-party. Blank line between groups.
- No wildcard imports.
- No relative imports beyond one level (`from .x import y` is fine; `from ..x import y` is not).

---

## Documentation

### Every Python file requires:

1. **Module docstring** at the top, in this format:

```python
"""
Module: <name>
Layer: <ingestion | graph | rules | engine | ai | brief | api | config | common>
Purpose: One sentence describing what this module does.
Dependencies: Which other modules this imports from.
Used by: Which other modules import from this.
"""
```

2. **Function docstrings** on every public function. Format:

```python
def my_function(arg: str) -> int:
    """One-line summary.

    Args:
        arg: Description.
    Returns:
        Description.
    Raises:
        SomeError: When this happens.
    """
```

3. **Class docstrings** on every class.

### `__init__.py` files

```python
"""
Package: <name>
Layer: <layer>
Purpose: One sentence describing what this package contains.
Public surface: List the names re-exported from this package.
"""
```

---

## Testing

### TDD discipline

For new code:
1. Write the failing test.
2. Confirm it fails for the right reason.
3. Write the minimum code to pass.
4. Refactor with tests green.

Bug fixes:
1. Write a regression test reproducing the bug.
2. Confirm it fails.
3. Fix the bug.
4. Confirm the test passes.

### Test layout

```
tests/
  unit/test_<module>.py
  integration/test_<module>.py
  conftest.py
```

- Unit tests: no I/O, no DB, no network. Mock all infrastructure.
- Integration tests: may use test Neo4j, mock AI. No real external calls.

### Test requirements per module

- Every public function has at least one happy-path test and one failure test.
- All engine functions are tested against the golden scenario's hand-computed values.
- Rule-pack loader has integration tests against real JSON packs.
- AI layer has unit tests with a mock Claude adapter.
- Deterministic functions with >2 input parameters have property tests.

---

## Rule-pack contract (load-bearing interface)

Each rule is a structured record with these required fields:

```
id             — unique within jurisdiction
jurisdiction   — ISO country code
type           — obligation_trigger | threshold | rate | deadline | treaty | source_rule
parameters     — dict of typed values the engine reads
as_of_date     — YYYY-MM-DD; surfaced in every output
source_citation — authoritative public source (statute, treaty article, official guidance)
```

The loader exposes `get_rules(jurisdiction, flow_type)`. Demo packs and future licensed
feeds implement the same interface — production means swapping the source, not the engine.

**The as_of_date is always surfaced in output.** Demo rules being outdated is an honest,
defensible design choice — not a hidden liability.

---

## Golden scenario

`data/golden/` contains the canonical test fixture:

- 3–4 jurisdictions, ~10–15 transactions flows.
- At least one **planted cross-border conflict** (same base claimed by ≥2 jurisdictions).
- Hand-computed expected obligations, thresholds, and deadlines — the engine must match these.
- Served as mock CSV/JSON exports simulating GL/bank data.

The golden scenario is the primary integration test. If the engine output diverges from
the hand-computed values, the engine has a bug.

---

## Project management files — canonical locations

`project-harness/ISSUES.md`, `project-harness/DECISIONS.md`, and `project-harness/ROADMAP.md`
are the only copies of these files. Never create or update root-level copies.

---

## Issues log

Format for new entries:

```markdown
## ISSUE-NNN: <short title>
**Found:** YYYY-MM-DD, during <task>
**Severity:** P1 (blocking) | P2 (annoying) | P3 (nice-to-fix)
**Where:** <file:line or component>
**Description:** What is wrong.
**Why deferred:** Why this is not being fixed now.
**To fix:** What needs to happen to fix it.
```

ID is monotonic across the file. Never reuse IDs. When fixed: change heading to
`## [FIXED] ISSUE-NNN: <title>` and add `**Fixed:** YYYY-MM-DD, in <commit/task>`.

---

## Task discipline

### Single-task focus

When working on task X, do not also do task Y. If Y is noticed, log it in `ISSUES.md`.
Exception: Y is *blocking* X.

### Pre-merge checklist

- [ ] All new tests pass
- [ ] All existing tests still pass
- [ ] No file exceeds 300 lines of non-test code
- [ ] Every new file has a module docstring
- [ ] Every new public function has a docstring
- [ ] No prompt strings introduced outside `prompts/`
- [ ] No layer rule violations
- [ ] AI emits no figures (all numbers come from engine)
- [ ] Every AI recommendation cites a rule (id + as_of_date + source_citation)
- [ ] Any deferred work is in `ISSUES.md`
- [ ] Any non-obvious choice is in `DECISIONS.md`
- [ ] Any new pattern reused twice is in `PATTERNS.md`

---

## Asking before doing

You may proceed without asking on:
- Bug fixes inside a single module
- Adding tests
- Adding documentation
- Adding entries to ISSUES, DECISIONS, PATTERNS

You must stop and ask before:
- Changing a public interface that has callers outside its module
- Adding a new dependency
- Changing the schema of a graph node or edge
- Changing the rule-pack contract fields
- Touching CI configuration
- Deleting a file that is not a temporary file you yourself created
- Violating any layer rule

---

## Coding principles

### SOLID

- **SRP** (strict): every module belongs to exactly one category — data model, reader,
  writer, handler/orchestrator, utility, protocol, adapter, or test. Never mix.
- **OCP** (strict): new rule types, country packs, or AI backends are added by creating a
  new file. Never edit existing engine files to add a variant.
- **DIP** (strict): engine and AI layer import protocols, never concrete classes. All
  concrete dependencies are injected via `__init__`.
- **ISP** (strict): protocols must be small. Split if not all implementors need a method.

### Structure

- **Function length** (strict): no function or method may exceed 40 lines.
- **Nesting** (strict): control-flow nesting must not exceed 3 levels. Extract inner blocks.
- **No magic numbers or strings** (strict): constants are named (`ALL_CAPS`). No raw numeric
  thresholds or rate values in logic code — those come from rule packs.

### Types and models

- **Pydantic v2 for all data** (strict): all data crossing module boundaries must be a
  Pydantic v2 `BaseModel`. No raw `dict` crossing a module boundary.
- **Enums/Literal for fixed sets** (strict): flow types, rule types, confidence levels,
  jurisdiction codes — all use `Literal[...]` or `enum.Enum`.

### Error handling

- **Fail fast at boundaries** (strict): validate all external inputs (file imports, LLM
  responses, Neo4j results, rule-pack files) immediately on receipt.
- **Custom exception hierarchy** (strict): all domain errors are typed exceptions in
  `common/errors.py`. Never `raise Exception("message")`.
- **Never swallow errors** (strict): every `except` block must re-raise, raise a domain
  error, or log-and-re-raise.

### Observability

- **Structured logging** (strict): use `common/logging.py`. Never `print()`.
- **Rule traceability** (strict): every engine output carries the rule id, as_of_date, and
  source_citation that produced it. Every brief item links to source transaction(s).

### Security

- **Input caps at API boundary** (strict): cap all string inputs; never pass unconstrained
  user input to Neo4j, the engine, or Claude.
- **No hardcoded secrets** (strict): API keys, DB credentials via environment variables only.
- **Parameterized Cypher only** (strict): no f-string interpolation into Cypher queries.
