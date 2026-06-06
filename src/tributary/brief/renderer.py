"""
Module: renderer
Layer: brief
Purpose: Renders FilingBrief and CrossBorderReport objects to markdown strings for
    file output and human review. All numeric values are sourced from engine output.
    This module is pure string formatting — no computation, no AI calls.
Dependencies: tributary.brief.models
Used by: engine.cli
"""
from __future__ import annotations

from .models import BriefSection, ConflictExplanation, CrossBorderReport, FilingBrief


def _fmt_hkd(amount) -> str:
    """Format a Decimal as HKD with comma thousands separator.

    Args:
        amount: Decimal amount.
    Returns:
        Formatted string, e.g. "HKD 1,234,567".
    """
    return f"HKD {amount:,.0f}"


def _fmt_pct(rate) -> str:
    """Format a Decimal rate as a percentage.

    Args:
        rate: Decimal between 0 and 1.
    Returns:
        Formatted percentage string, e.g. "15.825%".
    """
    return f"{rate * 100:.3f}%".rstrip("0").rstrip(".")


def _render_section(section: BriefSection) -> str:
    """Render one BriefSection to markdown.

    Args:
        section: The section to render.
    Returns:
        Markdown string for this section.
    """
    lines: list[str] = [f"## [{section.obligation_type.value.upper()}] {section.title}"]

    if section.obligation:
        o = section.obligation
        lines.append(
            f"**Taxable base:** {_fmt_hkd(o.taxable_base_hkd)} | "
            f"**Rate:** {_fmt_pct(o.rate)} | "
            f"**Tax obligation:** {_fmt_hkd(o.net_amount_hkd)}"
        )
        if o.treaty_relief_hkd and o.treaty_relief_hkd > 0:
            lines.append(f"**Treaty relief:** {_fmt_hkd(o.treaty_relief_hkd)}")
        lines.append(
            f"**Rule:** {o.rule_id} (as of {o.as_of_date.isoformat()}) — {o.source_citation}"
        )
        if o.source_flow_ids:
            lines.append(f"**Source flows:** {', '.join(o.source_flow_ids)}")
        if o.needs_review:
            lines.append("⚠ **Needs review**")

    for loss in section.loss_records:
        lines.append(
            f"**Loss offset applied:** {_fmt_hkd(loss.used_this_period_hkd)} "
            f"(FY{loss.loss_period.start_date.year}, {loss.entity_id}) — "
            f"remaining: {_fmt_hkd(loss.remaining_loss_hkd)}"
        )

    for threshold in section.thresholds:
        status = "BREACHED" if threshold.breached else "OK"
        lines.append(
            f"**{threshold.threshold_name}:** {status} "
            f"(actual {_fmt_hkd(threshold.actual_value_hkd)} vs "
            f"limit {_fmt_hkd(threshold.threshold_value_hkd)})"
        )

    for deadline in section.deadlines:
        lines.append(
            f"**Filing deadline:** {deadline.filing_deadline.isoformat()} | "
            f"**Payment deadline:** {deadline.payment_deadline.isoformat()}"
        )

    if section.narrative:
        lines.append("")
        lines.append(section.narrative)

    return "\n".join(lines)


def _render_conflict(conflict: ConflictExplanation) -> str:
    """Render one ConflictExplanation to markdown.

    Args:
        conflict: The conflict explanation to render.
    Returns:
        Markdown string for this conflict.
    """
    flag = conflict.conflict
    lines: list[str] = [
        f"## ⚠ {flag.conflict_type.value.replace('_', ' ').title()}",
        f"**Entities:** {', '.join(flag.entities)}",
        f"**Jurisdictions:** {', '.join(flag.jurisdictions)}",
        f"**Attributed base:** {_fmt_hkd(flag.attributed_base_hkd)}",
        f"**PE tax:** {_fmt_hkd(flag.pe_tax_hkd)} | "
        f"**Residence tax (before relief):** {_fmt_hkd(flag.residence_tax_before_relief_hkd)}",
        f"**Resolution:** {conflict.treaty_pointer}",
        f"**Residual double-tax:** {_fmt_hkd(flag.residual_double_tax_hkd)}",
        f"**Treaty:** {flag.treaty_rule_id} (as of {flag.treaty_as_of_date.isoformat()}) — "
        f"{flag.treaty_source_citation}",
    ]
    if flag.credit_method_note:
        lines.append(f"*Note: {flag.credit_method_note}*")
    if conflict.recommended_action:
        lines.append(f"**Recommended action:** {conflict.recommended_action}")
    if conflict.narrative:
        lines.append("")
        lines.append(conflict.narrative)
    return "\n".join(lines)


def render_brief_markdown(brief: FilingBrief) -> str:
    """Render a complete FilingBrief to a markdown string.

    Args:
        brief: The filing brief to render.
    Returns:
        Full markdown document as a string.
    """
    header_lines: list[str] = [
        f"# Filing Brief — {brief.entity_name} ({brief.jurisdiction})",
        f"**Entity ID:** {brief.entity_id}",
        f"**Fiscal period:** {brief.fiscal_period.start_date.isoformat()} to "
        f"{brief.fiscal_period.end_date.isoformat()}",
        f"**Generated:** {brief.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
    ]
    if brief.needs_review:
        header_lines.append("⚠ **This brief contains items requiring professional review.**")

    sections_md = [_render_section(s) for s in brief.sections]
    conflicts_md = [_render_conflict(c) for c in brief.conflicts]

    open_q_lines: list[str] = []
    if brief.open_questions:
        open_q_lines = ["## Open Questions"] + [f"- {q}" for q in brief.open_questions]

    aod_lines: list[str] = []
    if brief.as_of_dates:
        aod_lines = ["## Rule As-of Dates"] + [
            f"- `{rule_id}`: {aod}" for rule_id, aod in sorted(brief.as_of_dates.items())
        ]

    parts = [
        "\n".join(header_lines),
        "---",
        *sections_md,
        *(["---", *conflicts_md] if conflicts_md else []),
        *open_q_lines,
        *aod_lines,
    ]
    return "\n\n".join(parts)


def render_report_markdown(report: CrossBorderReport) -> str:
    """Render a CrossBorderReport to a markdown string.

    Args:
        report: The cross-border conflict report to render.
    Returns:
        Full markdown document as a string.
    """
    header_lines: list[str] = [
        "# Cross-Border Conflict Report — Meridian Group",
        f"**Entities:** {', '.join(report.entity_ids)}",
        f"**Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
    ]

    if not report.conflicts:
        return "\n".join(header_lines) + "\n\n*No cross-border conflicts detected.*"

    conflicts_md = [_render_conflict(c) for c in report.conflicts]

    pe_narrative_section: list[str] = []
    if report.pe_triangle_narrative:
        pe_narrative_section = ["## PE Triangle Summary", report.pe_triangle_narrative]

    relief_section: list[str] = []
    if report.group_relief_opportunities:
        relief_section = ["## Group Relief Opportunities"]
        for opp in report.group_relief_opportunities:
            relief_section.append(
                f"- {opp.income_entity_id} ({opp.income_jurisdiction}) → "
                f"{opp.loss_entity_id} ({opp.loss_jurisdiction}): "
                f"{opp.relief_mechanism.value} — rule {opp.applicable_rule_id} "
                f"(as of {opp.as_of_date.isoformat()}) ⚠ requires review"
            )

    parts = [
        "\n".join(header_lines),
        "---",
        *conflicts_md,
        *pe_narrative_section,
        *relief_section,
    ]
    return "\n\n".join(parts)
