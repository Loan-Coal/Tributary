# Issues Log

Persistent issues log. Read at the start of every session. Updated whenever
work is deferred or completed.

Rules:
- Never reuse IDs.
- Never delete entries. Mark as `[FIXED]` instead.
- Severity: P1 (blocking) | P2 (annoying) | P3 (nice-to-fix).
- New issues get the next monotonic ID.
- **Next ID to use: ISSUE-027**

---

## Open

## ISSUE-001: `make test` fails until W1.2 completes
**Found:** 2026-06-06, during W1.1 scaffold
**Severity:** P2 (annoying)
**Where:** `tests/unit/test_models.py:16`
**Description:** W1.2 created `tests/unit/test_models.py` before finishing `src/tributary/common/models.py`. pytest collection fails with `ModuleNotFoundError: No module named 'tributary.common.models'`. The scaffold package structure is correct; the missing module is W1.2's deliverable.
**Why deferred:** W1.1 must not create `src/tributary/common/` — that directory is owned by W1.2 (parallel task). Creating a stub here would conflict with W1.2's output.
**To fix:** Complete W1.2 (create `src/tributary/common/models.py` and related modules). Once W1.2 merges, `make test` will pass.

## ISSUE-002: HK source-rule determination for T001 royalty income
**Found:** 2026-06-06, during W1.5 (EXPECTED.md hand-computation)
**Severity:** P2 (annoying)
**Where:** MERID-HK Profits Tax; T001; HK IRO Cap.112 s.15(1)(b)
**Description:** T001 royalty (HKD 2,400,000) from MERID-DE is included in MERID-HK taxable income on the conservative assumption it is HK-sourced under IRO s.15(1)(b). Actual sourcing depends on where the IP is used (Germany), which may mean it is not HK-sourced.
**Why deferred:** Sourcing analysis requires factual inquiry beyond demo scope; conservative inclusion is defensible for a brief flagged needs_review.
**To fix:** Obtain counsel opinion on whether royalties paid by a DE entity to HK IP owner for IP used in DE are HK-sourced under IRO s.15(1)(b). If not HK-sourced, exclude T001 from HK taxable income → HK tax drops from HKD 445,500 to HKD 49,500.

## ISSUE-003: HK taxability of T006 interest income
**Found:** 2026-06-06, during W1.5 (EXPECTED.md hand-computation)
**Severity:** P3 (nice-to-fix)
**Where:** MERID-HK Profits Tax; T006; HK IRO Cap.112 s.15(1)(f)
**Description:** T006 interest received (HKD 320,000) from MERID-DE is excluded from MERID-HK taxable income on the assumption MERID-HK is not a money-lending business. If MERID-HK is treated as carrying on a money-lending business, the interest would be taxable.
**Why deferred:** Factual determination of MERID-HK's business character deferred.
**To fix:** Determine whether MERID-HK is a money-lending business under IRO. If yes, include T006 in HK taxable income → HK tax increases by HKD 52,800.

## ISSUE-004: T007 management fee arm's-length verification
**Found:** 2026-06-06, during W1.5 (EXPECTED.md hand-computation)
**Severity:** P2 (annoying)
**Where:** MERID-FR CIT computation; T007; FR transfer pricing rules
**Description:** T007 management fee (HKD 300,000) paid by MERID-FR to MERID-HK is treated as a deductible expense in the FR CIT base on the assumption it is arm's length. No transfer pricing analysis has been performed.
**Why deferred:** TP analysis out of scope for demo.
**To fix:** Perform arm's-length comparability analysis. If not arm's length, FR tax authority may disallow some or all of the HKD 300,000 deduction.

## ISSUE-005: FR VAT arithmetic not computed in v1
**Found:** 2026-06-06, during W1.5 (EXPECTED.md hand-computation)
**Severity:** P3 (nice-to-fix)
**Where:** MERID-FR VAT; T009; CGI Art.293B
**Description:** The VAT filing obligation flag is computed (TRIGGERED, quarterly returns required). Net VAT payable, input VAT recovery rate, and quarterly return amounts are not modeled in v1.
**Why deferred:** VAT arithmetic requires detailed input/output VAT ledger analysis; out of scope for the demo deliverable.
**To fix:** In v2, add VAT sub-engine that computes output VAT on T009 revenue and applies standard 20% rate with input VAT recovery based on cost structure.

## ISSUE-007: Decimal→float precision loss in seed layer
**Found:** 2026-06-06, during W1.6 (Neo4j seed implementation)
**Severity:** P3 (nice-to-fix)
**Where:** `src/tributary/ingestion/seed.py` — `_decimal_to_float()` helper
**Description:** Neo4j does not support Python's `Decimal` type. The seed script converts all `Decimal` fields (e.g. `amount_hkd`, `fx_rate`, `ownership_pct`, `original_loss_hkd`, `remaining_loss_hkd`) to `float` before writing. Float representation can introduce small precision errors for large monetary values (e.g. rounding at the 15th significant digit). For the golden demo scenario the amounts are simple enough that no precision is lost in practice, but this is not guaranteed for arbitrary values.
**Why deferred:** Acceptable for a dev-utility seed. Wave 2 `graph/writer.py` will own the production write path.
**To fix:** In Wave 2 graph layer, store monetary amounts either as Neo4j `integer` cents (multiply by 100 and round) or as `string` with a defined scale, then convert back on read. Alternatively, use Neo4j APOC's BigDecimal support if licensed. Document the precision contract in the graph schema.

## [FIXED] ISSUE-008: ClaudeClient uses legacy completions API — will fail in production

**Found:** 2026-06-06, during Wave 5 AI layer review
**Fixed:** 2026-06-06, fix(ai): migrate ClaudeClient to messages.create() API
**Severity:** P1 (blocking — live Claude path does not work)
**Where:** `src/tributary/ai/client.py:27,37`
**Description:** `ClaudeClient.__init__` set `model="claude-3.0"` (not a valid model ID) and `generate()` called `client.completions.create()` — the old text-completion API removed from the Anthropic SDK.
**Fix applied:** Replaced with `client.messages.create()` + `messages=[{"role":"user","content":prompt}]`. Model defaults to `settings.CLAUDE_MODEL` (`claude-haiku-4-5-20251001`). Added 4 unit tests in `tests/unit/test_claude_client.py`.

## ISSUE-006: PE attribution percentage (35%) is a demo assumption
**Found:** 2026-06-06, during W1.5 (EXPECTED.md hand-computation)
**Severity:** P2 (annoying)
**Where:** MERID-DE PE attribution; T003; DE-FR DTA Art.7
**Description:** The 35% PE income attribution is stated in DEC-007 as a demo assumption based on functional analysis. Arm's-length attribution of PE profits requires detailed documentation under OECD PE attribution rules (2010 Report).
**Why deferred:** Attribution methodology beyond demo scope.
**To fix:** Perform OECD-compliant PE profit attribution analysis for MERID-DE's France operations. Attribution percentage could range from 10%–50% depending on assets, risks, and functions in France.

## ISSUE-009: rules/db.py — SQLite FTS5 module violates rules/ layer boundary
**Found:** 2026-06-06, during /audit
**Severity:** P1 (blocking — architecture violation)
**Where:** `src/tributary/rules/db.py` (entire file)
**Description:** `db.py` is a SQLite FTS5 retrieval module inside the `rules/` layer, which by CLAUDE.md is restricted to JSON file loading with dependencies only on `config/` and `common/`. A SQLite database connection is infrastructure that belongs in `graph/` or an `ai/` retrieval adapter. The file also contains raw-dict cross-boundary inputs/outputs and three silent `except: pass` blocks.
**Why deferred:** Surfaced by full-codebase audit; remediation is a separate gated step.
**To fix:** Move `db.py` into `ai/` as a retrieval adapter (mirrors existing `ai/rag_retriever.py`); remove from `rules/`. Fix raw-dict boundaries to use typed Pydantic models. Replace silent excepts with `logger.warning()` calls. Route via refactor-cleaner (no regression test needed — db.py is only called from rag_retriever.py).

## [FIXED] ISSUE-010: wht_engine.py:98 — treaty_rate None silently applies 0% WHT
**Fixed:** 2026-06-06, W6c.1 — `get_treaty_rate()` now raises `RulePackError` when `treaty_rate is None`
**Found:** 2026-06-06, during /audit
**Severity:** P1 (correctness bug — masked by golden test coincidence)
**Where:** `src/tributary/engine/wht_engine.py:98`
**Description:** `return rule.parameters.treaty_rate or Decimal("0"), rule` — if `treaty_rate` is `None` (malformed rule pack), the engine silently applies 0% WHT instead of failing. The golden test passes by coincidence because the HK-DE DTA Art.11 interest rate legitimately is 0%.
**Why deferred:** Surfaced by full-codebase audit; remediation is a separate gated step.
**To fix:** Replace with `if rule.parameters.treaty_rate is None: raise RulePackError(f"treaty rule {rule.id} missing treaty_rate")`. Add regression test with a rule pack where treaty_rate is None. Route via /iterate.

## [FIXED] ISSUE-011: wht_engine.py:32-35 — EU_MEMBER_JURISDICTIONS violates DEC-006
**Fixed:** 2026-06-06, W6c.2 — moved to `common/jurisdictions.py`; engine imports from there
**Found:** 2026-06-06, during /audit
**Severity:** P1 (architecture — DEC-006 country-agnostic violation)
**Where:** `src/tributary/engine/wht_engine.py:32-35`
**Description:** `EU_MEMBER_JURISDICTIONS` is a hardcoded `frozenset` of 27 country string literals inside the engine. DEC-006 mandates the engine is country-agnostic; all jurisdiction-specific values must come from rule packs. Adding or removing an EU member requires editing engine code.
**Why deferred:** Surfaced by full-codebase audit; remediation is a separate gated step.
**To fix:** Move the membership set to a reference data file in `common/` or `config/` (e.g. `EU_MEMBERS` constant), or add an `eu_member: bool` flag to each country's rule pack parameters and read that in the engine. Route via /iterate (regression test: EU PSD exemption still fires for MERID-FR→MERID-DE T004).

## [FIXED] ISSUE-012: thresholds.py:40-41 — negative EBITDA proxy causes false-positive Zinsschranke
**Fixed:** 2026-06-06, W6c.3 — clamped `ebitda_proxy = max(ebitda_proxy, Decimal("0"))` before cap; 2 regression tests added; 218 tests green
**Found:** 2026-06-06, during /audit
**Severity:** P1 (business correctness — needs tax-expert sign-off)
**Where:** `src/tributary/engine/thresholds.py:40-41`
**Description:** When an entity has net losses but interest expense, the EBITDA proxy can be negative. A negative proxy yields a negative 30%-cap, making `interest > cap` True even for small interest — a false-positive Zinsschranke flag. The golden scenario avoids this (MERID-DE is profitable).
**Why deferred:** Surfaced by full-codebase audit; remediation requires tax-expert confirmation.
**To fix:** Clamp `ebitda_proxy = max(ebitda_proxy, Decimal("0"))` before computing the cap, consistent with the German minimum-base rule. Add regression test for a loss-making entity with interest. Route via /iterate.

## [FIXED] ISSUE-013: conflict.py:56 — PE conflict_id not unique for multi-entity PE
**Fixed:** 2026-06-06, W6c.4 — conflict_id now `f"PE-{pe.entity_id}-{pe.residence_jurisdiction}-{conflict_year}"`; regression test added; 219 tests green
**Found:** 2026-06-06, during /audit
**Severity:** P1 (correctness — data loss for multi-entity scenarios)
**Where:** `src/tributary/engine/conflict.py:56`
**Description:** `conflict_id = f"PE-TRIANGLE-{year}"` is not unique when more than one entity triggers a PE in the same fiscal year. A second PE conflict silently overwrites the first if stored by ID.
**Why deferred:** Surfaced by full-codebase audit; golden scenario has only one PE.
**To fix:** Include `entity_id` and `residence_jurisdiction` in the key: `f"PE-{pe.entity_id}-{residence_jurisdiction}-{year}"`. Add regression test with two simultaneous PE triggers. Route via /iterate.

## [FIXED] ISSUE-014: runner.py:210 — unguarded [0] index on get_rules() raises IndexError
**Fixed:** 2026-06-06, W6c.5 — guarded with `if not rules: raise EngineError(...)`; regression test added; 220 tests green
**Found:** 2026-06-06, during /audit
**Severity:** P1 (correctness — unhandled exception breaks entire run)
**Where:** `src/tributary/engine/runner.py:210`
**Description:** `_cit_rule()` calls `get_rules()` and immediately indexes `[0]` without checking the result length. A rule pack missing a CIT rate rule raises `IndexError`, not `EngineError`, breaking the entire engine run with an unhelpful traceback.
**Why deferred:** Surfaced by full-codebase audit; golden packs are complete.
**To fix:** Add `if not rules: raise EngineError(f"no CIT rate rule for jurisdiction {jurisdiction}")` before the index. Route via /iterate.

## [FIXED] ISSUE-015: adapter.py:139-142 — fake RuleCitation("adapter-placeholder") bypasses citation contract
**Fixed:** 2026-06-07, in W6c.6 (adapter-placeholder removed; rationale_citation made Optional; _first_real_citation() helper; abstain path used when no real citation)
**Found:** 2026-06-06, during /audit
**Severity:** P1 (business — fake citation leaks into briefs)
**Where:** `src/tributary/ai/adapter.py:139-142`
**Description:** `_to_attribution()` constructs `RuleCitation(rule_id="adapter-placeholder", source_citation="Derived from AI output; confirm against rule pack.")` for every jurisdiction claim. CLAUDE.md requires every AI recommendation to cite a real rule id + as_of_date + source_citation, or emit `needs_review=True`. This placeholder citation will appear in real briefs instead of triggering the abstain path.
**Why deferred:** Surfaced by full-codebase audit; remediation is a separate gated step.
**To fix:** For attribution claims without a real rule reference, set `abstain=True, needs_human_review=True` and omit the `rule_citations` list (or pass an empty list). Route via /iterate (unit test: adapter must not produce RuleCitation with rule_id containing "placeholder").

## [FIXED] ISSUE-016: service.py:42 — Pydantic model mutated in-place
**Fixed:** 2026-06-07, in W6c.7 (model_copy(update={...}) with warning log)
**Found:** 2026-06-06, during /audit
**Severity:** P1 (correctness — immutability violation, masks ID mismatch)
**Where:** `src/tributary/ai/service.py:42`
**Description:** `output.transaction_id = transaction_id` directly mutates a Pydantic v2 model after validation. No `frozen=True` config, so it silently succeeds. This masks the case where the LLM returns a mismatched `transaction_id`.
**Why deferred:** Surfaced by full-codebase audit; remediation is a separate gated step.
**To fix:** Either rebuild via `output.model_copy(update={"transaction_id": transaction_id})` and log a warning if IDs diverge, or add `frozen=True` to `AILayerOutput` and enforce the immutable pattern. Route via /iterate.

## [FIXED] ISSUE-017: common/__init__.py — GroupReliefOpportunity and GroupReliefMechanism missing from re-exports
**Fixed:** 2026-06-07, in W6c.8 (added to import block and __all__)
**Found:** 2026-06-06, during /audit
**Severity:** P1 (runtime ImportError for any caller using `from tributary.common import GroupReliefOpportunity`)
**Where:** `src/tributary/common/__init__.py:18-51`
**Description:** `GroupReliefOpportunity` and `GroupReliefMechanism` were added to `models_engine.py` in W6b.1 but not added to the `from .models import (...)` block or `__all__` in `common/__init__.py`. Any caller using the common package surface gets an `ImportError`.
**Why deferred:** W6b.4 (engine module) hasn't been written yet, so no caller currently imports these from common — but the bug will manifest immediately when W6b.4 wires in.
**To fix:** Add `GroupReliefOpportunity` and `GroupReliefMechanism` to the import block and `__all__` in `common/__init__.py`. Also update the package docstring. Route via refactor-cleaner.

## [FIXED] ISSUE-018: ai/protocols.py — duplicate protocol module violates DEC-018
**Fixed:** 2026-06-07, in W6c.12 (ai/protocols.py deleted; protocols moved to common/protocols_ai.py)
**Found:** 2026-06-06, during /audit
**Severity:** P1 (architecture — DEC-018 violation, two divergent protocol hierarchies)
**Where:** `src/tributary/ai/protocols.py`
**Description:** `ai/protocols.py` independently defines `GraphReaderProtocol` and `RulePackLoaderProtocol` using legacy `typing.List` — a parallel, divergent set of structural types alongside the canonical `common/protocols_ai.py` and `common/protocols_graph.py` (DEC-018). `ai/service.py` imports from this file instead of the canonical location. The naming collision with `ai/protocol.py` (a legitimate re-export shim) is a confirmed readability trap.
**Why deferred:** Surfaced by full-codebase audit; remediation is a separate gated step.
**To fix:** Delete `ai/protocols.py`. Update `ai/service.py` to import `GraphReader` and `RulePackLoader` from `tributary.common.protocols_graph` / `tributary.common.protocols_ai`. Route via refactor-cleaner.

## [FIXED] ISSUE-019: Engine — 8 functions exceed the 40-line limit
**Fixed:** 2026-06-07, in W6c.14 (helpers extracted from all 8 over-limit functions)
**Found:** 2026-06-06, during /audit
**Severity:** P2 (CLAUDE.md hard limit breach)
**Where:** `engine/cit_engine.py:38,90`, `engine/conflict.py:26`, `engine/deadlines.py:21`, `engine/entity_run.py:56`, `engine/pe.py:50`, `engine/trade_tax_engine.py:25`, `engine/wht_engine.py:159`, `engine/wht_exposure.py:34,78` — 10 functions total across 6 files
**Description:** All confirmed over 40 lines. The engine was written in a single session and the extraction step was deferred.
**Why deferred:** Functions are correct; extraction is mechanical refactoring.
**To fix:** Extract clearly-named helper functions (e.g. `_apply_pe_deduction`, `_compute_residence_tax`, `_parse_deadline_rule`). Route via /simplify per file.

## [FIXED] ISSUE-020: common/logging.py:4 — unresolved merge conflict marker in module docstring
**Fixed:** 2026-06-07, in W6c.24 (<<<<<<< HEAD line removed from docstring)
**Found:** 2026-06-06, during /audit
**Severity:** P2 (malformed docstring; not a SyntaxError since it is inside a string)
**Where:** `src/tributary/common/logging.py:4`
**Description:** `<<<<<<< HEAD` is embedded in the module docstring. The `=======` and `>>>>>>> branch` markers were removed but the opening marker was not. The file is importable and tests pass, but the docstring is visually broken and signals an incomplete rebase.
**Why deferred:** Surfaced during /audit; no runtime impact confirmed.
**To fix:** Remove the `<<<<<<< HEAD` line from the docstring. Route via refactor-cleaner.

## [FIXED] ISSUE-021: loss_ledger.py:115 — limitation_rule_id always None, audit trail lost
**Fixed:** 2026-06-07, in W6c.15 (rule.id passed to _allocate_fifo when limited=True)
**Found:** 2026-06-06, during /audit
**Severity:** P2 (audit trail gap)
**Where:** `src/tributary/engine/loss_ledger.py:115`
**Description:** `LossCarryforwardRecord.limitation_rule_id` is always `None` even when `limited=True` — the field exists to cite which rule capped the deduction, but the value is never populated. Capped deductions cannot be traced to a rule in the output brief.
**Why deferred:** Surfaced by full-codebase audit; golden scenario uses full loss offset (no cap triggered).
**To fix:** Pass the limiting rule's ID from the caller when `limited=True`. Route via /iterate.

## ISSUE-022: runner.py:114-117 — PE adjustment only applied to first co-resident entity
**Found:** 2026-06-06, during /audit
**Severity:** P2 (silent data loss for multi-entity scenarios)
**Where:** `src/tributary/engine/runner.py:114-117`
**Description:** `_entity_in_jurisdiction()` returns the first matching entity in the PE jurisdiction. If two group entities co-reside in the same jurisdiction, only the first absorbs the PE-attributed income — the second entity's base is silently unaffected.
**Why deferred:** Golden scenario has a single entity per jurisdiction; the bug does not affect current tests.
**To fix:** Document as a known limitation in this entry, or implement multi-entity PE income distribution. Route via /iterate if fixed.

## ISSUE-023: config/settings.py:42 — raises built-in EnvironmentError instead of domain exception
**Found:** 2026-06-06, during /audit
**Severity:** P2 (exception hierarchy violation)
**Where:** `src/tributary/config/settings.py:42`
**Description:** `validate()` raises `EnvironmentError` (alias for `OSError`) rather than a typed domain exception. Callers catching `TributaryError` will miss it.
**Why deferred:** Surfaced by full-codebase audit; remediation is a separate gated step.
**To fix:** Define `ConfigurationError(TributaryError)` in `common/errors.py`; raise that instead. Route via refactor-cleaner.

## ISSUE-024: models_entity.py:222-223 — FiscalCalendar cross-field day/month validation missing
**Found:** 2026-06-06, during /audit
**Severity:** P2 (silent validation gap; engine could compute wrong fiscal periods)
**Where:** `src/tributary/common/models_entity.py:222-223`
**Description:** `period_start_day` is validated `ge=1, le=31` but no cross-field validator checks the day against the month (e.g. `day=31, month=2` passes silently). A badly-configured fiscal calendar could silently produce wrong period boundaries.
**Why deferred:** Surfaced by full-codebase audit; golden scenario uses valid dates.
**To fix:** Add `model_validator(mode='after')` that calls `date(2000, self.period_start_month, self.period_start_day)` and raises `ValueError` on invalid combinations. Route via /iterate.

## ISSUE-025: Test coverage 79% — below the 80% CLAUDE.md minimum
**Found:** 2026-06-06, during /audit
**Severity:** P2 (CLAUDE.md coverage minimum breached)
**Where:** Full test suite — `pytest --cov` reports 79%
**Description:** Coverage sits at 79%, one point below the 80% minimum. The gap is partly structural (W6b.7 tests not yet written for group_relief.py which doesn't exist yet) and partly missing negative-path tests in the engine.
**Why deferred:** W6b.7 (group_relief tests) will add coverage. Some gap may already exist in wht_exposure.py negative paths.
**To fix:** Write missing negative-path tests for engine modules (esp. thresholds, wht_engine error paths). Coverage will recover automatically when W6b.7 completes.

## ISSUE-026: ai/qwen_client.py — unguarded torch import hard-fails in envs without torch
**Found:** 2026-06-06, during /audit
**Severity:** P2 (import-time failure for non-GPU environments)
**Where:** `src/tributary/ai/qwen_client.py:15`
**Description:** `import torch` at module top with no `try/except ImportError` guard. Any environment without torch (e.g. CI, the demo machine) will fail on `import tributary.ai` even though `qwen_client.py` is not the active backend. Also has two confirmed-unused imports: `Optional` (vulture 90%) and `torch` itself is never called directly.
**Why deferred:** Surfaced by full-codebase audit; `qwen_client.py` is not wired in production path.
**To fix:** Wrap `import torch` and `from transformers import ...` in `try/except ImportError: ...`. Remove unused `Optional` import. Route via refactor-cleaner.

---

## Fixed

_(none yet)_
