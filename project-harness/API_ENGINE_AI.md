# Tributary — Engine ↔ AI Layer Contract

**Version:** 1.0  
**Date:** 2026-06-06  
**Owner:** deterministic engine team  
**Audience:** AI layer implementor  

This document is the source of truth for the interface between the AI layer (`src/tributary/ai/`) and the deterministic engine (`src/tributary/engine/`). Both sides must implement against this contract. Changing it requires a `DECISIONS.md` entry and agreement from both sides.

> **v1.1 (2026-06-06):**
> - `AILayerProtocol` is defined in `tributary/common/protocols_ai.py` (DEC-018) and
>   **re-exported from `tributary/ai/protocol.py`** as the published import surface for the
>   AI colleague (`from tributary.ai.protocol import AILayerProtocol, FlowContext, ...`).
> - `FlowContext.activity_type` is now the typed `ActivityType` enum (not `str`).
> - `EngineRunResult.conflicts` is now `list[ConflictFlag]` (typed; see §7) — no longer a
>   `list[dict]` placeholder.

---

## 1. Boundary rules

These are non-negotiable constraints enforced by code review and integration tests.

| Rule | Enforcement |
|------|-------------|
| **AI emits no figures.** No amounts, rates, thresholds, deadlines, or percentages in any AI output field. | Integration test asserts all numeric fields in `EngineRunResult` trace to `ObligationResult` computed by engine, never to AI output. |
| **Every non-abstained output cites at least one rule.** `rule_citations` must be non-empty if `confidence != ABSTAIN`. | Validated in `AILayerProtocol` adapters on receipt. |
| **Jurisdiction codes are ISO-3166-1 alpha-2.** Two uppercase letters. Validated at boundary. | `Annotated[str, Field(pattern=r"^[A-Z]{2}$")]` |
| **No engine computation in `ai/`.** AI classifies and attributes; engine computes. | Layer check via `make check-layers`. |
| **No prompt strings outside `prompts/`.** All text passed to Claude lives in versioned YAML. | Grep check in CI. |
| **Multi-jurisdiction attribution signals conflict.** If `len(FlowAttribution.claims) > 1`, the engine passes the result to conflict detection. The AI does not resolve conflicts — it surfaces them. | Engine runner handles routing. |

---

## 2. Shared enums and scalar types

```python
from __future__ import annotations
from typing import Annotated
from enum import Enum
from pydantic import Field

# ISO-3166-1 alpha-2 country code — validated at boundary
JurisdictionCode = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]

class ConfidenceLevel(str, Enum):
    HIGH    = "HIGH"     # engine proceeds; no review flag
    MEDIUM  = "MEDIUM"   # engine proceeds; brief flags for review
    LOW     = "LOW"      # engine proceeds; item marked needs_review=True
    ABSTAIN = "ABSTAIN"  # AI cannot determine; engine flags as unresolved; abstain_reason required

class FlowNature(str, Enum):
    REVENUE        = "revenue"
    EXPENSE        = "expense"
    INTERCOMPANY   = "intercompany"   # intragroup flow — subject to IC elimination
    CAPITAL        = "capital"        # equity / asset transfer
    LOAN           = "loan"           # principal movement
    ROYALTY        = "royalty"        # IP license payment
    DIVIDEND       = "dividend"       # profit distribution
    INTEREST       = "interest"       # loan interest payment
    MANAGEMENT_FEE = "management_fee" # management / service fee
    OTHER          = "other"          # edge case; must set abstain_reason explaining why

class ObligationType(str, Enum):
    CIT        = "cit"        # Corporate Income Tax
    VAT        = "vat"        # Value Added Tax
    WHT        = "wht"        # Withholding Tax
    TRADE_TAX  = "trade_tax"  # German Gewerbesteuer / local business tax
    STAMP_DUTY = "stamp_duty" # HK Stamp Duty
```

---

## 3. Shared base models

These models are defined in `common/models.py` and imported by both `ai/` and `engine/`.

```python
from __future__ import annotations
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field

class FiscalPeriod(BaseModel):
    """A single fiscal period for one jurisdiction."""
    jurisdiction: JurisdictionCode
    start_date: date
    end_date: date

class RuleCitation(BaseModel):
    """A pointer to a specific rule in a rule pack. Always present in non-abstained AI output."""
    rule_id: str                  # matches Rule.id in the rule pack
    jurisdiction: JurisdictionCode
    as_of_date: date              # the as_of_date on the rule pack entry
    source_citation: str          # e.g. "DE KStG §8b Abs.1", "HK IRO s.14(1)", "DE-FR DTA Art.12"
```

---

## 4. AI input: FlowContext

The engine constructs this and passes it to the AI layer. The AI must not augment it with external data beyond what the graph and rule packs contain.

```python
class FlowContext(BaseModel):
    """
    All information the AI needs to classify and attribute one transaction flow.
    Constructed by EngineRunner from graph data + transaction record.
    """
    flow_id: str                                  # maps to Transaction.transaction_id in graph
    description: str                              # raw narrative from GL export — may be vague
    amount_hkd: Decimal                           # FX-normalised to HKD at ingestion time
    flow_date: date
    source_entity_id: str
    source_jurisdiction: JurisdictionCode | None  # entity's registered jurisdiction; None if unknown
    counterparty_entity_id: str | None
    counterparty_jurisdiction: JurisdictionCode | None
    is_intercompany: bool                         # True if counterparty is in same ownership group
    activity_type: str | None                     # "service_delivery", "goods_sale", "royalty", etc. — from GL
    days_present: int | None                      # non-None for presence/PE-relevant flows
    has_agent_authority: bool                     # True if agent can bind entity in contracts (PE-relevant)
    available_jurisdictions: list[JurisdictionCode]  # jurisdictions with loaded rule packs — AI should only attribute to these
```

---

## 5. AI outputs

### 5.1 FlowClassification

Returned by `classify_flow()`. Must be produced before `attribute_flow()` is called.

```python
class FlowClassification(BaseModel):
    """
    AI determination of what kind of flow this transaction represents.
    The engine uses this to route to the correct tax-type sub-engine.
    """
    flow_id: str
    nature: FlowNature
    confidence: ConfidenceLevel
    rule_citations: list[RuleCitation]  # REQUIRED if confidence != ABSTAIN; explains basis for classification
    abstain_reason: str | None          # REQUIRED if confidence == ABSTAIN; plain English, one sentence max
```

**Constraints:**
- `nature == FlowNature.OTHER` is only valid when `confidence == ABSTAIN`.
- If `confidence == ABSTAIN`, `rule_citations` may be empty, `abstain_reason` must be set.
- If `confidence != ABSTAIN`, `rule_citations` must contain at least one entry.

---

### 5.2 FlowAttribution

Returned by `attribute_flow()`. Called after `classify_flow()` — receives the classification as input.

```python
class JurisdictionClaim(BaseModel):
    """One jurisdiction's claim to tax this flow."""
    jurisdiction: JurisdictionCode
    confidence: ConfidenceLevel
    claim_basis: str              # "source_country" | "residence" | "pe" | "situs" | "treaty" — free text, one word
    rationale_citation: RuleCitation

class FlowAttribution(BaseModel):
    """
    AI determination of which jurisdiction(s) may tax this flow.
    More than one claim means a potential cross-border conflict — the engine will route to conflict detection.
    """
    flow_id: str
    primary_jurisdiction: JurisdictionCode | None  # None only if abstain=True
    claims: list[JurisdictionClaim]                # min 1 if abstain=False; order: highest confidence first
    abstain: bool
    abstain_reason: str | None                     # REQUIRED if abstain=True
```

**Constraints:**
- If `abstain=False`: `primary_jurisdiction` must be set; `claims` must be non-empty; each claim has `confidence != ABSTAIN`.
- If `abstain=True`: `primary_jurisdiction` is None; `claims` may be empty; `abstain_reason` is required.
- `primary_jurisdiction` must appear as the first entry in `claims`.
- If `len(claims) > 1`: the engine will flag this flow for conflict detection. The AI does **not** choose a winner — it surfaces all credible claims.

---

### 5.3 RuleRetrievalResult

Returned by `retrieve_applicable_rules()`. Used by the engine to confirm which rules to apply before computing.

```python
class ApplicableRule(BaseModel):
    """One rule the AI believes is applicable to this flow in this jurisdiction."""
    rule_id: str
    jurisdiction: JurisdictionCode
    rule_type: str        # mirrors Rule.type in rule pack: "rate" | "threshold" | "trigger" | "treaty" | "deadline"
    as_of_date: date
    source_citation: str
    relevance_note: str | None  # optional one-line explanation of why this rule applies

class RuleRetrievalResult(BaseModel):
    """
    AI-retrieved list of applicable rules for a given flow + jurisdiction combination.
    The engine cross-checks these against the rule pack before applying them.
    """
    flow_id: str
    jurisdiction: JurisdictionCode
    applicable_rules: list[ApplicableRule]  # empty only if abstain=True
    abstain: bool
    abstain_reason: str | None
```

---

## 6. The Protocol (what the AI layer must implement)

```python
from typing import Protocol

class AILayerProtocol(Protocol):
    """
    The contract the AI layer must implement.
    The engine depends only on this protocol — never on concrete AI classes.
    The attribution stub (Phase 3) and the real Claude adapter (Phase 4) both implement this.
    """

    def classify_flow(self, context: FlowContext) -> FlowClassification:
        """
        Classify the nature of a transaction flow.

        Args:
            context: All graph + transaction data for one flow.
        Returns:
            Classification with nature, confidence, and rule citations.
        Raises:
            AILayerError: If the underlying model call fails (not for abstention — abstain via ConfidenceLevel.ABSTAIN).
        """
        ...

    def attribute_flow(
        self,
        context: FlowContext,
        classification: FlowClassification,
    ) -> FlowAttribution:
        """
        Attribute jurisdiction(s) that may tax this flow.
        Called after classify_flow() — receives the classification as context.

        Args:
            context: Same FlowContext passed to classify_flow().
            classification: Output from classify_flow() for this flow.
        Returns:
            Attribution with one or more jurisdiction claims.
        Raises:
            AILayerError: On model call failure.
        """
        ...

    def retrieve_applicable_rules(
        self,
        flow_id: str,
        jurisdiction: JurisdictionCode,
        nature: FlowNature,
    ) -> RuleRetrievalResult:
        """
        Retrieve rule IDs the AI believes apply to this flow in this jurisdiction.
        The engine cross-checks against the loaded rule pack.

        Args:
            flow_id: The transaction ID.
            jurisdiction: The attributed jurisdiction.
            nature: The classified flow nature.
        Returns:
            List of applicable rule citations for this jurisdiction.
        Raises:
            AILayerError: On model call failure.
        """
        ...
```

---

## 7. Engine outputs (for AI colleague reference — brief layer consumes these)

The engine produces these. The brief layer and AI narrator receive them. The AI narrator must NOT re-derive or restate numeric fields — it wraps them in prose only.

```python
class ComputationStep(BaseModel):
    """One step in the engine's computation audit trail."""
    step_name: str        # "aggregate_base", "apply_loss_offset", "apply_rate", "apply_treaty_relief"
    input_value_hkd: Decimal
    rule_id: str
    rule_as_of_date: date
    result_value_hkd: Decimal
    note: str | None

class ObligationResult(BaseModel):
    """
    One computed tax obligation. All numeric fields are engine-computed.
    source_flow_ids enables conflict detection by tracing which flows contributed.
    """
    obligation_id: str                  # uuid
    entity_id: str
    jurisdiction: JurisdictionCode
    obligation_type: ObligationType
    fiscal_period: FiscalPeriod
    taxable_base_hkd: Decimal
    rate: Decimal                       # as a fraction, e.g. 0.165 for 16.5%
    gross_amount_hkd: Decimal           # before treaty relief
    treaty_relief_hkd: Decimal          # 0 if no treaty applies
    net_amount_hkd: Decimal             # gross_amount_hkd - treaty_relief_hkd
    rule_id: str
    as_of_date: date
    source_citation: str
    source_flow_ids: list[str]          # which transaction IDs contributed to this obligation
    computation_trace: list[ComputationStep]
    needs_review: bool                  # True if any contributing attribution had LOW confidence

class ThresholdResult(BaseModel):
    """Whether a rule-based threshold was breached (e.g. VAT registration, PE day-count)."""
    entity_id: str
    jurisdiction: JurisdictionCode
    rule_id: str
    threshold_name: str
    threshold_value_hkd: Decimal
    actual_value_hkd: Decimal
    breached: bool
    as_of_date: date
    source_citation: str

class DeadlineResult(BaseModel):
    """Filing and payment deadlines per obligation type and jurisdiction."""
    entity_id: str
    jurisdiction: JurisdictionCode
    obligation_type: ObligationType
    filing_deadline: date
    payment_deadline: date
    rule_id: str
    as_of_date: date
    source_citation: str
    fiscal_period: FiscalPeriod

class LossCarryforwardRecord(BaseModel):
    """Audit trail of how prior-period losses were applied."""
    entity_id: str
    jurisdiction: JurisdictionCode
    loss_period: FiscalPeriod
    original_loss_hkd: Decimal
    used_this_period_hkd: Decimal
    remaining_loss_hkd: Decimal
    limitation_applied: bool           # True if Mindestbesteuerung or equivalent capped the offset
    limitation_rule_id: str | None

class EngineRunResult(BaseModel):
    """
    Full output of one engine run for one entity.
    This is what the brief layer and conflict detector consume.
    Conflicts are added in Wave 6 — field is reserved here.
    """
    run_id: str                             # uuid
    entity_id: str
    fiscal_period: FiscalPeriod
    base_currency: str                      # always "HKD" for this demo
    obligations: list[ObligationResult]
    threshold_checks: list[ThresholdResult]
    deadlines: list[DeadlineResult]
    loss_carryforward_applied: list[LossCarryforwardRecord]
    conflicts: list[dict]                   # typed as ConflictFlag in Wave 6; reserved here
    has_unresolved_items: bool              # True if any obligation has needs_review=True or any abstention
```

---

## 8. Abstention protocol

When the AI cannot determine nature or attribution with reasonable confidence:

1. Set `confidence = ConfidenceLevel.ABSTAIN` (classification) or `abstain = True` (attribution).
2. Set `abstain_reason` to a plain-English one-sentence explanation.
3. The engine sets `ObligationResult.needs_review = True` for all obligations derived from this flow.
4. The brief assembler generates a "lawyer open question" entry for this flow.
5. The engine still runs — abstention does not halt execution.

**Never use abstention to avoid a hard call.** If there is a dominant jurisdiction supported by a rule citation, attribute it (even at LOW confidence) rather than abstaining.

---

## 9. Stub implementation guidance (Phase 3)

The `AttributionStub` class in `engine/attribution_stub.py` implements `AILayerProtocol` by loading `data/golden/attributions_stub.json`.

**Stub JSON format:**

```json
{
  "flows": {
    "T001": {
      "nature": "royalty",
      "confidence": "HIGH",
      "rule_citations": [
        {
          "rule_id": "HK-IRO-S14",
          "jurisdiction": "HK",
          "as_of_date": "2024-01-01",
          "source_citation": "HK Inland Revenue Ordinance s.14(1)"
        }
      ],
      "attribution": {
        "primary_jurisdiction": "DE",
        "claims": [
          {
            "jurisdiction": "DE",
            "confidence": "HIGH",
            "claim_basis": "source_country",
            "rationale_citation": {
              "rule_id": "DE-KStG-WHT-ROYALTY",
              "jurisdiction": "DE",
              "as_of_date": "2024-01-01",
              "source_citation": "DE KStG §49 Abs.1 Nr.6"
            }
          }
        ]
      }
    }
  }
}
```

The stub returns `RuleRetrievalResult` by reading applicable_rules from the same file under a `"rules"` key per flow + jurisdiction pair.

---

## 10. Error types

```python
# In common/errors.py

class AILayerError(TributaryError):
    """Base for all AI layer errors."""

class AIModelCallError(AILayerError):
    """Claude API call failed."""

class AIValidationError(AILayerError):
    """AI output failed Pydantic validation."""

class AIContractViolationError(AILayerError):
    """AI output violated a contract constraint (e.g. non-empty citations on non-abstain)."""
```

All three must be raised — never swallowed. The engine catches `AILayerError` and marks the run as `has_unresolved_items = True` before continuing.
