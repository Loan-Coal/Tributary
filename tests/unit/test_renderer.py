"""
Module: test_renderer
Layer: test-unit
Purpose: Regression tests for brief/renderer.py — currency display, PE-day threshold
    format, WHT gross→treaty→net structure, VAT section content, FX footnote, review_reason
    rendering, and as-of date filtering. No I/O, no Neo4j, no AI calls.
Dependencies: datetime, decimal, pytest, tributary.brief.renderer, tributary.brief.models,
    tributary.common.models_engine, tributary.common.models_entity
Used by: make test
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

from tributary.brief.models import BriefSection, FilingBrief
from tributary.brief.renderer import (
    _fmt_local,
    _fmt_pct,
    _fmt_threshold,
    render_brief_markdown,
)
from tributary.common.models_engine import (
    DeadlineResult,
    ObligationResult,
    RuleCitation,
    ThresholdResult,
)
from tributary.common.models_entity import FiscalPeriod, ObligationType


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_PERIOD = FiscalPeriod(jurisdiction="HK", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
_AOD = date(2025, 1, 1)


def _obligation(
    obligation_type: ObligationType = ObligationType.CIT,
    taxable_base_hkd: Decimal = Decimal("1000000"),
    rate: Decimal = Decimal("0.165"),
    gross_amount_hkd: Decimal = Decimal("165000"),
    treaty_relief_hkd: Decimal = Decimal("0"),
    net_amount_hkd: Decimal = Decimal("165000"),
    needs_review: bool = False,
    review_reason: str | None = None,
    treaty_citation: RuleCitation | None = None,
    rule_id: str = "HK-CIT-RATE-2024",
    source_citation: str = "HK IRO s.16",
    source_flow_ids: list[str] | None = None,
) -> ObligationResult:
    return ObligationResult(
        obligation_id=str(uuid.uuid4()),
        entity_id="LENOVO-HK",
        jurisdiction="HK",
        obligation_type=obligation_type,
        fiscal_period=_PERIOD,
        taxable_base_hkd=taxable_base_hkd,
        rate=rate,
        gross_amount_hkd=gross_amount_hkd,
        treaty_relief_hkd=treaty_relief_hkd,
        net_amount_hkd=net_amount_hkd,
        rule_id=rule_id,
        as_of_date=_AOD,
        source_citation=source_citation,
        treaty_citation=treaty_citation,
        source_flow_ids=source_flow_ids or [],
        computation_trace=[],
        needs_review=needs_review,
        review_reason=review_reason,
    )


def _section(
    obligation: ObligationResult | None = None,
    obligation_type: ObligationType = ObligationType.CIT,
    thresholds: list[ThresholdResult] | None = None,
    deadlines: list[DeadlineResult] | None = None,
) -> BriefSection:
    ob = obligation or _obligation(obligation_type=obligation_type)
    return BriefSection(
        section_id=str(uuid.uuid4()),
        title=f"{obligation_type.value} Filing",
        obligation_type=obligation_type,
        obligation=ob,
        thresholds=thresholds or [],
        deadlines=deadlines or [],
        loss_records=[],
        narrative=None,
        needs_review=ob.needs_review,
    )


def _brief(
    sections: list[BriefSection] | None = None,
    jurisdiction: str = "HK",
    as_of_dates: dict[str, str] | None = None,
) -> FilingBrief:
    secs = sections or [_section()]
    return FilingBrief(
        brief_id=str(uuid.uuid4()),
        entity_id="LENOVO-HK",
        entity_name="Meridian HK",
        jurisdiction=jurisdiction,
        fiscal_period=_PERIOD,
        generated_at=datetime(2025, 6, 7, 0, 0, 0),
        sections=secs,
        conflicts=[],
        group_relief_opportunities=[],
        open_questions=[],
        as_of_dates=as_of_dates if as_of_dates is not None else {"HK-CIT-RATE-2024": "2025-01-01"},
        needs_review=any(s.needs_review for s in secs),
    )


# ---------------------------------------------------------------------------
# Unit tests: formatting helpers
# ---------------------------------------------------------------------------


class TestFmtLocal:
    def test_hkd_passthrough(self):
        result = _fmt_local(Decimal("100000"), Decimal("1"), "HKD")
        assert result == "HKD 100,000"

    def test_eur_conversion(self):
        # 850000 HKD / 8.50 = 100000 EUR
        result = _fmt_local(Decimal("850000"), Decimal("8.50"), "EUR")
        assert result == "EUR 100,000"

    def test_usd_conversion(self):
        # 77800 HKD / 7.78 = 10000 USD
        result = _fmt_local(Decimal("77800"), Decimal("7.78"), "USD")
        assert result == "USD 10,000"

    def test_hkd_currency_always_no_divide(self):
        # If currency is HKD, no division even if rate != 1
        result = _fmt_local(Decimal("100"), Decimal("8.50"), "HKD")
        assert result == "HKD 100"


class TestFmtPct:
    def test_exact(self):
        assert _fmt_pct(Decimal("0.165")) == "16.5%"

    def test_with_surcharge(self):
        # 15% × 1.055 = 15.825%
        assert _fmt_pct(Decimal("0.15825")) == "15.825%"

    def test_integer_rate(self):
        assert _fmt_pct(Decimal("0.25")) == "25%"


class TestFmtThreshold:
    def test_monetary_threshold(self):
        t = ThresholdResult(
            entity_id="E1",
            jurisdiction="DE",
            rule_id="DE-VAT-THRESHOLD-2024",
            threshold_name="VAT Registration Threshold",
            threshold_value_hkd=Decimal("850000"),
            actual_value_hkd=Decimal("1000000"),
            breached=True,
            as_of_date=_AOD,
            source_citation="§ 19 UStG",
            unit="HKD",
        )
        result = _fmt_threshold(t, Decimal("8.50"), "EUR")
        # 1000000 / 8.50 = 117647 (approx)
        assert "EUR" in result
        assert "117,647" in result

    def test_pe_day_threshold_shows_days(self):
        t = ThresholdResult(
            entity_id="E1",
            jurisdiction="DE",
            rule_id="DE-PE-DAYS",
            threshold_name="PE Day Count",
            threshold_value_hkd=Decimal("183"),
            actual_value_hkd=Decimal("185"),
            breached=True,
            as_of_date=_AOD,
            source_citation="Art.5 OECD MC",
            unit="days",
        )
        result = _fmt_threshold(t, Decimal("8.50"), "EUR")
        assert result == "185 days"
        assert "EUR" not in result


# ---------------------------------------------------------------------------
# Integration tests: render_brief_markdown
# ---------------------------------------------------------------------------


class TestRenderBriefMarkdownCurrency:
    def test_hkd_brief_has_no_fx_footnote(self):
        md = render_brief_markdown(_brief(), "HKD", Decimal("1"))
        assert "ECB" not in md
        assert "HKMA" not in md

    def test_eur_brief_has_fx_footnote(self):
        md = render_brief_markdown(_brief(jurisdiction="DE"), "EUR", Decimal("8.50"))
        assert "EUR/HKD = 8.5" in md
        assert "ECB" in md

    def test_usd_brief_has_fx_footnote(self):
        md = render_brief_markdown(_brief(jurisdiction="US"), "USD", Decimal("7.78"))
        assert "USD/HKD = 7.78" in md
        assert "HKMA" in md

    def test_eur_amounts_converted(self):
        # CIT obligation: taxable_base_hkd=850000, net_amount_hkd=140250
        ob = _obligation(
            taxable_base_hkd=Decimal("850000"),
            gross_amount_hkd=Decimal("140250"),
            net_amount_hkd=Decimal("140250"),
        )
        md = render_brief_markdown(
            _brief(sections=[_section(obligation=ob)], jurisdiction="DE"),
            "EUR",
            Decimal("8.50"),
        )
        # 850000 / 8.50 = 100000 EUR
        assert "EUR 100,000" in md


class TestRenderBriefMarkdownWHT:
    def test_wht_no_treaty_shows_net(self):
        ob = _obligation(
            obligation_type=ObligationType.WHT,
            taxable_base_hkd=Decimal("500000"),
            rate=Decimal("0.10"),
            gross_amount_hkd=Decimal("50000"),
            treaty_relief_hkd=Decimal("0"),
            net_amount_hkd=Decimal("50000"),
        )
        md = render_brief_markdown(
            _brief(sections=[_section(obligation=ob, obligation_type=ObligationType.WHT)]),
            "HKD",
            Decimal("1"),
        )
        assert "Statutory WHT" in md
        assert "Net obligation" in md
        assert "Treaty relief" not in md

    def test_wht_with_treaty_shows_gross_relief_net(self):
        treaty = RuleCitation(
            rule_id="HK-DE-DTA-WHT",
            jurisdiction="HK",
            as_of_date=_AOD,
            source_citation="HK-DE DTA Art.11",
        )
        ob = _obligation(
            obligation_type=ObligationType.WHT,
            taxable_base_hkd=Decimal("500000"),
            rate=Decimal("0.10"),
            gross_amount_hkd=Decimal("50000"),
            treaty_relief_hkd=Decimal("25000"),
            net_amount_hkd=Decimal("25000"),
            treaty_citation=treaty,
        )
        md = render_brief_markdown(
            _brief(sections=[_section(obligation=ob, obligation_type=ObligationType.WHT)]),
            "HKD",
            Decimal("1"),
        )
        assert "Statutory WHT" in md
        assert "Treaty relief" in md
        assert "-HKD 25,000" in md
        assert "Net obligation" in md
        assert "HK-DE-DTA-WHT" in md


class TestRenderBriefMarkdownVAT:
    def test_vat_section_shows_registration_message(self):
        ob = _obligation(
            obligation_type=ObligationType.VAT,
            taxable_base_hkd=Decimal("1000000"),
            rate=Decimal("0"),
            gross_amount_hkd=Decimal("0"),
            treaty_relief_hkd=Decimal("0"),
            net_amount_hkd=Decimal("0"),
            needs_review=True,
            review_reason="VAT net arithmetic not modelled",
            rule_id="DE-VAT-THRESHOLD-2024",
        )
        md = render_brief_markdown(
            _brief(
                sections=[_section(obligation=ob, obligation_type=ObligationType.VAT)],
                as_of_dates={"DE-VAT-THRESHOLD-2024": "2025-01-01"},
            ),
            "EUR",
            Decimal("8.50"),
        )
        assert "Registration threshold breached" in md
        assert "quarterly VAT returns required" in md


class TestRenderBriefMarkdownReviewReason:
    def test_review_reason_rendered_after_flag(self):
        ob = _obligation(
            needs_review=True,
            review_reason="HK IRO s.15(1)(b) — royalty source uncertain (IP used in DE)",
        )
        md = render_brief_markdown(
            _brief(sections=[_section(obligation=ob)]),
            "HKD",
            Decimal("1"),
        )
        assert "⚠" in md
        assert "Needs review" in md
        assert "HK IRO s.15(1)(b)" in md

    def test_no_review_reason_when_not_needed(self):
        ob = _obligation(needs_review=False, review_reason=None)
        md = render_brief_markdown(
            _brief(sections=[_section(obligation=ob)]),
            "HKD",
            Decimal("1"),
        )
        assert "⚠" not in md


class TestRenderBriefMarkdownAsOfDateFilter:
    def test_only_obligation_rule_ids_shown(self):
        # as_of_dates includes extra rule IDs not referenced by any obligation
        ob = _obligation(rule_id="HK-CIT-RATE-2024")
        brief = _brief(
            sections=[_section(obligation=ob)],
            as_of_dates={
                "HK-CIT-RATE-2024": "2025-01-01",
                "HK-LOSS-RELIEF-2024": "2025-01-01",
                "HK-THRESHOLD-2024": "2025-01-01",
            },
        )
        md = render_brief_markdown(brief, "HKD", Decimal("1"))
        assert "HK-CIT-RATE-2024" in md
        # These rule IDs are not in any section obligation, so filtered out
        assert "HK-LOSS-RELIEF-2024" not in md
        assert "HK-THRESHOLD-2024" not in md

    def test_empty_as_of_dates_section_omitted(self):
        ob = _obligation(rule_id="HK-CIT-RATE-2024")
        brief = _brief(
            sections=[_section(obligation=ob)],
            as_of_dates={},
        )
        md = render_brief_markdown(brief, "HKD", Decimal("1"))
        assert "Rule As-of Dates" not in md


class TestRenderBriefMarkdownPEDays:
    def test_pe_days_threshold_shows_days_not_currency(self):
        t = ThresholdResult(
            entity_id="LENOVO-HK",
            jurisdiction="HK",
            rule_id="HK-PE-DAYS",
            threshold_name="PE Day Count",
            threshold_value_hkd=Decimal("183"),
            actual_value_hkd=Decimal("185"),
            breached=True,
            as_of_date=_AOD,
            source_citation="OECD Model Convention Art.5",
            unit="days",
        )
        ob = _obligation()
        sec = _section(obligation=ob, thresholds=[t])
        md = render_brief_markdown(_brief(sections=[sec]), "HKD", Decimal("1"))
        assert "185 days" in md
        assert "183 days" in md
        assert "BREACHED" in md
