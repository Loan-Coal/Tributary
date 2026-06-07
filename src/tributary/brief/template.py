"""
Module: template
Layer: brief
Purpose: Builds FilingBrief and CrossBorderReport skeletons from engine output. Pure data
    transformation — no AI calls, no I/O. All numeric slots are engine-sourced.
    Narrative fields are initialised to None; the assembler fills them later.
Dependencies: datetime, uuid, tributary.common, tributary.brief.models
Used by: brief.assembler
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from tributary.common.models_engine import (
    ConflictFlag,
    DeadlineResult,
    EngineRunResult,
    LossCarryforwardRecord,
    ObligationResult,
    ReliefMechanism,
    ThresholdResult,
)
from tributary.common.models_entity import EntityRecord, ObligationType
from .models import (
    BriefSection,
    ConflictExplanation,
    CrossBorderReport,
    FilingBrief,
)

_OBLIGATION_TITLES: dict[ObligationType, str] = {
    ObligationType.CIT: "Corporate Income Tax",
    ObligationType.TRADE_TAX: "Trade Tax (Gewerbesteuer)",
    ObligationType.WHT: "Withholding Tax",
    ObligationType.VAT: "Value Added Tax",
    ObligationType.STAMP_DUTY: "Stamp Duty",
}


def _section_title(obligation_type: ObligationType, jurisdiction: str) -> str:
    """Format a section title from obligation type and jurisdiction.

    Args:
        obligation_type: The type of obligation.
        jurisdiction: Two-letter jurisdiction code.
    Returns:
        Human-readable section title.
    """
    base = _OBLIGATION_TITLES.get(obligation_type, obligation_type.value.upper())
    return f"{base} — {jurisdiction}"


def _treaty_pointer(conflict: ConflictFlag) -> str:
    """Format a human-readable treaty pointer from a ConflictFlag.

    Args:
        conflict: The detected cross-border conflict.
    Returns:
        Treaty pointer string, e.g. "DE-FR DTA — exemption method".
    """
    mechanism = (
        "exemption method"
        if conflict.relief_mechanism == ReliefMechanism.EXEMPTION
        else "credit method"
    )
    return f"{conflict.treaty_source_citation} — {mechanism}"


def _collect_as_of_dates(result: EngineRunResult) -> dict[str, str]:
    """Collect rule_id → as_of_date strings from all obligations and thresholds.

    Args:
        result: Engine run result for one entity.
    Returns:
        Dict mapping rule_id to ISO date string.
    """
    dates: dict[str, str] = {}
    for obligation in result.obligations:
        dates[obligation.rule_id] = obligation.as_of_date.isoformat()
    for threshold in result.threshold_checks:
        dates[threshold.rule_id] = threshold.as_of_date.isoformat()
    for deadline in result.deadlines:
        dates[deadline.rule_id] = deadline.as_of_date.isoformat()
    return dates


def _open_questions(sections: list[BriefSection], result: EngineRunResult) -> list[str]:
    """Derive open questions from needs_review flags and threshold breaches.

    Args:
        sections: Brief sections already assembled.
        result: Engine run result for context.
    Returns:
        List of plain-English open question strings.
    """
    questions: list[str] = []
    for section in sections:
        if section.needs_review:
            questions.append(f"Review required: {section.title}")
        if (
            section.obligation is not None
            and section.obligation_type == ObligationType.WHT
            and section.obligation.is_intercompany
        ):
            flow_ids = ", ".join(section.obligation.source_flow_ids)
            questions.append(
                f"Transfer pricing: arm's-length basis for intercompany payment "
                f"({flow_ids}) has not been benchmarked — OECD Art.9 documentation required."
            )
    for threshold in result.threshold_checks:
        if threshold.breached:
            if getattr(threshold, "unit", "HKD") == "days":
                questions.append(
                    f"Threshold breached: {threshold.threshold_name} "
                    f"(actual {threshold.actual_value_hkd:,.0f} vs "
                    f"limit {threshold.threshold_value_hkd:,.0f} days)"
                )
            else:
                # Monetary detail is already in the section body (local currency);
                # omit amounts here to avoid the HKD-vs-local mismatch.
                questions.append(f"Threshold breached: {threshold.threshold_name}")
    return questions


def _build_section(
    obligation_type: ObligationType,
    obligations: list[ObligationResult],
    thresholds: list[ThresholdResult],
    deadlines: list[DeadlineResult],
    loss_records: list[LossCarryforwardRecord],
    jurisdiction: str,
) -> BriefSection:
    """Build one BriefSection for an obligation type.

    Args:
        obligation_type: The tax type for this section.
        obligations: All obligations of this type for the entity.
        thresholds: Threshold checks relevant to this obligation type.
        deadlines: Deadline records for this obligation type.
        loss_records: Loss carryforward records applied in this run.
        jurisdiction: Two-letter jurisdiction code.
    Returns:
        A BriefSection with narrative=None.
    """
    obligation = obligations[0] if obligations else None
    needs_review = (
        (obligation.needs_review if obligation else False)
        or any(t.breached for t in thresholds)
    )
    return BriefSection(
        section_id=str(uuid.uuid4()),
        title=_section_title(obligation_type, jurisdiction),
        obligation_type=obligation_type,
        obligation=obligation,
        thresholds=thresholds,
        deadlines=deadlines,
        loss_records=loss_records,
        narrative=None,
        needs_review=needs_review,
    )


def build_filing_brief(result: EngineRunResult, entity_record: EntityRecord) -> FilingBrief:
    """Build a FilingBrief skeleton from engine output and entity metadata.

    All numeric slots are engine-sourced. Narrative fields are None;
    the assembler populates them if a narrator is available.

    Args:
        result: Full engine run result for one entity.
        entity_record: The entity's canonical record (for name, jurisdiction).
    Returns:
        FilingBrief with sections, conflicts, and open_questions populated.
    """
    obligation_by_type: dict[ObligationType, list[ObligationResult]] = {}
    for obligation in result.obligations:
        obligation_by_type.setdefault(obligation.obligation_type, []).append(obligation)

    threshold_by_type: dict[ObligationType, list[ThresholdResult]] = {
        ObligationType.CIT: [t for t in result.threshold_checks if "zinsschranke" in t.threshold_name.lower() or "loss" in t.threshold_name.lower()],
        ObligationType.VAT: [t for t in result.threshold_checks if "vat" in t.threshold_name.lower()],
        ObligationType.WHT: [t for t in result.threshold_checks if "wht" in t.threshold_name.lower()],
    }
    deadline_by_type: dict[ObligationType, list[DeadlineResult]] = {}
    for deadline in result.deadlines:
        deadline_by_type.setdefault(deadline.obligation_type, []).append(deadline)

    all_types = sorted(obligation_by_type.keys(), key=lambda t: t.value)
    sections: list[BriefSection] = []
    for ot in all_types:
        obs = obligation_by_type.get(ot, [])
        thresholds = threshold_by_type.get(ot, [])
        deadlines = deadline_by_type.get(ot, [])
        loss = result.loss_carryforward_applied if ot == ObligationType.CIT else []

        if ot == ObligationType.WHT and len(obs) > 1:
            # One section per WHT flow — each payment is a distinct cross-border obligation.
            # Thresholds and deadlines attach to the first section only.
            for i, ob in enumerate(obs):
                sections.append(_build_section(
                    obligation_type=ot,
                    obligations=[ob],
                    thresholds=thresholds if i == 0 else [],
                    deadlines=deadlines if i == 0 else [],
                    loss_records=[],
                    jurisdiction=entity_record.resident_jurisdiction,
                ))
        else:
            sections.append(_build_section(ot, obs, thresholds, deadlines, loss, entity_record.resident_jurisdiction))

    conflict_explanations: list[ConflictExplanation] = [
        ConflictExplanation(
            conflict=conflict,
            narrative=None,
            treaty_pointer=_treaty_pointer(conflict),
            recommended_action=None,
        )
        for conflict in result.conflicts
    ]

    open_qs = _open_questions(sections, result)
    needs_review = result.has_unresolved_items or any(c.conflict.needs_review for c in conflict_explanations)

    return FilingBrief(
        brief_id=str(uuid.uuid4()),
        entity_id=result.entity_id,
        entity_name=entity_record.name,
        jurisdiction=entity_record.resident_jurisdiction,
        fiscal_period=result.fiscal_period,
        generated_at=datetime.now(tz=timezone.utc),
        sections=sections,
        conflicts=conflict_explanations,
        group_relief_opportunities=result.group_relief_opportunities,
        open_questions=open_qs,
        as_of_dates=_collect_as_of_dates(result),
        needs_review=needs_review,
    )


def build_cross_border_report(briefs: list[FilingBrief]) -> CrossBorderReport:
    """Build a CrossBorderReport from a list of entity briefs.

    De-duplicates conflicts by conflict_id across all briefs.
    ``pe_triangle_narrative`` is None; the assembler fills it if a narrator is available.

    Args:
        briefs: Per-entity filing briefs for the whole group.
    Returns:
        CrossBorderReport with all unique conflicts and group-relief opportunities.
    """
    seen_conflict_ids: set[str] = set()
    all_conflicts: list[ConflictExplanation] = []
    all_relief: list = []

    for brief in briefs:
        for conflict_explanation in brief.conflicts:
            cid = conflict_explanation.conflict.conflict_id
            if cid not in seen_conflict_ids:
                seen_conflict_ids.add(cid)
                all_conflicts.append(conflict_explanation)
        all_relief.extend(brief.group_relief_opportunities)

    return CrossBorderReport(
        report_id=str(uuid.uuid4()),
        generated_at=datetime.now(tz=timezone.utc),
        entity_ids=[b.entity_id for b in briefs],
        conflicts=all_conflicts,
        pe_triangle_narrative=None,
        group_relief_opportunities=all_relief,
    )
