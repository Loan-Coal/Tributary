"""
Module: runner
Layer: engine
Purpose: EngineRunner orchestrates a full deterministic run for the group: aggregate each
    entity, run the AI seam for review flags, detect PEs and attribute profit across entities,
    compute all obligations, detect the cross-border conflict, and assemble one EngineRunResult
    per entity. All concrete dependencies (graph, AI, rules) are injected as protocols (DIP).
Dependencies: collections, decimal, uuid, tributary.common, tributary.rules, engine.*
Used by: engine.cli (make run-golden), integration tests
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal

from tributary.common.errors import EngineError
from tributary.common.models import (
    AILayerProtocol,
    ConflictFlag,
    EngineRunResult,
    EntityRecord,
    GraphReader,
    GraphWriter,
    JurisdictionCode,
    ObligationType,
)
from tributary.engine.aggregator import EntityBase, aggregate_entity
from tributary.engine.conflict import build_pe_conflict
from tributary.engine.entity_run import EntityArtifacts, build_entity_result
from tributary.engine.flow_context import FlowJudgement, judge_flows
from tributary.engine.pe import PeAttribution, detect_pe
from tributary.engine.periods import compute_period
from tributary.engine.wht_exposure import scan_wht_exposure
from tributary.rules.models import Rule, RuleCategory, RulePackLoader

_BASE_CURRENCY = "HKD"


class EngineRunner:
    """Deterministic engine orchestrator. Inject graph, AI, and rule-pack dependencies."""

    def __init__(
        self,
        reader: GraphReader,
        writer: GraphWriter,
        ai: AILayerProtocol,
        loader: RulePackLoader,
        reference_year: int,
    ) -> None:
        """Wire the runner.

        Args:
            reader: Graph reader.
            writer: Graph writer (results are persisted).
            ai: AI layer (classification + attribution; no figures).
            loader: Rule-pack loader.
            reference_year: Calendar year in which each entity's fiscal year begins.
        """
        self._reader = reader
        self._writer = writer
        self._ai = ai
        self._loader = loader
        self._year = reference_year

    def run(self) -> list[EngineRunResult]:
        """Run the engine for every entity and persist the results.

        Returns:
            One EngineRunResult per entity.
        """
        entities = self._reader.get_all_entities()
        jurisdictions = sorted({e.resident_jurisdiction for e in entities})
        bases, judgements = self._aggregate_all(entities, jurisdictions)
        pe_attrs, pe_adjustment = self._detect_pes(entities, bases, jurisdictions)
        results = self._assemble_results(entities, bases, judgements, pe_adjustment, pe_attrs)
        for result in results:
            self._persist(result)
        return results

    def _aggregate_all(
        self, entities: list[EntityRecord], jurisdictions: list[JurisdictionCode]
    ) -> tuple[dict[str, EntityBase], dict[str, dict[str, FlowJudgement]]]:
        """Phase 1: aggregate each entity's base and run the AI seam."""
        bases: dict[str, EntityBase] = {}
        judgements: dict[str, dict[str, FlowJudgement]] = {}
        for entity in entities:
            period = compute_period(
                self._loader.get_fiscal_calendar(entity.resident_jurisdiction), self._year
            )
            bases[entity.entity_id] = aggregate_entity(
                self._reader, self._loader, entity.entity_id, entity.resident_jurisdiction, period
            )
            txns = self._reader.get_transactions_involving_entity(
                entity.entity_id, period.start_date, period.end_date
            )
            judgements[entity.entity_id] = judge_flows(self._ai, self._reader, txns, jurisdictions)
        return bases, judgements

    def _detect_pes(
        self,
        entities: list[EntityRecord],
        bases: dict[str, EntityBase],
        jurisdictions: list[JurisdictionCode],
    ) -> tuple[list[PeAttribution], dict[str, Decimal]]:
        """Phase 2: detect PEs and build the signed CIT-base adjustment per entity."""
        pe_attrs: list[PeAttribution] = []
        adjustment: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for entity in entities:
            pe = detect_pe(self._reader, self._loader, bases[entity.entity_id], jurisdictions)
            if pe is None:
                continue
            pe_attrs.append(pe)
            adjustment[entity.entity_id] -= pe.attributed_income_hkd  # residence exempts
            pe_entity = self._entity_in_jurisdiction(entities, pe.pe_jurisdiction)
            if pe_entity is not None:
                adjustment[pe_entity.entity_id] += pe.attributed_income_hkd
        return pe_attrs, adjustment

    def _assemble_results(
        self,
        entities: list[EntityRecord],
        bases: dict[str, EntityBase],
        judgements: dict[str, dict[str, FlowJudgement]],
        pe_adjustment: dict[str, Decimal],
        pe_attrs: list[PeAttribution],
    ) -> list[EngineRunResult]:
        """Phase 3+4: build each entity's artifacts and attach PE threshold / conflict."""
        artifacts = {
            e.entity_id: build_entity_result(
                self._reader,
                self._loader,
                bases[e.entity_id],
                pe_adjustment.get(e.entity_id, Decimal("0")),
                judgements[e.entity_id],
            )
            for e in entities
        }
        conflicts_by_entity = self._build_conflicts(entities, pe_attrs, artifacts, bases)
        return [self._to_run_result(artifacts[e.entity_id], conflicts_by_entity.get(e.entity_id, [])) for e in entities]

    def _build_conflicts(
        self,
        entities: list[EntityRecord],
        pe_attrs: list[PeAttribution],
        artifacts: dict[str, EntityArtifacts],
        bases: dict[str, EntityBase],
    ) -> dict[str, list[ConflictFlag]]:
        """Phase 4: build PE conflict flags and WHT exposure flags per entity."""
        conflicts: dict[str, list[ConflictFlag]] = defaultdict(list)
        for pe in pe_attrs:
            artifacts[pe.entity_id].threshold_checks.append(pe.threshold)
            pe_entity = self._entity_in_jurisdiction(entities, pe.pe_jurisdiction)
            conflicts[pe.entity_id].append(
                build_pe_conflict(
                    pe,
                    self._cit_rule(pe.residence_jurisdiction),
                    self._cit_rule(pe.pe_jurisdiction),
                    self._elimination_rule(pe.residence_jurisdiction, pe.pe_jurisdiction),
                    pe_entity.entity_id if pe_entity is not None else pe.entity_id,
                    self._year,
                )
            )
        for entity in entities:
            base = bases[entity.entity_id]
            art = artifacts[entity.entity_id]
            wht_obs = [o for o in art.obligations if o.obligation_type is ObligationType.WHT]
            if wht_obs and base.outbound_payments:
                wht_flags = scan_wht_exposure(
                    wht_obs, base.outbound_payments, self._loader, self._reader, base.period
                )
                conflicts[entity.entity_id].extend(wht_flags)
        return conflicts

    def _to_run_result(self, art: EntityArtifacts, conflicts: list[ConflictFlag]) -> EngineRunResult:
        """Assemble the final EngineRunResult for one entity."""
        unresolved = any(o.needs_review for o in art.obligations) or any(c.needs_review for c in conflicts)
        return EngineRunResult(
            run_id=str(uuid.uuid4()),
            entity_id=art.entity_id,
            fiscal_period=art.period,
            base_currency=_BASE_CURRENCY,
            obligations=art.obligations,
            threshold_checks=art.threshold_checks,
            deadlines=art.deadlines,
            loss_carryforward_applied=art.loss_records,
            conflicts=conflicts,
            has_unresolved_items=unresolved,
        )

    def _persist(self, result: EngineRunResult) -> None:
        """Write obligations and the run summary via the graph writer."""
        for obligation in result.obligations:
            self._writer.write_obligation(result.entity_id, obligation)
        for loss_record in result.loss_carryforward_applied:
            self._writer.update_loss_carryforward(result.entity_id, loss_record)
        self._writer.write_engine_run_summary(result)

    def _entity_in_jurisdiction(
        self, entities: list[EntityRecord], jurisdiction: JurisdictionCode
    ) -> EntityRecord | None:
        """Return the first entity resident in a jurisdiction, if any."""
        for entity in entities:
            if entity.resident_jurisdiction == jurisdiction:
                return entity
        return None

    def _cit_rule(self, jurisdiction: JurisdictionCode) -> Rule:
        """Return the CIT rate rule for a jurisdiction.

        Raises:
            EngineError: When the rule pack contains no CIT rate rule for the jurisdiction.
        """
        rules = self._loader.get_rules(jurisdiction, RuleCategory.CIT_RATE)
        if not rules:
            raise EngineError(f"no CIT rate rule for jurisdiction {jurisdiction}")
        return rules[0]

    def _elimination_rule(self, jur_a: JurisdictionCode, jur_b: JurisdictionCode) -> Rule:
        """Return the treaty elimination rule between two jurisdictions."""
        for rule in self._loader.get_treaty_rules(jur_a, jur_b):
            if rule.category == RuleCategory.TREATY_ELIMINATION:
                return rule
        raise EngineError(f"No treaty elimination rule between {jur_a} and {jur_b}")
