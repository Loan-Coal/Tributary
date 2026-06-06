# Tributary — Engine ↔ Graph Layer Contract

**Version:** 1.0  
**Date:** 2026-06-06  
**Owner:** deterministic engine team  
**Audience:** graph layer implementor (Neo4j team)  

This document is the source of truth for what the engine needs from the graph layer. The graph layer must implement `GraphReader` and `GraphWriter` against this contract. The engine depends only on these protocols — never on Neo4j directly.

> **v1.1 (2026-06-06):** The `GraphReader`/`GraphWriter` Protocol definitions live in
> `tributary/common/protocols_graph.py` (DEC-018 — the engine may not import `graph/`,
> and `graph/` may not import `engine/`, so the shared `common/` layer holds the contract).
> The Neo4j implementations still live in `graph/readers.py` and `graph/writer_engine.py`.
> Two changes from v1.0: (1) **transaction direction convention** (§3) is now explicit and
> (2) a new reader method `get_transactions_involving_entity` (§4) lets each entity see both
> sides of its intercompany flows.

---

## 1. Boundary rules

| Rule | Enforcement |
|------|-------------|
| **No Neo4j queries outside `graph/`.** The engine calls protocol methods only. | Layer check via `make check-layers`. |
| **All returned data is Pydantic v2 models.** No raw `dict`. | Type annotations + validation at boundary. |
| **FX normalization is done at ingestion.** All amounts returned by the graph are already in HKD. The engine never converts currencies. | `amount_hkd` field convention in all return models. |
| **Idempotent reads.** All reader methods must be safe to call multiple times with the same arguments. | Unit tests assert no side effects. |
| **Parameterized Cypher only.** No f-string interpolation into queries. | Code review enforced. |
| **Engine writes obligations via `GraphWriter` only.** The engine never calls Neo4j directly. | Layer check. |

---

## 2. Shared scalar types

```python
from __future__ import annotations
from typing import Annotated
from pydantic import Field

# ISO-3166-1 alpha-2 — shared with AI contract
JurisdictionCode = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
```

---

## 3. Data models returned by the graph

These are defined in `common/models.py`. The graph layer returns them; the engine reads them.

```python
from __future__ import annotations
from datetime import date
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel

class EntityType(str, Enum):
    HOLDCO     = "holdco"
    SUBSIDIARY = "subsidiary"
    BRANCH     = "branch"
    PE         = "pe"           # permanent establishment (created by engine in Phase 6)

class EntityRecord(BaseModel):
    """One legal entity in the group."""
    entity_id: str
    name: str
    entity_type: EntityType
    incorporation_jurisdiction: JurisdictionCode
    resident_jurisdiction: JurisdictionCode       # tax residence — may differ from incorporation
    is_group_member: bool                         # True = eligible for IC elimination

class OwnershipRecord(BaseModel):
    """One ownership edge in the group structure."""
    owner_entity_id: str
    owned_entity_id: str
    ownership_pct: Decimal                        # 0–100
    effective_from: date
    effective_to: date | None                     # None = still current

class TransactionRecord(BaseModel):
    """
    One normalized transaction from the GL/bank export.
    FX normalization to HKD was applied at ingestion — amount_hkd is the authoritative figure.
    activity_type and days_present are populated for PE-relevant records only.

    DIRECTION CONVENTION (DEC-016 — the ingestion normaliser MUST follow this):
      • Intercompany flow:  source_entity_id = PAYER, counterparty_entity_id = PAYEE.
      • Third-party inbound revenue: source_entity_id = the receiving group entity,
        counterparty_entity_id = None.
    The engine derives income vs expense from (which side the entity is on, activity_type).
    Each intercompany flow is stored ONCE; both parties retrieve it via
    get_transactions_involving_entity().
    """
    transaction_id: str
    transaction_date: date
    description: str
    amount_hkd: Decimal           # FX-normalized to HKD at ingestion
    source_amount: Decimal        # original-currency amount before FX (for traceability)
    fx_rate: Decimal              # rate used for normalization
    fx_date: date                 # rate date
    source_currency: str          # ISO-4217 original currency
    source_entity_id: str         # PAYER (IC) or receiving entity (third-party revenue)
    counterparty_entity_id: str | None   # PAYEE (IC) or None (third-party)
    counterparty_jurisdiction: JurisdictionCode | None
    is_intercompany: bool         # True = counterparty is in same ownership group
    activity_type: ActivityType | None   # typed enum (revenue, goods_sale, service_delivery,
                                  #   royalty, dividend, interest, management_fee, loan_principal, other)
    days_present: int | None      # number of employee-days if this record is PE-relevant
    has_agent_authority: bool     # True if agent can bind entity in contracts

class PresenceRecord(BaseModel):
    """
    Employee or agent presence in a jurisdiction.
    Used by PE trigger detection in the engine.
    A single record may span multiple days (cumulative for the period).
    """
    presence_id: str
    entity_id: str                  # the entity whose employees are present
    jurisdiction: JurisdictionCode  # the jurisdiction where they are present
    period_start: date
    period_end: date
    total_days_present: int         # cumulative days in this period
    activity_type: str              # "service_delivery" | "sales" | "management" | "construction"
    has_agent_authority: bool       # any agent in this presence record can bind the entity
    has_fixed_place: bool           # employees operate from a fixed location (office, desk, etc.)

class PriorPeriodLoss(BaseModel):
    """
    A tax loss from a prior fiscal period available for carryforward.
    Populated at ingestion from historical GL data or manually for the golden scenario.
    """
    loss_id: str
    entity_id: str
    jurisdiction: JurisdictionCode
    loss_period_start: date
    loss_period_end: date
    original_loss_hkd: Decimal
    remaining_loss_hkd: Decimal     # updated by engine after each period's computation
    created_at: date

class CounterpartyRecord(BaseModel):
    """A counterparty to a transaction (may or may not be a group entity)."""
    counterparty_id: str
    name: str
    jurisdiction: JurisdictionCode | None
    is_related_party: bool

class FiscalPeriod(BaseModel):
    """A single fiscal period for one jurisdiction. Computed from FiscalCalendar rule."""
    jurisdiction: JurisdictionCode
    start_date: date
    end_date: date
```

---

## 4. GraphReader protocol

The engine depends on this protocol. The Neo4j implementation lives in `graph/readers.py`.

```python
from typing import Protocol

class GraphReader(Protocol):
    """
    Read-only access to the graph for the deterministic engine.
    All methods must be pure reads — no side effects.
    All amounts are already in HKD.
    """

    # ── Entity queries ────────────────────────────────────────────────────────

    def get_entity(self, entity_id: str) -> EntityRecord:
        """
        Fetch one entity by ID.

        Raises:
            EntityNotFoundError: If entity_id does not exist in graph.
        """
        ...

    def get_all_entities(self) -> list[EntityRecord]:
        """
        Return all entities in the graph.
        Used by EngineRunner to enumerate which entities to run the engine on.
        """
        ...

    def get_entity_ownership(self, entity_id: str) -> list[OwnershipRecord]:
        """
        Return all ownership edges where entity_id is the owner.
        Empty list if entity has no subsidiaries.
        """
        ...

    def get_related_party_ids(self, entity_id: str, max_hops: int = 5) -> list[str]:
        """
        Return entity_ids of all entities within max_hops ownership hops of entity_id.
        Used for IC elimination: if counterparty_entity_id is in this list, the flow is intragroup.

        Args:
            entity_id: Starting entity.
            max_hops: Maximum ownership hops to traverse. Default 5 covers typical group structures.
        Returns:
            List of entity_ids (not including entity_id itself).
        """
        ...

    # ── Transaction queries ───────────────────────────────────────────────────

    def get_transactions_for_entity(
        self,
        entity_id: str,
        period_start: date,
        period_end: date,
    ) -> list[TransactionRecord]:
        """
        Return all transactions where source_entity_id == entity_id,
        with transaction_date within [period_start, period_end] inclusive.

        Args:
            entity_id: The entity whose transactions to fetch.
            period_start: First date of the fiscal period (inclusive).
            period_end: Last date of the fiscal period (inclusive).
        Returns:
            All matching TransactionRecords, ordered by transaction_date ascending.
        """
        ...

    def get_transactions_involving_entity(
        self,
        entity_id: str,
        period_start: date,
        period_end: date,
    ) -> list[TransactionRecord]:
        """
        Return all transactions where the entity is on EITHER side of the flow:
        source_entity_id == entity_id OR counterparty_entity_id == entity_id,
        with transaction_date within [period_start, period_end] inclusive.

        This is the method the engine uses to assemble an entity's full books — income
        flows where it is the payee and expense/distribution flows where it is the payer
        (DEC-016). Cypher must match both the [:RECORDS] (source) side and the
        [:WITH]->(Counterparty mapped to entity) / counterparty_entity_id side.

        Returns:
            All matching TransactionRecords, ordered by transaction_date ascending.
        """
        ...

    def get_intercompany_transactions(
        self,
        entity_id: str,
        period_start: date,
        period_end: date,
    ) -> list[TransactionRecord]:
        """
        Return only transactions where is_intercompany == True.
        Used by the aggregator's IC elimination step.
        """
        ...

    def get_transactions_by_activity_type(
        self,
        entity_id: str,
        activity_type: str,
        period_start: date,
        period_end: date,
    ) -> list[TransactionRecord]:
        """
        Return transactions filtered by activity_type within the period.
        Used by tax-type sub-engines to fetch only relevant flows
        (e.g. activity_type="royalty" for WHT computation).
        """
        ...

    # ── Presence / PE queries ─────────────────────────────────────────────────

    def get_presence_records(
        self,
        entity_id: str,
        jurisdiction: JurisdictionCode,
        period_start: date,
        period_end: date,
    ) -> list[PresenceRecord]:
        """
        Return all presence records for entity_id in jurisdiction within the period.
        The engine aggregates total_days_present across records to check PE thresholds.

        Args:
            entity_id: The entity whose employees/agents are present.
            jurisdiction: The jurisdiction where presence occurred.
            period_start: Period start (inclusive).
            period_end: Period end (inclusive).
        Returns:
            All PresenceRecords for this entity + jurisdiction + period.
        """
        ...

    # ── Loss carryforward queries ─────────────────────────────────────────────

    def get_prior_period_losses(
        self,
        entity_id: str,
        jurisdiction: JurisdictionCode,
    ) -> list[PriorPeriodLoss]:
        """
        Return all unabsorbed prior-period losses for entity_id in jurisdiction.
        Ordered by loss_period_start ascending (oldest first — FIFO offset order).

        Args:
            entity_id: The entity whose losses to fetch.
            jurisdiction: The jurisdiction where losses arose.
        Returns:
            List of PriorPeriodLoss with remaining_loss_hkd > 0.
            Empty list if no carryforward losses exist.
        """
        ...

    # ── Counterparty queries ──────────────────────────────────────────────────

    def get_counterparty(self, counterparty_id: str) -> CounterpartyRecord:
        """
        Fetch counterparty details by ID.

        Raises:
            CounterpartyNotFoundError: If counterparty_id does not exist.
        """
        ...
```

---

## 5. GraphWriter protocol

The engine calls this to persist obligation results and update loss positions. Lives in `graph/writer_engine.py`.

```python
class GraphWriter(Protocol):
    """
    Write-only interface for the engine to persist computation results.
    Creates `[:HAS_OBLIGATION]` edges and updates loss carryforward nodes.
    All writes must be idempotent — safe to re-run on the same obligation_id.
    """

    def write_obligation(
        self,
        entity_id: str,
        obligation: ObligationResult,
    ) -> None:
        """
        Persist one computed obligation result.
        Creates or updates an ObligationNode linked to the entity via [:HAS_OBLIGATION].
        Idempotent on obligation.obligation_id.

        Args:
            entity_id: The entity the obligation belongs to.
            obligation: The fully computed ObligationResult from the engine.
        Raises:
            GraphWriteError: On Neo4j write failure.
        """
        ...

    def update_loss_carryforward(
        self,
        entity_id: str,
        loss_record: LossCarryforwardRecord,
    ) -> None:
        """
        Update remaining_loss_hkd on a PriorPeriodLoss node after the engine applied an offset.
        Must be called once per period per jurisdiction where loss was used.
        Idempotent: re-running with the same loss_record.loss_id and period is safe.

        Args:
            entity_id: The entity whose loss position to update.
            loss_record: Contains which loss was used and how much remains.
        Raises:
            GraphWriteError: On Neo4j write failure.
        """
        ...

    def write_engine_run_summary(self, summary: EngineRunResult) -> None:
        """
        Persist a summary node for one engine run.
        Used for audit trail and `make run-golden` output tracing.
        Idempotent on summary.run_id.

        Args:
            summary: The complete EngineRunResult for one entity + period.
        Raises:
            GraphWriteError: On Neo4j write failure.
        """
        ...
```

---

## 6. Error types expected from the graph layer

Define these in `common/errors.py`. The engine catches them and handles gracefully.

```python
class GraphError(TributaryError):
    """Base for all graph layer errors."""

class EntityNotFoundError(GraphError):
    """Raised when get_entity() or get_counterparty() finds no record."""

class CounterpartyNotFoundError(GraphError):
    """Raised when get_counterparty() finds no record."""

class GraphWriteError(GraphError):
    """Raised on Neo4j write failure in GraphWriter."""
```

---

## 7. Cypher implementation guidance

The following are hints for the Neo4j implementation. These are not prescriptive — the implementor owns the Cypher. What is prescriptive is the method signatures and return types above.

### Node labels expected

```
(e:Entity)           — entity_id, name, entity_type, incorporation_jurisdiction, resident_jurisdiction, is_group_member
(a:Account)          — linked to Entity via [:HOLDS]
(t:Transaction)      — transaction_id, transaction_date, description, amount_hkd, fx_rate, fx_date, source_currency, is_intercompany, activity_type, days_present, has_agent_authority
(cp:Counterparty)    — counterparty_id, name, jurisdiction, is_related_party
(p:PresenceRecord)   — presence_id, entity_id, jurisdiction, period_start, period_end, total_days_present, activity_type, has_agent_authority, has_fixed_place
(l:PriorPeriodLoss)  — loss_id, entity_id, jurisdiction, loss_period_start, loss_period_end, original_loss_hkd, remaining_loss_hkd, created_at
(o:ObligationResult) — all ObligationResult fields; written by engine
```

### Relationship types expected

```
(Entity)-[:OWNS {pct: Decimal, effective_from: date, effective_to: date}]->(Entity)
(Entity)-[:HOLDS]->(Account)
(Account)-[:RECORDS]->(Transaction)
(Transaction)-[:WITH]->(Counterparty)
(Entity)-[:RESIDENT_IN]->(Jurisdiction)
(Entity)-[:HAS_OBLIGATION]->(ObligationResult)  -- written by engine
(Entity)-[:HAS_PRESENCE]->(PresenceRecord)
(Entity)-[:HAS_PRIOR_LOSS]->(PriorPeriodLoss)
```

### Example: get_transactions_for_entity (Cypher sketch)

```cypher
MATCH (e:Entity {entity_id: $entity_id})-[:HOLDS]->(a:Account)-[:RECORDS]->(t:Transaction)
WHERE t.transaction_date >= date($period_start)
  AND t.transaction_date <= date($period_end)
RETURN t
ORDER BY t.transaction_date ASC
```

### Example: get_related_party_ids (Cypher sketch — variable-length path)

```cypher
MATCH (root:Entity {entity_id: $entity_id})-[:OWNS*1..5]->(related:Entity)
RETURN DISTINCT related.entity_id AS entity_id
```

### Example: get_presence_records (Cypher sketch)

```cypher
MATCH (e:Entity {entity_id: $entity_id})-[:HAS_PRESENCE]->(p:PresenceRecord)
WHERE p.jurisdiction = $jurisdiction
  AND p.period_start >= date($period_start)
  AND p.period_end   <= date($period_end)
RETURN p
```

---

## 8. Golden scenario — graph structure reference

The engine will be tested against this structure. The graph layer must produce exactly these records when the golden Meridian Group data is ingested.

### Entities

| entity_id | name | type | incorporation | residence |
|-----------|------|------|---------------|-----------|
| MERID-HK | Meridian Holdings Ltd | holdco | HK | HK |
| MERID-DE | Meridian Operations GmbH | subsidiary | DE | DE |
| MERID-FR | Meridian Distribution SAS | subsidiary | FR | FR |

### Ownership

| owner | owned | pct |
|-------|-------|-----|
| MERID-HK | MERID-DE | 100% |
| MERID-DE | MERID-FR | 100% |

### Transactions (summary — see `data/golden/transactions.json` for full records)

| tx_id | from (payer = source_entity_id) | to (payee = counterparty) | type | amount_hkd |
|-------|------|----|------|------------|
| T001 | MERID-DE | MERID-HK | royalty (IC) | 2,400,000 |
| T002 | MERID-DE | MERID-FR | royalty (IC) | 600,000 |
| T004 | MERID-FR | MERID-DE | dividend (IC) | 900,000 |
| T005 | MERID-DE | MERID-HK | dividend (IC) | 1,500,000 |
| T006 | MERID-DE | MERID-HK | interest (IC) | 320,000 |
| T007 | MERID-FR | MERID-HK | management_fee (IC) | 300,000 |
| T008 | (3rd party) | MERID-DE | revenue | 6,200,000 |
| T009 | (3rd party) | MERID-FR | revenue | 2,800,000 |

### Presence records

| entity | jurisdiction | days | activity | agent_authority |
|--------|-------------|------|----------|----------------|
| MERID-DE | FR | 185 | service_delivery | False |

This is the **PE trigger record** — 185 days in France triggers the planted conflict.

### Prior period losses

| entity | jurisdiction | period | original_loss_hkd |
|--------|-------------|--------|-------------------|
| MERID-DE | DE | FY2024 (2024-01-01 to 2024-12-31) | 1,600,000 |
