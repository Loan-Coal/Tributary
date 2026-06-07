# Codebase Audit — 2026-06-06

**Branch:** conflict-detection · **Commit:** c7be298 · **Files reviewed:** ~50
**Mechanical gate:** check-layers PASS · ruff 5 hits · vulture 4 hits · tests PASS (208 passed, 6 skipped), coverage 79%

---

## Summary

The deterministic engine produces correct golden figures and 208 tests are green, but two categories
of structural bugs need remediation before Wave 7 can be safely layered on top.

**Most important fix:** `adapter.py` fabricates a `RuleCitation(rule_id="adapter-placeholder")` for
every jurisdiction attribution — a direct violation of the citation contract (every AI claim must
cite a real rule or emit `needs_review`). This is a P1 business integrity issue that would leak
fake citations into real briefs.

**Second most important:** `rules/db.py` (a SQLite FTS5 module) lives inside the `rules/` layer,
which is restricted to JSON loading only. This is a confirmed cross-layer architecture violation.
The module is also the origin of raw-dict boundary crossings and silent `except: pass` blocks.

**Tax correctness caveat:** This audit cannot verify that computed tax rates, thresholds, or treaty
relief rates match current statutes. EXPECTED.md values were used as the oracle; any engine
divergence from those figures would be a P1. The golden tests pass — EXPECTED.md figures are met.
Items in "Needs human review" require a tax professional, not code.

---

## P1 — must fix

| Layer | Location | Category | Problem | Suggested fix |
|---|---|---|---|---|
| engine | [wht_engine.py:32-35](src/tributary/engine/wht_engine.py#L32) | architecture | `EU_MEMBER_JURISDICTIONS` frozenset of 27 country literals hardcoded in engine/ — DEC-006 violation; adding/removing an EU member requires editing engine code | Move membership set to a reference data file served by config/ or common/; engine reads it, never declares it |
| engine | [wht_engine.py:98](src/tributary/engine/wht_engine.py#L98) | business | `treaty_rate or Decimal("0")` silently applies 0% WHT when `treaty_rate` is `None` — a malformed rule pack produces 0% instead of failing; passes golden tests by coincidence (HK-DE Art.11 is legitimately 0%) | Replace with explicit `if rule.parameters.treaty_rate is None: raise RulePackError(...)` |
| engine | [thresholds.py:40-41](src/tributary/engine/thresholds.py#L40) | business | Zinsschranke EBITDA proxy can be negative (loss-making entity with interest expense) → cap is negative → `interest > cap` is True → false-positive Zinsschranke flag | Clamp `ebitda_proxy = max(ebitda_proxy, Decimal("0"))` before computing cap; needs tax-expert sign-off |
| engine | [conflict.py:56](src/tributary/engine/conflict.py#L56) | quality | `conflict_id = f"PE-TRIANGLE-{year}"` is not unique when multiple entities trigger PE in the same year — ID collision silently overwrites earlier records | Include `entity_id` or `residence_jurisdiction` in the key |
| engine | [runner.py:210](src/tributary/engine/runner.py#L210) | quality | Unguarded `[0]` index on `get_rules()` result — missing CIT rule in a pack raises `IndexError`, not `EngineError`, breaking the entire run | Add `if not rules: raise EngineError(...)` guard before indexing |
| rules | [rules/db.py](src/tributary/rules/db.py) | architecture | `db.py` is a SQLite FTS5 module living inside `rules/` — layer restricted to JSON loading and config/common deps only; database I/O belongs in `graph/` or an `ai/` adapter | Move to `ai/` as a retrieval adapter; wire via the RAGRetriever already in `ai/rag_retriever.py` |
| rules | [rules/db.py:42,69](src/tributary/rules/db.py#L42) | quality | `ingest_rules()` accepts `Iterable[Dict[str, Any]]` and `query_rules()` returns `List[Dict[str, Any]]` — raw dicts crossing module boundary | Change to typed Pydantic models (`Rule` input; `RuleSearchResult` output) |
| rules | [rules/db.py:31,58,80](src/tributary/rules/db.py#L31) | quality | Three `except sqlite3.OperationalError: pass` blocks swallow failures silently (init, ingest, query) — no log, no re-raise | Log at WARNING level before each fallback |
| ai | [ai/protocols.py](src/tributary/ai/protocols.py) | architecture | Defines `GraphReaderProtocol` / `RulePackLoaderProtocol` — a parallel, divergent protocol hierarchy alongside the canonical `common/protocols_ai.py` (DEC-018 violation); two sets of unrelated structural types for the same concerns | Delete `ai/protocols.py`; update `service.py` to import from `tributary.common.protocols_ai` |
| ai | [adapter.py:139-142](src/tributary/ai/adapter.py#L139) | business | `_to_attribution` fabricates `RuleCitation(rule_id="adapter-placeholder", source_citation="Derived from AI output...")` for every jurisdiction claim — fake citation leaks into briefs instead of triggering the `needs_review` abstain path | Emit `abstain=True, needs_human_review=True` with no synthetic citation for attribution claims without a real rule reference |
| ai | [service.py:42](src/tributary/ai/service.py#L42) | quality | `output.transaction_id = transaction_id` mutates a Pydantic v2 model in-place — no `frozen=True` config, so it succeeds silently; masks an LLM returning a mismatched ID | Rebuild via `output.model_copy(update={"transaction_id": transaction_id})` or raise on mismatch |
| ai | [adapter.py:104-113](src/tributary/ai/adapter.py#L104) | quality | `_map_citation(raw: object)` calls `.rule_id`, `.as_of_date`, `.source_citation` with no `isinstance` guard — wrong type in `retrieved_rules` raises bare `AttributeError`, not a domain error | Type `raw` as `ai.models.RuleCitation` or add `isinstance(raw, RuleCitation)` guard |
| common | [common/__init__.py:18-51](src/tributary/common/__init__.py#L18) | quality | `GroupReliefOpportunity` and `GroupReliefMechanism` (added in W6b.1) are missing from the `__init__.py` import block and `__all__` — callers doing `from tributary.common import GroupReliefOpportunity` get `ImportError` | Add both names to the `from .models import (...)` block and to `__all__` |

---

## P2 — should fix

| Layer | Location | Category | Problem | Suggested fix |
|---|---|---|---|---|
| engine | [cit_engine.py:38,90](src/tributary/engine/cit_engine.py#L38) | quality | `compute_cit()` 50 lines, `_build_trace()` 53 lines — over 40-line limit | Extract `_apply_pe_deduction()` and `_apply_loss_offset()` helpers |
| engine | [conflict.py:26](src/tributary/engine/conflict.py#L26) | quality | `build_pe_conflict()` 52 lines — over 40-line limit | Extract `_compute_residence_tax()` and `_resolve_treaty()` |
| engine | [deadlines.py:21](src/tributary/engine/deadlines.py#L21) | quality | `compute_deadline()` 43 lines — over 40-line limit | Extract `_parse_deadline_rule()` helper |
| engine | [entity_run.py:56](src/tributary/engine/entity_run.py#L56) | quality | `build_entity_result()` 52 lines — over 40-line limit | Extract WHT sub-pipeline |
| engine | [pe.py:50](src/tributary/engine/pe.py#L50) | quality | `detect_pe()` 45 lines — over 40-line limit | Extract `_compute_attribution()` |
| engine | [trade_tax_engine.py:25](src/tributary/engine/trade_tax_engine.py#L25) | quality | `compute_trade_tax()` 45 lines — over 40-line limit | Extract `_validate_base()` |
| engine | [wht_engine.py:159](src/tributary/engine/wht_engine.py#L159) | quality | `_build_obligation()` 48 lines — over 40-line limit | Extract `_build_trace()` |
| engine | [wht_exposure.py:34,78](src/tributary/engine/wht_exposure.py#L34) | quality | `scan_wht_exposure()` 42 lines, `_build_flag()` 43 lines — over 40-line limit | Extract per-obligation check into helper |
| engine | [loss_ledger.py:115](src/tributary/engine/loss_ledger.py#L115) | quality | `limitation_rule_id=None` in every `LossCarryforwardRecord` even when `limited=True` — audit trail for capped deductions is silently dropped | Pass `loss_rule.id if limited else None` from the caller |
| engine | [runner.py:114-117](src/tributary/engine/runner.py#L114) | business | PE adjustment applied only to the first entity found in `pe.pe_jurisdiction` — silent data loss if two entities co-reside in the same jurisdiction | Document as known limitation in ISSUES.md or implement multi-entity PE distribution |
| engine | [cit_engine.py:63-64](src/tributary/engine/cit_engine.py#L63) | quality | `from tributary.common.errors import EngineError` deferred import inside conditional branch | Hoist to module-level import |
| engine | [deadlines.py:43-44](src/tributary/engine/deadlines.py#L43) | quality | Same deferred import pattern as cit_engine.py | Hoist to module-level import |
| engine | [entity_run.py:95-96](src/tributary/engine/entity_run.py#L95) | dead-code | `_wht()` accepts `cit_review: bool` parameter but never uses it | Remove the unused parameter |
| ai | [ai/qwen_client.py:14-15](src/tributary/ai/qwen_client.py#L14) | architecture | `import torch` at module top with no ImportError guard — any env without torch will hard-fail on `import tributary.ai` | Wrap in `try/except ImportError` mirroring `ClaudeClient` pattern |
| ai | [client.py:29,43](src/tributary/ai/client.py#L29) | quality | `temperature` stored in `__init__` but never passed to `messages.create()` — constructor parameter silently ignored | Pass `temperature=self.temperature` in `messages.create()` |
| ai | [service.py:26 / adapter.py:197](src/tributary/ai/service.py#L26) | architecture | `llm_client: object` erases the protocol contract — no static guarantee `.generate()` exists | Define `LLMClientProtocol` with `generate(prompt, max_tokens) -> AILayerOutput` and type both fields against it |
| ai | [models.py:15](src/tributary/ai/models.py#L15) | quality | `TransactionContext` uses `extra="allow"` — unvalidated arbitrary fields silently pass to LLM prompt serialization | Use `extra="forbid"` to fail fast at the boundary |
| ai | [rag_retriever.py:4-6](src/tributary/ai/rag_retriever.py#L4) | quality | Missing module docstring in required CLAUDE.md format (Module/Layer/Purpose/Dependencies/Used by) | Add the standard five-field module docstring |
| ai | [rag_retriever.py:19](src/tributary/ai/rag_retriever.py#L19) | quality | `get_rule_summaries(jurisdictions, query_text=None)` signature diverges from `RulePackLoaderProtocol.get_rule_summaries(jurisdictions)` | Align the signature with the protocol |
| ai | [adapter.py:174](src/tributary/ai/adapter.py#L174) | quality | `rule_type="unknown"` magic string — if `ApplicableRule.rule_type` is a `Literal`/`Enum`, this may fail validation | Use a defined constant or the appropriate enum value |
| rules | [rules/loader.py:59,74](src/tributary/rules/loader.py#L59) | quality | Broad `except Exception` in `_load_pack()` and `_load_treaty()` masks unexpected errors | Catch `(ValueError, pydantic.ValidationError)` specifically |
| common | [common/logging.py:4](src/tributary/common/logging.py#L4) | quality | `<<<<<<< HEAD` merge conflict marker embedded in module docstring — malformed but not a SyntaxError | Remove the conflict marker; keep the Purpose line beneath it |
| common | [models_entity.py:222-223](src/tributary/common/models_entity.py#L222) | quality | `FiscalCalendar.period_start_day` validated with `ge=1, le=31` but no cross-field check — `day=31, month=2` passes silently; engine could compute wrong fiscal periods | Add `model_validator(mode='after')` that calls `date(2000, period_start_month, period_start_day)` |
| common | [protocols_graph.py:71,191](src/tributary/common/protocols_graph.py#L71) | dead-code | `max_hops: int = 5` and `counterparty_id` parameters flagged unused by vulture (100%) — verify Wave 2 implementations actually use them | Confirm graph/readers.py (Wave 2) uses both; remove if no implementation plans to honour them |
| common | [errors.py:65](src/tributary/common/errors.py#L65) | architecture | `PromptLoaderError` inherits from `AILayerError` — prompt loading is infrastructure, not an AI model call | Move under `PromptError(TributaryError)` or directly under `TributaryError` |
| config | [settings.py:42](src/tributary/config/settings.py#L42) | quality | `validate()` raises built-in `EnvironmentError` instead of a domain exception | Define `ConfigurationError(TributaryError)` in `common/errors.py` and raise that |
| global | tests/coverage | quality | Test coverage 79% — just under the 80% CLAUDE.md minimum; engine modules not yet covered by group-relief tests (W6b pending) | Add missing unit tests; coverage will recover once W6b.7 completes |

---

## P3 — nits

| Layer | Location | Category | Problem |
|---|---|---|---|
| engine | [conflict.py:6-8](src/tributary/engine/conflict.py#L6) | quality | Module docstring names Germany/France — contradicts DEC-006 country-agnostic framing |
| engine | [runner.py:37](src/tributary/engine/runner.py#L37) | quality | `_BASE_CURRENCY = "HKD"` should be typed as `Literal["HKD"]` |
| engine | [pe.py:65](src/tributary/engine/pe.py#L65) | quality | "the golden scenario has exactly one" inline comment embeds fixture assumptions in general logic |
| engine | [wht_exposure.py:107](src/tributary/engine/wht_exposure.py#L107) | quality | `ConflictFlag.pe_jurisdiction` reused for WHT payee jurisdiction — confusing field repurposing undocumented |
| engine | [loss_ledger.py:79](src/tributary/engine/loss_ledger.py#L79) | simplify | Double-paren generator expression in `sum((...), Decimal("0"))` — style nit |
| ai | [client.py:9](src/tributary/ai/client.py#L9) | quality | Unsorted imports (ruff I001) |
| ai | [fake_client.py:32](src/tributary/ai/fake_client.py#L32) | quality | Trailing whitespace (ruff W291) |
| ai | [models.py:9](src/tributary/ai/models.py#L9) | quality | `typing.List` deprecated (UP035), unused `Any` (F401), unsorted imports (I001) — 3 ruff hits |
| ai | [adapter.py:97-101](src/tributary/ai/adapter.py#L97) | business | `_confidence()` maps all output to HIGH or LOW only — MEDIUM is unreachable |
| ai | [service.py:76-77](src/tributary/ai/service.py#L76) | quality | Numeric fields silently dropped in `_serialize_context` with no debug log |
| ai | [fake_client.py:12](src/tributary/ai/fake_client.py#L12) | quality | `prompt` parameter accepted but never read — should be named `_prompt` |
| rules | [rules/models.py:109-124](src/tributary/rules/models.py#L109) | quality | `raise ValueError` in Pydantic validator — correct for Pydantic but add comment to clarify the intentional use |
| common | [common/__init__.py:54-73](src/tributary/common/__init__.py#L54) | quality | Two separate `from .errors import (...)` blocks — consolidate into one |
| config | [config/__init__.py:6](src/tributary/config/__init__.py#L6) | quality | Package docstring still says `Public surface: (empty)` — settings.py is populated |
| P3 nits (engine) | various | simplify | `aggregator.py` silent transaction skip; `attribution_stub.py` unvalidated stub JSON; `_is_payee` missing `is_intercompany` guard — 3 nits |

---

## Pending-wiring (NOT dead code)

These were flagged by vulture/agents but are planned by an upcoming wave:

| Symbol | File | Wave |
|---|---|---|
| `GroupReliefOpportunity`, `GroupReliefMechanism` | `common/models_engine.py` | W6b.4–W6b.7 (engine module + wiring + tests) |
| `EngineRunResult.group_relief_opportunities` | `common/models_engine.py` | W6b.5 (runner wiring) |
| `GROUP_RELIEF` rule category | `rules/models.py` | W6b.4 (scanner reads it) |
| `GraphReader`, `GraphWriter` protocols | `common/protocols_graph.py` | Wave 2 (graph/readers.py, graph/writer_engine.py) |
| `ai/protocol.py` re-export shim | `ai/protocol.py` | Stays — needed as re-export surface; will be clearer once `ai/protocols.py` is deleted |

---

## Needs human review

These items require a qualified tax professional — the audit cannot certify them:

- **Zinsschranke EBITDA proxy negativity** (ISSUE-012): Clamping to zero before computing the 30% cap appears correct under German law, but the minimum-base rule has nuance; sign off with a DE tax specialist.
- **WHT exposure scanner coverage** (`wht_exposure.py:57-58`): Scanner marks treaty-cited obligations as clean without re-checking whether a more favourable treaty applies; a second treaty could be missed.
- **PE attribution percentage (35%)**: Already ISSUE-006. Arm's-length attribution requires functional analysis.
- **HK royalty source rule (T001)**: Already ISSUE-002.
- **T007 management fee arm's-length**: Already ISSUE-003.

---

## Remediation routing

**Use `/iterate --unit <id>` for anything that needs a regression test first:**

| File(s) | ISSUEs | Why /iterate |
|---|---|---|
| `engine/wht_engine.py` | ISSUE-010, ISSUE-011 | Correctness bugs in the tax computation path — need regression tests |
| `engine/thresholds.py` | ISSUE-012 | False-positive flag — regression test for loss-making entity with interest |
| `engine/conflict.py` | ISSUE-013 | Non-unique conflict ID — regression test for multi-entity PE scenario |
| `engine/runner.py` | ISSUE-014 | IndexError path — test with pack missing CIT rule |
| `ai/adapter.py` | ISSUE-015, ISSUE-016 | Citation contract and mutation bugs — unit tests with mock AI output |

**Use `refactor-cleaner` / `/simplify` for mechanical cleanup (no regression test needed):**

| File(s) | ISSUEs | Type |
|---|---|---|
| `rules/db.py` | ISSUE-009 | Move module to `ai/`; delete from `rules/` |
| `ai/protocols.py` | ISSUE-018 | Delete file; update `service.py` imports |
| `common/__init__.py` | ISSUE-017 | Add 2 missing re-exports |
| `common/logging.py` | ISSUE-020 | Remove conflict marker from docstring |
| Engine functions >40 lines | ISSUE-019 | Extract helper functions (8 functions across 5 files) |
| Ruff hits | P3 | `ruff check --fix src/` |
