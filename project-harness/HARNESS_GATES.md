# Harness Quality Gates

The quality rules are executable and enforced, not just prose in `CLAUDE.md`.
Design goal: no lint/type/coverage debt accumulates silently.

## The one command

```bash
make check        # lint + check-layers + type + test-cov (80% floor)
```

Same command runs locally and in CI.

## The gates

| Gate | Make target | What it enforces | Mechanism |
|------|-------------|------------------|-----------|
| Lint | `make lint` | ruff clean on `src/` | hard fail |
| Layers | `make check-layers` | no cross-layer imports (engine→ai, ai→engine, etc.) | hard fail |
| Types | `make type` | mypy on `src/` | hard fail (start clean; keep it clean) |
| Coverage | `make test-cov` | full unit suite, ≥80% | hard fail (`--cov-fail-under=80`) |
| Rules | `make check-rules` | CLAUDE.md strict rules (file-size, `print()`, `except: pass`, `raise Exception`, raw Cypher, AI-typed figures) | hard fail |

## AI-figure guard (critical rule)

`make check-rules` includes a check that no code in `ai/` or `brief/` constructs a
numeric value from scratch (pattern: float/int literals or arithmetic in those modules
that is not reading a field from an engine output model). If the engine is the only
source of numbers, this check is always green.

## Starting clean

Since this project starts from zero, all gates begin at zero debt. The target is to
keep them green from day one — no ratchet mechanism needed.

## Local fast feedback (pre-commit)

```bash
pip install pre-commit
pre-commit install                       # ruff + check-layers + check-rules on commit
pre-commit install --hook-type pre-push  # mypy + test-cov on push
```

## CI (`.github/workflows/ci.yml`)

- Python pinned to match the project stack.
- `static-analysis` job: lint + check-layers + type + check-rules.
- `coverage-gate` job: full suite with 80% floor.

**Mark CI jobs as required for merge in GitHub branch-protection** before the first PR.

## Adding a new rule

Add a check to `scripts/check_rules.py`, run `make check-rules` to confirm it's clean,
and document the rule in the table above.
