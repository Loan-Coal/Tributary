"""
Module: narrator
Layer: brief
Purpose: Generates AI prose narratives for brief sections and conflict explanations.
    Calls the injected LLM client with versioned YAML prompts. Falls back gracefully
    if AI is unavailable — the brief renders from engine data alone.
Dependencies: json, tributary.common, tributary.prompts, tributary.brief.models
Used by: brief.assembler
"""
from __future__ import annotations

import json

from tributary.common.errors import AILayerError
from tributary.common.logging import get_logger
from tributary.common.models_entity import JurisdictionCode
from tributary.common.protocols_ai import NarratorClientProtocol
from tributary.prompts.loader import load_brief_narrative_prompts
from .models import BriefSection, ConflictExplanation

logger = get_logger(__name__)

_UNAVAILABLE_MSG = "[Narrative unavailable — review required]"


def _format_section_summary(section: BriefSection) -> str:
    """Serialise a BriefSection to a compact JSON string for the prompt.

    Args:
        section: The section to summarise.
    Returns:
        JSON string with obligation type, rule ids, source flows, and deadline dates.
    """
    obligation = section.obligation
    summary: dict = {
        "obligation_type": section.obligation_type.value,
        "has_obligation": obligation is not None,
        "needs_review": section.needs_review,
    }
    if obligation is not None:
        summary["rule_id"] = obligation.rule_id
        summary["as_of_date"] = obligation.as_of_date.isoformat()
        summary["source_citation"] = obligation.source_citation
        summary["source_flow_ids"] = obligation.source_flow_ids
        if obligation.loss_carryforward_applied if hasattr(obligation, "loss_carryforward_applied") else False:
            summary["loss_carryforward_applied"] = True
    if section.deadlines:
        summary["filing_deadline"] = section.deadlines[0].filing_deadline.isoformat()
        summary["payment_deadline"] = section.deadlines[0].payment_deadline.isoformat()
    if section.thresholds:
        summary["threshold_checks"] = [
            {"name": t.threshold_name, "breached": t.breached} for t in section.thresholds
        ]
    return json.dumps(summary, indent=2)


def _format_conflict_summary(conflict: ConflictExplanation) -> str:
    """Serialise a ConflictExplanation to a compact JSON string for the prompt.

    Args:
        conflict: The conflict explanation to summarise.
    Returns:
        JSON string with conflict type, entities, jurisdictions, and treaty reference.
    """
    flag = conflict.conflict
    return json.dumps(
        {
            "conflict_type": flag.conflict_type.value,
            "entities": flag.entities,
            "jurisdictions": list(flag.jurisdictions),
            "residence_jurisdiction": flag.residence_jurisdiction,
            "pe_jurisdiction": flag.pe_jurisdiction,
            "relief_mechanism": flag.relief_mechanism.value,
            "treaty_rule_id": flag.treaty_rule_id,
            "treaty_as_of_date": flag.treaty_as_of_date.isoformat(),
            "treaty_source_citation": flag.treaty_source_citation,
            "needs_review": flag.needs_review,
            "treaty_pointer": conflict.treaty_pointer,
        },
        indent=2,
    )


def _format_rule_citations(section: BriefSection) -> str:
    """Format available rule citations for the section narrative prompt.

    Args:
        section: The section whose citations to list.
    Returns:
        Newline-separated list of rule_id + as_of_date strings.
    """
    lines: list[str] = []
    if section.obligation:
        o = section.obligation
        lines.append(f"- {o.rule_id} (as of {o.as_of_date.isoformat()}): {o.source_citation}")
        if o.treaty_citation:
            tc = o.treaty_citation
            lines.append(f"- {tc.rule_id} (as of {tc.as_of_date.isoformat()}): {tc.source_citation}")
    for t in section.thresholds:
        lines.append(f"- {t.rule_id} (as of {t.as_of_date.isoformat()}): {t.source_citation}")
    return "\n".join(lines) if lines else "(none)"


class BriefNarrator:
    """Generates AI prose narratives for filing brief sections and conflict explanations.

    Loads versioned prompts from brief_narrative.yaml. On any AI error, returns a
    safe fallback message so the brief still renders from engine data alone.
    """

    def __init__(self, llm_client: NarratorClientProtocol) -> None:
        """Wire the narrator LLM client.

        Args:
            llm_client: Client implementing NarratorClientProtocol (generate returns str).
        """
        self._client = llm_client
        self._prompts = load_brief_narrative_prompts()

    def narrate_section(
        self, section: BriefSection, entity_name: str, jurisdiction: JurisdictionCode
    ) -> str:
        """Generate AI prose for one brief section.

        Args:
            section: The section to narrate.
            entity_name: Name of the entity (for personalisation).
            jurisdiction: Two-letter jurisdiction code.
        Returns:
            AI narrative string, or fallback message on error.
        """
        template = self._prompts["section_narrative"]
        prompt = (
            template
            .replace("{{entity_name}}", entity_name)
            .replace("{{jurisdiction}}", jurisdiction)
            .replace("{{obligation_type}}", section.obligation_type.value)
            .replace("{{section_summary}}", _format_section_summary(section))
            .replace("{{rule_citations}}", _format_rule_citations(section))
        )
        try:
            output = self._client.generate(
                system_prompt=prompt,
                user_message=f"Write the section narrative for {section.title}.",
            )
            return output.strip()
        except (AILayerError, Exception) as exc:
            logger.warning("Section narrative generation failed", extra={"error": str(exc)})
            return _UNAVAILABLE_MSG

    def narrate_conflict(self, conflict: ConflictExplanation) -> str:
        """Generate AI prose for one conflict explanation.

        Args:
            conflict: The conflict explanation to narrate.
        Returns:
            AI narrative string, or fallback message on error.
        """
        template = self._prompts["conflict_narrative"]
        prompt = template.replace("{{conflict_summary}}", _format_conflict_summary(conflict))
        try:
            output = self._client.generate(
                system_prompt=prompt,
                user_message="Write the conflict explanation.",
            )
            return output.strip()
        except (AILayerError, Exception) as exc:
            logger.warning("Conflict narrative generation failed", extra={"error": str(exc)})
            return _UNAVAILABLE_MSG
