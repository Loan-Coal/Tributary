# Issues Log

Persistent issues log. Read at the start of every session. Updated whenever
work is deferred or completed.

Rules:
- Never reuse IDs.
- Never delete entries. Mark as `[FIXED]` instead.
- Severity: P1 (blocking) | P2 (annoying) | P3 (nice-to-fix).
- New issues get the next monotonic ID.
- **Next ID to use: ISSUE-009**

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

## ISSUE-008: ClaudeClient uses legacy completions API — will fail in production

**Found:** 2026-06-06, during Wave 5 AI layer review
**Severity:** P1 (blocking — live Claude path does not work)
**Where:** `src/tributary/ai/client.py:27,37`
**Description:** `ClaudeClient.__init__` sets `model="claude-3.0"` (not a valid model ID) and `generate()` calls `client.completions.create()` — the old text-completion API which is removed from the Anthropic SDK. The correct path is `client.messages.create()` with a `messages=[{"role": "user", "content": prompt}]` structure and a valid model ID (e.g. `claude-haiku-4-5-20251001`).
**Why deferred:** Tests use `FakeClaudeClient` or `QwenLocalClient`; the broken path is never exercised. Demo can run offline with `QwenLocalClient`.
**To fix:** In `client.py` replace `client.completions.create(model=..., prompt=..., max_tokens_to_sample=...)` with `client.messages.create(model=..., messages=[{"role":"user","content":prompt}], max_tokens=...)`. Read model name from `settings.CLAUDE_MODEL` (add the setting). Write a unit test that mocks `Anthropic.messages.create`.

## ISSUE-006: PE attribution percentage (35%) is a demo assumption
**Found:** 2026-06-06, during W1.5 (EXPECTED.md hand-computation)
**Severity:** P2 (annoying)
**Where:** MERID-DE PE attribution; T003; DE-FR DTA Art.7
**Description:** The 35% PE income attribution is stated in DEC-007 as a demo assumption based on functional analysis. Arm's-length attribution of PE profits requires detailed documentation under OECD PE attribution rules (2010 Report).
**Why deferred:** Attribution methodology beyond demo scope.
**To fix:** Perform OECD-compliant PE profit attribution analysis for MERID-DE's France operations. Attribution percentage could range from 10%–50% depending on assets, risks, and functions in France.

---

## Fixed

_(none yet)_
