"""
Module: group_renderer
Layer: brief
Purpose: Render a GroupSummary to a markdown executive summary document.
Dependencies: decimal, brief.group_summary
Used by: engine.cli (_write_outputs)
"""
from __future__ import annotations

from decimal import Decimal

from tributary.brief.group_summary import GroupSummary

_ZERO = Decimal("0")

_HKD_FMT = "HKD {:,.0f}"
_LOCAL_FMT = "{} {:,.0f}"


def _hkd(amount: Decimal) -> str:
    return _HKD_FMT.format(amount)


def _local(amount: Decimal, currency: str, fx_rate: Decimal) -> str:
    if currency == "HKD" or fx_rate == _ZERO:
        return _hkd(amount)
    return _LOCAL_FMT.format(currency, amount / fx_rate)


def render_group_summary_markdown(
    summary: GroupSummary,
    fx_map: dict[str, Decimal],
    fx_source: str = "",
) -> str:
    """Render a GroupSummary to a markdown executive summary.

    Args:
        summary: Aggregated group tax data.
        fx_map: Currency → HKD rate for reference conversions in header.
        fx_source: Human-readable source label for FX rates.
    Returns:
        Full markdown document as a string.
    """
    lines: list[str] = []

    lines.append("# Group Tax Exposure — Executive Summary")
    lines.append(f"**Fiscal year:** {summary.fiscal_year}")
    lines.append(f"**Generated:** {summary.generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
    if fx_source:
        lines.append(f"*FX rates: {fx_source} — all amounts shown in HKD*")
    else:
        lines.append("*All amounts shown in HKD*")
    if summary.review_flag_count:
        lines.append(f"⚠ **{summary.review_flag_count} entit{'y' if summary.review_flag_count == 1 else 'ies'} require professional review.**")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Entity-by-entity table
    lines.append("## Tax Obligation by Entity")
    lines.append("")
    lines.append("| Entity | Jurisdiction | CIT | Trade Tax | WHT (net) | **Total** | Review |")
    lines.append("|--------|-------------|----:|----------:|----------:|----------:|:------:|")
    for ln in summary.entity_lines:
        flag = "⚠" if ln.needs_review else "✓"
        lines.append(
            f"| {ln.entity_name} | {ln.jurisdiction} "
            f"| {_hkd(ln.cit_hkd)} "
            f"| {_hkd(ln.trade_tax_hkd) if ln.trade_tax_hkd else '—'} "
            f"| {_hkd(ln.wht_net_hkd)} "
            f"| **{_hkd(ln.total_hkd)}** "
            f"| {flag} |"
        )

    # Totals row
    lines.append(
        f"| **Group Total** | | **{_hkd(summary.total_cit_hkd)}** "
        f"| **{_hkd(summary.total_trade_tax_hkd)}** "
        f"| **{_hkd(summary.total_wht_hkd)}** "
        f"| **{_hkd(summary.total_obligation_hkd)}** | |"
    )

    # Cross-border conflicts
    if summary.conflicts:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Cross-Border Conflicts")
        lines.append("")
        for conflict in summary.conflicts:
            entities_str = ", ".join(conflict.entities)
            jur_str = " / ".join(conflict.jurisdictions)
            lines.append(f"### {conflict.conflict_type.value.replace('_', ' ').title()}")
            lines.append(f"**Entities:** {entities_str} | **Jurisdictions:** {jur_str}")
            lines.append(
                f"**Attributed base:** {_hkd(conflict.attributed_base_hkd)} | "
                f"**Residual double-tax after relief:** {_hkd(conflict.residual_double_tax_hkd)}"
            )
            lines.append(f"**Resolution:** {conflict.relief_mechanism.value} — {conflict.treaty_source_citation}")
            lines.append("")
        if summary.residual_double_tax_hkd > _ZERO:
            lines.append(f"**Total unrelieved double-tax: {_hkd(summary.residual_double_tax_hkd)}**")
        else:
            lines.append("*All detected conflicts fully relieved by treaty.*")

    # Group relief opportunities
    if summary.group_relief_opportunities:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Group Relief Opportunities")
        lines.append("")
        lines.append("*Requires professional review before action — engine flags opportunity only.*")
        lines.append("")
        for opp in summary.group_relief_opportunities:
            lines.append(
                f"- **{opp.income_entity_id} → {opp.loss_entity_id}** "
                f"({opp.income_jurisdiction}/{opp.loss_jurisdiction}): "
                f"{_hkd(opp.available_income_hkd)} income vs {_hkd(opp.unused_loss_hkd)} unused loss — "
                f"{opp.relief_mechanism.value} ({opp.applicable_rule_id})"
            )

    # Open items requiring review
    if summary.open_items:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Items Requiring Professional Review")
        lines.append("")
        for item in summary.open_items:
            lines.append(f"- {item}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*See individual entity briefs for full citations, deadlines, and rule as-of dates.*")
    lines.append(f"*Conflict detail: see `conflict_report.md`.*")

    return "\n".join(lines)
