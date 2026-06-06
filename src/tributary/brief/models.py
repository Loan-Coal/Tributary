"""
Module: models
Layer: brief
Purpose: Pydantic data models for per-jurisdiction filing briefs and the cross-border
    conflict report. All numeric fields are engine-sourced; the brief layer never computes.
Dependencies: pydantic, datetime, tributary.common
Used by: brief.template, brief.assembler, brief.renderer
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from tributary.common.models_engine import (
    ConflictFlag,
    DeadlineResult,
    GroupReliefOpportunity,
    LossCarryforwardRecord,
    ObligationResult,
    ThresholdResult,
)
from tributary.common.models_entity import FiscalPeriod, JurisdictionCode, ObligationType


class BriefSection(BaseModel):
    """One tax-type section within a filing brief.

    Groups all engine outputs for a single obligation type: the computed obligation
    (if any), threshold checks, filing deadlines, and loss records. ``narrative``
    is None when AI prose is unavailable; the section still renders from engine data.
    """

    section_id: str
    title: str
    obligation_type: ObligationType
    obligation: ObligationResult | None
    thresholds: list[ThresholdResult]
    deadlines: list[DeadlineResult]
    loss_records: list[LossCarryforwardRecord]
    narrative: str | None
    needs_review: bool


class ConflictExplanation(BaseModel):
    """One cross-border conflict enriched with a formatted treaty pointer.

    ``treaty_pointer`` is formatted from the conflict's treaty citation
    (e.g. "DE-FR DTA Art.23 — exemption method"). ``narrative`` is None when
    AI prose is unavailable. ``recommended_action`` is always None when AI is
    unavailable — never synthesised without grounded retrieval.
    """

    conflict: ConflictFlag
    narrative: str | None
    treaty_pointer: str
    recommended_action: str | None


class FilingBrief(BaseModel):
    """Per-entity filing brief combining engine-computed obligations and optional AI prose.

    All numeric values in ``sections`` originate in the deterministic engine.
    ``as_of_dates`` maps rule_id to the ISO date string from which the rule was current,
    collected across all obligations and thresholds in this brief.
    ``open_questions`` lists section titles or threshold descriptions requiring review.
    """

    brief_id: str
    entity_id: str
    entity_name: str
    jurisdiction: JurisdictionCode
    fiscal_period: FiscalPeriod
    generated_at: datetime
    sections: list[BriefSection]
    conflicts: list[ConflictExplanation]
    group_relief_opportunities: list[GroupReliefOpportunity]
    open_questions: list[str]
    as_of_dates: dict[str, str]
    needs_review: bool


class CrossBorderReport(BaseModel):
    """Multi-entity conflict report for the full group.

    Aggregates all unique ConflictExplanation objects across the group's briefs,
    de-duplicated by conflict_id. ``pe_triangle_narrative`` is None when AI is unavailable.
    """

    report_id: str
    generated_at: datetime
    entity_ids: list[str]
    conflicts: list[ConflictExplanation]
    pe_triangle_narrative: str | None
    group_relief_opportunities: list[GroupReliefOpportunity]
