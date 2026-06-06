# Patterns Log

Reusable code and design patterns discovered during development. A pattern is
worth recording when it has been applied at least twice and would be worth
applying again.

Rules:
- Append-only.
- Each pattern has a short name, a "when to use" description, a "why" justification,
  and a minimal example.
- If a pattern is superseded, mark it as `[SUPERSEDED]` and link to the replacement.
  Do not delete.

---

## Anti-Pattern: Common Mistakes to Avoid

| Mistake | Correct Pattern |
|---|---|
| `session.run(f"MATCH ... '{entity_id}'")` | `session.run(CYPHER_CONST, entity_id=entity_id)` — parameterized Cypher only |
| AI code building an amount: `tax_due = rate * base` | Engine computes; AI receives a pre-filled brief template field |
| `rule_result["rate"]` (raw dict) | `rule.parameters.rate` — always parse via Pydantic model before field access |
| `except Exception: pass` | `except SpecificError as e: logger.error(...); raise` |
| Hardcoded rate in engine logic: `if amount > 1000000:` | Read threshold from rule pack: `rule.parameters.threshold` |
| Brief narrative restating the engine's number | Brief narrative wraps it: "The engine determined an obligation of {engine_amount}" |
| Missing `source_citation` on a rule application | Every recommendation links to: rule id + as_of_date + source_citation — or it's a "needs review" flag |
| `print(f"Rule: {rule}")` | `logger.info("rule_applied", rule_id=rule.id, jurisdiction=rule.jurisdiction)` |
| Relative imports beyond one level (`from ..x import y`) | `from tributary.x import y` — one level max |

---

_(patterns are added as development proceeds and patterns emerge)_
