"""
Module: assembler
Layer: brief
Purpose: Composes complete FilingBrief and CrossBorderReport objects by combining
    engine-sourced templates with optional AI prose narratives. If no narrator is
    provided, all narrative fields remain None and briefs render from engine data alone.
Dependencies: tributary.common, tributary.brief.models, tributary.brief.template,
    tributary.brief.narrator
Used by: engine.cli
"""
from __future__ import annotations

from tributary.common.logging import get_logger
from tributary.common.models_engine import ConflictType, EngineRunResult
from tributary.common.models_entity import EntityRecord
from .models import CrossBorderReport, FilingBrief
from .narrator import BriefNarrator
from .template import build_cross_border_report, build_filing_brief

logger = get_logger(__name__)

_PE_TRIANGLE_TYPES = frozenset({ConflictType.SERVICE_PE_DOUBLE_TAX})


class BriefAssembler:
    """Orchestrates brief assembly: template → optional AI narrative → final brief.

    If ``narrator`` is None, briefs are assembled purely from engine data.
    This is the demo-safe mode (no live Claude API required).
    """

    def __init__(self, narrator: BriefNarrator | None) -> None:
        """Wire the narrator.

        Args:
            narrator: Optional BriefNarrator for AI prose. None for offline mode.
        """
        self._narrator = narrator

    def assemble(self, result: EngineRunResult, entity_record: EntityRecord) -> FilingBrief:
        """Build a complete FilingBrief for one entity.

        Args:
            result: Full engine run result for the entity.
            entity_record: The entity's canonical record.
        Returns:
            FilingBrief with all sections and optional AI narratives.
        """
        brief = build_filing_brief(result, entity_record)
        if self._narrator is None:
            return brief
        return self._add_narratives(brief)

    def assemble_report(self, briefs: list[FilingBrief]) -> CrossBorderReport:
        """Build a CrossBorderReport from all entity briefs.

        Args:
            briefs: Per-entity filing briefs for the whole group.
        Returns:
            CrossBorderReport with de-duplicated conflicts and optional PE triangle narrative.
        """
        report = build_cross_border_report(briefs)
        if self._narrator is None:
            return report
        return self._add_report_narrative(report)

    def _add_narratives(self, brief: FilingBrief) -> FilingBrief:
        """Fill narrative fields in each section and conflict explanation.

        Args:
            brief: Brief with None narrative fields.
        Returns:
            Brief with AI prose populated in each section.
        """
        assert self._narrator is not None
        updated_sections = []
        for section in brief.sections:
            narrative = self._narrator.narrate_section(
                section, brief.entity_name, brief.jurisdiction
            )
            updated_sections.append(section.model_copy(update={"narrative": narrative}))

        updated_conflicts = []
        for conflict_explanation in brief.conflicts:
            narrative = self._narrator.narrate_conflict(conflict_explanation)
            updated_conflicts.append(
                conflict_explanation.model_copy(update={"narrative": narrative})
            )

        return brief.model_copy(
            update={"sections": updated_sections, "conflicts": updated_conflicts}
        )

    def _add_report_narrative(self, report: CrossBorderReport) -> CrossBorderReport:
        """Fill narrative fields in conflict explanations and add PE triangle narrative.

        Args:
            report: Report with None narrative fields.
        Returns:
            Report with AI prose populated.
        """
        assert self._narrator is not None
        updated_conflicts = []
        pe_triangle_narrative: str | None = None
        for conflict_explanation in report.conflicts:
            narrative = self._narrator.narrate_conflict(conflict_explanation)
            updated = conflict_explanation.model_copy(update={"narrative": narrative})
            updated_conflicts.append(updated)
            if conflict_explanation.conflict.conflict_type in _PE_TRIANGLE_TYPES:
                pe_triangle_narrative = narrative

        return report.model_copy(
            update={
                "conflicts": updated_conflicts,
                "pe_triangle_narrative": pe_triangle_narrative,
            }
        )
