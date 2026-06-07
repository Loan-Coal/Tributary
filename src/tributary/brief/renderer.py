"""
Module: renderer
Layer: brief
Purpose: Renders FilingBrief and CrossBorderReport objects to markdown strings for
    file output and human review. Displays amounts in the entity's local currency using
    the FX rate supplied by the caller (W7a). All numeric values are sourced from engine
    output. This module is pure string formatting — no computation, no AI calls.
Dependencies: decimal, tributary.brief.models, tributary.common.models_entity
Used by: engine.cli
"""
from __future__ import annotations

from decimal import Decimal

from tributary.common.models_entity import ObligationType

from .models import BriefSection, ConflictExplanation, CrossBorderReport, FilingBrief


def _fmt_local(amount_hkd: Decimal, fx_rate: Decimal, currency: str) -> str:
    """Convert an HKD amount to local currency and format with currency code.

    Args:
        amount_hkd: Amount stored in HKD.
        fx_rate: HKD units per one local-currency unit (e.g. 8.50 for EUR/HKD).
        currency: ISO 4217 currency code (e.g. "EUR", "HKD").
    Returns:
        Formatted string, e.g. "EUR 1,234" or "HKD 10,493".
    """
    if fx_rate == Decimal("1") or currency == "HKD":
        local = amount_hkd
    else:
        local = amount_hkd / fx_rate
    return f"{currency} {local:,.0f}"


def _fmt_days(value: Decimal) -> str:
    """Format a day-count value (no currency suffix).

    Args:
        value: Number of days as Decimal.
    Returns:
        Formatted string, e.g. "185 days".
    """
    return f"{value:,.0f} days"


def _fmt_pct(rate: Decimal) -> str:
    """Format a Decimal rate as a percentage.

    Args:
        rate: Decimal between 0 and 1.
    Returns:
        Formatted percentage string, e.g. "15.825%".
    """
    return f"{rate * 100:.3f}".rstrip("0").rstrip(".") + "%"


def _fmt_threshold(threshold, fx_rate: Decimal, currency: str) -> str:
    """Format a threshold value using the correct unit (days or currency).

    Args:
        threshold: ThresholdResult instance.
        fx_rate: FX rate for monetary conversion.
        currency: Local currency code.
    Returns:
        Formatted string.
    """
    if getattr(threshold, "unit", "HKD") == "days":
        return _fmt_days(threshold.actual_value_hkd)
    return _fmt_local(threshold.actual_value_hkd, fx_rate, currency)


def _fmt_threshold_limit(threshold, fx_rate: Decimal, currency: str) -> str:
    """Format a threshold limit value using the correct unit.

    Args:
        threshold: ThresholdResult instance.
        fx_rate: FX rate for monetary conversion.
        currency: Local currency code.
    Returns:
        Formatted string.
    """
    if getattr(threshold, "unit", "HKD") == "days":
        return _fmt_days(threshold.threshold_value_hkd)
    return _fmt_local(threshold.threshold_value_hkd, fx_rate, currency)


def _render_obligation_lines(section: BriefSection, fx_rate: Decimal, currency: str) -> list[str]:
    """Build the obligation lines for a brief section, branching on obligation type.

    Args:
        section: The brief section containing the obligation.
        fx_rate: FX rate for amount conversion.
        currency: Local currency code.
    Returns:
        List of markdown lines for the obligation.
    """
    o = section.obligation
    if o is None:
        return []
    lines: list[str] = []
    if o.obligation_type is ObligationType.WHT:
        lines.extend(_render_wht_lines(o, fx_rate, currency))
    elif o.obligation_type is ObligationType.VAT:
        lines.extend(_render_vat_lines(o, fx_rate, currency))
    else:
        lines.extend(_render_standard_obligation_lines(o, fx_rate, currency))
    lines.append(
        f"**Rule:** {o.rule_id} (as of {o.as_of_date.isoformat()}) — {o.source_citation}"
    )
    if o.source_flow_ids:
        lines.append(f"**Source flows:** {', '.join(o.source_flow_ids)}")
    if o.needs_review:
        lines.append("⚠ **Needs review**")
        if o.review_reason:
            lines.append(f"  *{o.review_reason}*")
    return lines


def _render_standard_obligation_lines(o, fx_rate: Decimal, currency: str) -> list[str]:
    """Render standard (CIT / Trade Tax) obligation: base | rate | obligation.

    Args:
        o: ObligationResult.
        fx_rate: FX rate.
        currency: Local currency code.
    Returns:
        List of markdown lines.
    """
    return [
        f"**Taxable base:** {_fmt_local(o.taxable_base_hkd, fx_rate, currency)} | "
        f"**Rate:** {_fmt_pct(o.rate)} | "
        f"**Tax obligation:** {_fmt_local(o.net_amount_hkd, fx_rate, currency)}"
    ]


def _render_wht_lines(o, fx_rate: Decimal, currency: str) -> list[str]:
    """Render WHT obligation: gross payment → statutory WHT → treaty relief → net.

    Args:
        o: ObligationResult of type WHT.
        fx_rate: FX rate.
        currency: Local currency code.
    Returns:
        List of markdown lines.
    """
    lines = [
        f"**Gross payment:** {_fmt_local(o.taxable_base_hkd, fx_rate, currency)} | "
        f"**Statutory WHT:** {_fmt_local(o.gross_amount_hkd, fx_rate, currency)}"
    ]
    if o.treaty_relief_hkd > Decimal("0"):
        lines.append(
            f"**Treaty relief:** -{_fmt_local(o.treaty_relief_hkd, fx_rate, currency)} | "
            f"**Net obligation:** {_fmt_local(o.net_amount_hkd, fx_rate, currency)}"
        )
        if o.treaty_citation:
            tc = o.treaty_citation
            lines.append(
                f"**Treaty rule:** {tc.rule_id} (as of {tc.as_of_date.isoformat()}) — {tc.source_citation}"
            )
    else:
        lines.append(f"**Net obligation:** {_fmt_local(o.net_amount_hkd, fx_rate, currency)}")
    return lines


def _render_vat_lines(o, fx_rate: Decimal, currency: str) -> list[str]:
    """Render VAT obligation: registration threshold breached, filing required.

    Args:
        o: ObligationResult of type VAT.
        fx_rate: FX rate.
        currency: Local currency code.
    Returns:
        List of markdown lines.
    """
    return [
        f"**Turnover:** {_fmt_local(o.taxable_base_hkd, fx_rate, currency)}",
        "Registration threshold breached — quarterly VAT returns required. "
        "Net VAT arithmetic not modelled (scope: Wave 7b+).",
    ]


def _render_section(section: BriefSection, fx_rate: Decimal, currency: str) -> str:
    """Render one BriefSection to markdown.

    Args:
        section: The section to render.
        fx_rate: FX rate for amount conversion.
        currency: Local currency code.
    Returns:
        Markdown string for this section.
    """
    lines: list[str] = [f"## [{section.obligation_type.value.upper()}] {section.title}"]
    lines.extend(_render_obligation_lines(section, fx_rate, currency))

    for loss in section.loss_records:
        lines.append(
            f"**Loss offset applied:** {_fmt_local(loss.used_this_period_hkd, fx_rate, currency)} "
            f"(FY{loss.loss_period.start_date.year}, {loss.entity_id}) — "
            f"remaining: {_fmt_local(loss.remaining_loss_hkd, fx_rate, currency)}"
        )

    for threshold in section.thresholds:
        status = "BREACHED" if threshold.breached else "OK"
        actual = _fmt_threshold(threshold, fx_rate, currency)
        limit = _fmt_threshold_limit(threshold, fx_rate, currency)
        lines.append(
            f"**{threshold.threshold_name}:** {status} "
            f"(actual {actual} vs limit {limit})"
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
        f"**Attributed base:** HKD {flag.attributed_base_hkd:,.0f}",
        f"**PE tax:** HKD {flag.pe_tax_hkd:,.0f} | "
        f"**Residence tax (before relief):** HKD {flag.residence_tax_before_relief_hkd:,.0f}",
        f"**Resolution:** {conflict.treaty_pointer}",
        f"**Residual double-tax:** HKD {flag.residual_double_tax_hkd:,.0f}",
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


def _obligation_rule_ids(brief: FilingBrief) -> set[str]:
    """Collect the set of rule IDs from sections that have an obligation.

    Args:
        brief: Filing brief whose sections to inspect.
    Returns:
        Set of rule_id strings from obligations only.
    """
    return {s.obligation.rule_id for s in brief.sections if s.obligation is not None}


def render_brief_markdown(
    brief: FilingBrief,
    local_currency: str,
    fx_rate: Decimal,
    fx_source: str = "",
) -> str:
    """Render a complete FilingBrief to a markdown string.

    Args:
        brief: The filing brief to render.
        local_currency: ISO 4217 currency code for this jurisdiction (e.g. "EUR").
        fx_rate: HKD per one local-currency unit (e.g. Decimal("8.50") for EUR/HKD).
        fx_source: Human-readable rate source label for the header (e.g. "frankfurter.app 2026-06-07").
    Returns:
        Full markdown document as a string.
    """
    source_label = fx_source or f"ECB/HKMA reference, {brief.fiscal_period.start_date.isoformat()}"
    header_lines: list[str] = [
        f"# Filing Brief — {brief.entity_name} ({brief.jurisdiction})",
        f"**Entity ID:** {brief.entity_id}",
        f"**Fiscal period:** {brief.fiscal_period.start_date.isoformat()} to "
        f"{brief.fiscal_period.end_date.isoformat()}",
        f"**Generated:** {brief.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
    ]
    if local_currency != "HKD":
        header_lines.append(
            f"*Amounts shown in {local_currency} at {local_currency}/HKD = "
            f"{fx_rate:g} ({source_label})*"
        )
    if brief.needs_review:
        header_lines.append("⚠ **This brief contains items requiring professional review.**")

    sections_md = [_render_section(s, fx_rate, local_currency) for s in brief.sections]
    conflicts_md = [_render_conflict(c) for c in brief.conflicts]

    open_q_lines: list[str] = []
    if brief.open_questions:
        open_q_lines = ["## Open Questions"] + [f"- {q}" for q in brief.open_questions]

    obligation_rule_ids = _obligation_rule_ids(brief)
    filtered_aod = {
        rule_id: aod
        for rule_id, aod in sorted(brief.as_of_dates.items())
        if rule_id in obligation_rule_ids
    }
    aod_lines: list[str] = []
    if filtered_aod:
        aod_lines = ["## Rule As-of Dates"] + [
            f"- `{rule_id}`: {aod}" for rule_id, aod in filtered_aod.items()
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
