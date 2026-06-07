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

---

## Pattern: Protocol Adapter with Per-Call Cache

**Applied in:** `ai/adapter.py` (`AILayerAdapter`), used twice (two inner adapters + one outer).

**When to use:** When two layers define incompatible protocol shapes for the same underlying resource, and one side may make multiple calls that should hit the backend only once per logical unit of work.

**Why:** The engine calls `classify_flow`, `attribute_flow`, and `retrieve_applicable_rules` as three separate methods on the same flow. The underlying LLM call is expensive; it should fire once. The adapter caches by `flow_id` and maps the single `AILayerOutput` to whichever protocol return type the caller needs.

**Minimal structure:**
```python
class TheirProtocol(Protocol):
    def single_call(self, id: str) -> TheirOutput: ...

class OurProtocol(Protocol):
    def method_a(self, ctx: Ctx) -> A: ...
    def method_b(self, ctx: Ctx) -> B: ...

class Adapter:
    def __init__(self, impl: TheirProtocol) -> None:
        self._impl = impl
        self._cache: dict[str, TheirOutput] = {}

    def _get(self, id: str) -> TheirOutput:
        if id not in self._cache:
            self._cache[id] = self._impl.single_call(id)
        return self._cache[id]

    def method_a(self, ctx: Ctx) -> A:
        return _map_to_a(self._get(ctx.id))

    def method_b(self, ctx: Ctx) -> B:
        return _map_to_b(self._get(ctx.id))
```

---

## Pattern: Protocol Facade for Dependency Inversion

**Applied in:** `common/protocols_ai.py`, `common/protocols_graph.py`; re-exported from each layer's `protocol.py`.

**When to use:** When layer A must depend on an abstraction that layer B implements, but importing from B in A would create a circular dependency or layer violation.

**Why:** Common layer has no upward dependencies — all layers can safely import from it. Defining protocols in `common/` and re-exporting them from each layer's `protocol.py` gives each implementor a single import point without coupling layers to each other.

**Rule:** Protocols live in `common/`. Concrete implementations live in their own layer. Every `__init__` uses constructor injection — no layer creates its own dependencies.

_(patterns are added as development proceeds and patterns emerge)_
