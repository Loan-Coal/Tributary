"""
Module: test_models
Layer: common
Purpose: Unit tests for canonical Pydantic v2 data models in tributary.common.
Dependencies: pydantic, tributary.common.models
Used by: pytest test suite
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from tributary.common.models import (
    AccountRecord,
    ActivityType,
    ApplicableRule,
    ConfidenceLevel,
    ComputationStep,
    ConflictFlag,
    ConflictType,
    CounterpartyRecord,
    DeadlineResult,
    EngineRunResult,
    EntityRecord,
    EntityType,
    FiscalCalendar,
    FiscalPeriod,
    FlowAttribution,
    FlowClassification,
    FlowContext,
    FlowNature,
    GroupReliefMechanism,
    GroupReliefOpportunity,
    JurisdictionClaim,
    LossCarryforwardRecord,
    ObligationResult,
    ObligationType,
    OwnershipRecord,
    PresenceActivity,
    PresenceRecord,
    PriorPeriodLoss,
    ReliefMechanism,
    RuleCitation,
    RuleRetrievalResult,
    ThresholdResult,
    TransactionRecord,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fiscal_period(jurisdiction: str = "HK") -> FiscalPeriod:
    """Return a minimal FiscalPeriod for reuse across tests."""
    return FiscalPeriod(
        jurisdiction=jurisdiction,
        start_date=date(2024, 4, 1),
        end_date=date(2025, 3, 31),
    )


def _make_rule_citation(jurisdiction: str = "HK") -> RuleCitation:
    """Return a minimal RuleCitation for reuse across tests."""
    return RuleCitation(
        rule_id="HK-CIT-001",
        jurisdiction=jurisdiction,
        as_of_date=date(2024, 1, 1),
        source_citation="IRO s.14",
    )


def _make_computation_step() -> ComputationStep:
    """Return a minimal ComputationStep for reuse across tests."""
    return ComputationStep(
        step_name="apply_rate",
        input_value_hkd=Decimal("1000000.00"),
        rule_id="HK-CIT-001",
        rule_as_of_date=date(2024, 1, 1),
        result_value_hkd=Decimal("165000.00"),
        note=None,
    )


# ---------------------------------------------------------------------------
# 1. JurisdictionCode validation on EntityRecord
# ---------------------------------------------------------------------------

class TestJurisdictionCode:
    """Tests for the JurisdictionCode annotated type via EntityRecord."""

    def test_jurisdiction_code_valid(self) -> None:
        """EntityRecord with two-letter uppercase jurisdiction codes validates OK."""
        record = EntityRecord(
            entity_id="MERID-HK",
            name="Meridian HK",
            entity_type=EntityType.HOLDCO,
            incorporation_jurisdiction="HK",
            resident_jurisdiction="HK",
            is_group_member=True,
        )
        assert record.incorporation_jurisdiction == "HK"
        assert record.resident_jurisdiction == "HK"

    def test_jurisdiction_code_lowercase_invalid(self) -> None:
        """EntityRecord with lowercase jurisdiction code raises ValidationError."""
        with pytest.raises(ValidationError):
            EntityRecord(
                entity_id="MERID-HK",
                name="Meridian HK",
                entity_type=EntityType.HOLDCO,
                incorporation_jurisdiction="hk",
                resident_jurisdiction="HK",
                is_group_member=True,
            )

    def test_jurisdiction_code_three_letter_invalid(self) -> None:
        """EntityRecord with three-letter jurisdiction code raises ValidationError."""
        with pytest.raises(ValidationError):
            EntityRecord(
                entity_id="MERID-HK",
                name="Meridian HK",
                entity_type=EntityType.HOLDCO,
                incorporation_jurisdiction="HKG",
                resident_jurisdiction="HK",
                is_group_member=True,
            )

    def test_jurisdiction_code_empty_invalid(self) -> None:
        """EntityRecord with empty jurisdiction code raises ValidationError."""
        with pytest.raises(ValidationError):
            EntityRecord(
                entity_id="MERID-HK",
                name="Meridian HK",
                entity_type=EntityType.HOLDCO,
                incorporation_jurisdiction="",
                resident_jurisdiction="HK",
                is_group_member=True,
            )


# ---------------------------------------------------------------------------
# 2. TransactionRecord
# ---------------------------------------------------------------------------

class TestTransactionRecord:
    """Tests for TransactionRecord construction and validation."""

    def test_transaction_record_valid(self) -> None:
        """TransactionRecord with all required fields constructs correctly."""
        record = TransactionRecord(
            transaction_id="T001",
            transaction_date=date(2024, 7, 1),
            description="Royalty payment DE→HK",
            amount_hkd=Decimal("500000.00"),
            source_amount=Decimal("500000.00"),
            fx_rate=Decimal("1.0"),
            fx_date=date(2024, 7, 1),
            source_currency="HKD",
            source_entity_id="MERID-DE",
            counterparty_entity_id="MERID-HK",
            counterparty_jurisdiction="HK",
            is_intercompany=True,
            activity_type="royalty",
            days_present=None,
            has_agent_authority=False,
        )
        assert record.transaction_id == "T001"
        assert record.amount_hkd == Decimal("500000.00")
        assert record.activity_type is ActivityType.ROYALTY
        assert record.is_intercompany is True

    def test_transaction_record_optional_none_fields(self) -> None:
        """TransactionRecord with optional None fields is valid."""
        record = TransactionRecord(
            transaction_id="T002",
            transaction_date=date(2024, 8, 1),
            description="External revenue",
            amount_hkd=Decimal("200000.00"),
            source_amount=Decimal("23529.41"),
            fx_rate=Decimal("8.50"),
            fx_date=date(2024, 8, 1),
            source_currency="EUR",
            source_entity_id="MERID-HK",
            counterparty_entity_id=None,
            counterparty_jurisdiction=None,
            is_intercompany=False,
            activity_type=None,
            days_present=None,
            has_agent_authority=False,
        )
        assert record.counterparty_entity_id is None
        assert record.counterparty_jurisdiction is None
        assert record.activity_type is None

    def test_transaction_record_invalid_activity_type(self) -> None:
        """TransactionRecord rejects an unknown activity_type (typo/wrong case)."""
        with pytest.raises(ValidationError):
            TransactionRecord(
                transaction_id="T003",
                transaction_date=date(2024, 8, 1),
                description="Bad activity",
                amount_hkd=Decimal("100.00"),
                source_amount=Decimal("100.00"),
                fx_rate=Decimal("1.0"),
                fx_date=date(2024, 8, 1),
                source_currency="HKD",
                source_entity_id="MERID-HK",
                counterparty_entity_id=None,
                counterparty_jurisdiction=None,
                is_intercompany=False,
                activity_type="Royalty",  # wrong case — not a valid ActivityType
                days_present=None,
                has_agent_authority=False,
            )


# ---------------------------------------------------------------------------
# 3. PresenceRecord
# ---------------------------------------------------------------------------

class TestPresenceRecord:
    """Tests for PresenceRecord used in PE scenario."""

    def test_presence_record_valid(self) -> None:
        """PresenceRecord for PE scenario (185 days) constructs correctly."""
        record = PresenceRecord(
            presence_id="PRES-001",
            entity_id="MERID-DE",
            jurisdiction="FR",
            period_start=date(2024, 4, 1),
            period_end=date(2024, 10, 2),
            total_days_present=185,
            activity_type="service_delivery",
            has_agent_authority=False,
            has_fixed_place=False,
        )
        assert record.total_days_present == 185
        assert record.jurisdiction == "FR"

    def test_presence_record_invalid_jurisdiction(self) -> None:
        """PresenceRecord with invalid jurisdiction raises ValidationError."""
        with pytest.raises(ValidationError):
            PresenceRecord(
                presence_id="PRES-001",
                entity_id="MERID-DE",
                jurisdiction="fra",
                period_start=date(2024, 4, 1),
                period_end=date(2024, 10, 2),
                total_days_present=185,
                activity_type="service_delivery",
                has_agent_authority=False,
                has_fixed_place=False,
            )


# ---------------------------------------------------------------------------
# 4. FiscalPeriod
# ---------------------------------------------------------------------------

class TestFiscalPeriod:
    """Tests for FiscalPeriod construction."""

    def test_fiscal_period_valid(self) -> None:
        """FiscalPeriod with valid jurisdiction and dates constructs correctly."""
        period = _make_fiscal_period("DE")
        assert period.jurisdiction == "DE"
        assert period.start_date == date(2024, 4, 1)
        assert period.end_date == date(2025, 3, 31)

    def test_fiscal_calendar_valid(self) -> None:
        """FiscalCalendar with valid fields constructs correctly."""
        calendar = FiscalCalendar(
            jurisdiction="HK",
            period_start_month=4,
            period_start_day=1,
        )
        assert calendar.period_start_month == 4
        assert calendar.period_start_day == 1

    def test_fiscal_calendar_month_out_of_range(self) -> None:
        """FiscalCalendar rejects period_start_month outside 1–12."""
        with pytest.raises(ValidationError):
            FiscalCalendar(jurisdiction="DE", period_start_month=13, period_start_day=1)

    def test_fiscal_calendar_day_out_of_range(self) -> None:
        """FiscalCalendar rejects period_start_day outside 1–31."""
        with pytest.raises(ValidationError):
            FiscalCalendar(jurisdiction="FR", period_start_month=1, period_start_day=32)


# ---------------------------------------------------------------------------
# 5. EngineRunResult with empty lists
# ---------------------------------------------------------------------------

class TestEngineRunResult:
    """Tests for EngineRunResult model."""

    def test_engine_run_result_empty(self) -> None:
        """EngineRunResult with all empty lists validates OK."""
        result = EngineRunResult(
            run_id="run-001",
            entity_id="MERID-HK",
            fiscal_period=_make_fiscal_period("HK"),
            base_currency="HKD",
            obligations=[],
            threshold_checks=[],
            deadlines=[],
            loss_carryforward_applied=[],
            conflicts=[],
            has_unresolved_items=False,
        )
        assert result.run_id == "run-001"
        assert result.obligations == []
        assert result.has_unresolved_items is False


# ---------------------------------------------------------------------------
# 6. ConfidenceLevel enum
# ---------------------------------------------------------------------------

class TestConfidenceLevel:
    """Tests for ConfidenceLevel enum completeness."""

    def test_confidence_level_enum_all_values(self) -> None:
        """All four ConfidenceLevel values are accessible and have expected string values."""
        assert ConfidenceLevel.HIGH == "HIGH"
        assert ConfidenceLevel.MEDIUM == "MEDIUM"
        assert ConfidenceLevel.LOW == "LOW"
        assert ConfidenceLevel.ABSTAIN == "ABSTAIN"

    def test_confidence_level_count(self) -> None:
        """ConfidenceLevel has exactly four members."""
        assert len(list(ConfidenceLevel)) == 4


# ---------------------------------------------------------------------------
# 7. FlowNature enum
# ---------------------------------------------------------------------------

class TestFlowNature:
    """Tests for FlowNature enum completeness."""

    def test_flow_nature_enum_all_values(self) -> None:
        """All FlowNature values are accessible."""
        expected = {
            "revenue", "expense", "intercompany", "capital", "loan",
            "royalty", "dividend", "interest", "management_fee", "other",
        }
        actual = {fn.value for fn in FlowNature}
        assert actual == expected

    def test_flow_nature_royalty(self) -> None:
        """FlowNature.ROYALTY maps to 'royalty' matching DEC-007 activity_type values."""
        assert FlowNature.ROYALTY == "royalty"


# ---------------------------------------------------------------------------
# 8. PriorPeriodLoss
# ---------------------------------------------------------------------------

class TestPriorPeriodLoss:
    """Tests for PriorPeriodLoss (DEC-008: loss carryforward in scope)."""

    def test_prior_period_loss_valid(self) -> None:
        """PriorPeriodLoss with valid Decimal amounts constructs correctly."""
        loss = PriorPeriodLoss(
            loss_id="LOSS-001",
            entity_id="MERID-DE",
            jurisdiction="DE",
            loss_period_start=date(2024, 1, 1),
            loss_period_end=date(2024, 12, 31),
            original_loss_hkd=Decimal("800000.00"),
            remaining_loss_hkd=Decimal("800000.00"),
            created_at=date(2025, 1, 15),
        )
        assert loss.original_loss_hkd == Decimal("800000.00")
        assert loss.remaining_loss_hkd == Decimal("800000.00")


# ---------------------------------------------------------------------------
# 9. ObligationResult with ComputationStep
# ---------------------------------------------------------------------------

class TestObligationResult:
    """Tests for ObligationResult including nested ComputationStep."""

    def test_obligation_result_valid(self) -> None:
        """ObligationResult with a ComputationStep constructs correctly."""
        step = _make_computation_step()
        result = ObligationResult(
            obligation_id="OBL-HK-001",
            entity_id="MERID-HK",
            jurisdiction="HK",
            obligation_type=ObligationType.CIT,
            fiscal_period=_make_fiscal_period("HK"),
            taxable_base_hkd=Decimal("1000000.00"),
            rate=Decimal("0.165"),
            gross_amount_hkd=Decimal("165000.00"),
            treaty_relief_hkd=Decimal("0.00"),
            net_amount_hkd=Decimal("165000.00"),
            rule_id="HK-CIT-001",
            as_of_date=date(2024, 1, 1),
            source_citation="IRO s.14",
            treaty_citation=None,
            source_flow_ids=["T001", "T002"],
            computation_trace=[step],
            needs_review=False,
        )
        assert result.obligation_type == ObligationType.CIT
        assert result.net_amount_hkd == Decimal("165000.00")
        assert len(result.computation_trace) == 1
        assert result.computation_trace[0].step_name == "apply_rate"

    def test_obligation_result_missing_required_field(self) -> None:
        """ObligationResult missing a required field raises ValidationError."""
        with pytest.raises(ValidationError):
            ObligationResult(
                obligation_id="OBL-HK-001",
                entity_id="MERID-HK",
                # jurisdiction missing
                obligation_type=ObligationType.CIT,
                fiscal_period=_make_fiscal_period("HK"),
                taxable_base_hkd=Decimal("1000000.00"),
                rate=Decimal("0.165"),
                gross_amount_hkd=Decimal("165000.00"),
                treaty_relief_hkd=Decimal("0.00"),
                net_amount_hkd=Decimal("165000.00"),
                rule_id="HK-CIT-001",
                as_of_date=date(2024, 1, 1),
                source_citation="IRO s.14",
                treaty_citation=None,
                source_flow_ids=[],
                computation_trace=[],
                needs_review=False,
            )


# ---------------------------------------------------------------------------
# 10. Additional model smoke tests
# ---------------------------------------------------------------------------

class TestAdditionalModels:
    """Smoke tests for remaining common models."""

    def test_ownership_record_valid(self) -> None:
        """OwnershipRecord constructs with valid Decimal ownership."""
        rec = OwnershipRecord(
            owner_entity_id="MERID-HK",
            owned_entity_id="MERID-DE",
            ownership_pct=Decimal("100.00"),
            effective_from=date(2020, 1, 1),
            effective_to=None,
        )
        assert rec.ownership_pct == Decimal("100.00")

    def test_account_record_valid(self) -> None:
        """AccountRecord constructs correctly."""
        acc = AccountRecord(
            account_id="ACC-001",
            entity_id="MERID-HK",
            account_name="Revenue",
            account_type="income",
        )
        assert acc.account_id == "ACC-001"

    def test_counterparty_record_valid(self) -> None:
        """CounterpartyRecord constructs with optional jurisdiction None."""
        cp = CounterpartyRecord(
            counterparty_id="CP-001",
            name="External Client",
            jurisdiction=None,
            is_related_party=False,
        )
        assert cp.jurisdiction is None

    def test_counterparty_record_with_jurisdiction(self) -> None:
        """CounterpartyRecord constructs with two-letter jurisdiction."""
        cp = CounterpartyRecord(
            counterparty_id="CP-002",
            name="Meridian DE",
            jurisdiction="DE",
            is_related_party=True,
        )
        assert cp.jurisdiction == "DE"

    def test_threshold_result_valid(self) -> None:
        """ThresholdResult constructs correctly."""
        result = ThresholdResult(
            entity_id="MERID-DE",
            jurisdiction="DE",
            rule_id="DE-WHT-001",
            threshold_name="Zinsschranke",
            threshold_value_hkd=Decimal("96000.00"),
            actual_value_hkd=Decimal("320000.00"),
            breached=True,
            as_of_date=date(2024, 1, 1),
            source_citation="KStG §8a",
        )
        assert result.breached is True

    def test_deadline_result_valid(self) -> None:
        """DeadlineResult constructs correctly."""
        result = DeadlineResult(
            entity_id="MERID-HK",
            jurisdiction="HK",
            obligation_type=ObligationType.CIT,
            filing_deadline=date(2025, 11, 30),
            payment_deadline=date(2025, 11, 30),
            rule_id="HK-CIT-DEADLINE-001",
            as_of_date=date(2024, 1, 1),
            source_citation="IRO s.51",
            fiscal_period=_make_fiscal_period("HK"),
        )
        assert result.filing_deadline == date(2025, 11, 30)

    def test_loss_carryforward_record_valid(self) -> None:
        """LossCarryforwardRecord constructs correctly."""
        record = LossCarryforwardRecord(
            entity_id="MERID-DE",
            jurisdiction="DE",
            loss_period=_make_fiscal_period("DE"),
            original_loss_hkd=Decimal("800000.00"),
            used_this_period_hkd=Decimal("480000.00"),
            remaining_loss_hkd=Decimal("320000.00"),
            limitation_applied=True,
            limitation_rule_id="DE-LOSS-CAP-001",
        )
        assert record.limitation_applied is True
        assert record.remaining_loss_hkd == Decimal("320000.00")

    def test_flow_context_valid(self) -> None:
        """FlowContext constructs correctly (DEC-010 AI input model)."""
        ctx = FlowContext(
            flow_id="T001",
            description="Royalty HK→DE",
            amount_hkd=Decimal("500000.00"),
            flow_date=date(2024, 7, 1),
            source_entity_id="MERID-HK",
            source_jurisdiction="HK",
            counterparty_entity_id="MERID-DE",
            counterparty_jurisdiction="DE",
            is_intercompany=True,
            activity_type="royalty",
            days_present=None,
            has_agent_authority=False,
            available_jurisdictions=["HK", "DE"],
        )
        assert ctx.flow_id == "T001"
        assert "HK" in ctx.available_jurisdictions

    def test_flow_classification_no_amounts(self) -> None:
        """FlowClassification contains no amount fields (DEC-002: AI emits no figures)."""
        fc = FlowClassification(
            flow_id="T001",
            nature=FlowNature.ROYALTY,
            confidence=ConfidenceLevel.HIGH,
            rule_citations=[_make_rule_citation("HK")],
            abstain_reason=None,
        )
        # Verify the model has no numeric amount fields
        assert not hasattr(fc, "amount_hkd")
        assert not hasattr(fc, "rate")
        assert fc.nature == FlowNature.ROYALTY

    def test_flow_attribution_abstain(self) -> None:
        """FlowAttribution with abstain=True and no primary jurisdiction is valid."""
        attr = FlowAttribution(
            flow_id="T001",
            primary_jurisdiction=None,
            claims=[],
            abstain=True,
            abstain_reason="Insufficient evidence to attribute jurisdiction.",
        )
        assert attr.abstain is True
        assert attr.primary_jurisdiction is None

    def test_jurisdiction_claim_valid(self) -> None:
        """JurisdictionClaim constructs with a rule citation."""
        claim = JurisdictionClaim(
            jurisdiction="FR",
            confidence=ConfidenceLevel.HIGH,
            claim_basis="Service PE threshold exceeded (DTA Art.5)",
            rationale_citation=_make_rule_citation("FR"),
        )
        assert claim.jurisdiction == "FR"

    def test_applicable_rule_valid(self) -> None:
        """ApplicableRule constructs correctly."""
        rule = ApplicableRule(
            rule_id="DE-WHT-001",
            jurisdiction="DE",
            rule_type="rate",
            as_of_date=date(2024, 1, 1),
            source_citation="EStG §50a",
            relevance_note="Applies to royalty payments from DE source.",
        )
        assert rule.rule_type == "rate"

    def test_rule_retrieval_result_valid(self) -> None:
        """RuleRetrievalResult constructs correctly."""
        result = RuleRetrievalResult(
            flow_id="T001",
            jurisdiction="HK",
            applicable_rules=[],
            abstain=False,
            abstain_reason=None,
        )
        assert result.abstain is False


# ---------------------------------------------------------------------------
# 11. ConflictFlag (Wave 6 — PE Triangle, exemption method)
# ---------------------------------------------------------------------------

class TestConflictFlag:
    """Tests for the typed ConflictFlag model (DEC-017)."""

    def test_conflict_flag_exemption_valid(self) -> None:
        """ConflictFlag for the PE Triangle (exemption method) constructs correctly."""
        flag = ConflictFlag(
            conflict_id="PE-TRIANGLE-2025",
            conflict_type=ConflictType.SERVICE_PE_DOUBLE_TAX,
            trigger_flow_ids=["T003"],
            entities=["MERID-DE", "MERID-FR"],
            jurisdictions=["DE", "FR"],
            attributed_base_hkd=Decimal("1023750.00"),
            residence_jurisdiction="DE",
            pe_jurisdiction="FR",
            pe_tax_hkd=Decimal("255938.00"),
            residence_tax_before_relief_hkd=Decimal("162008.44"),
            relief_mechanism=ReliefMechanism.EXEMPTION,
            relieved_amount_hkd=Decimal("162008.44"),
            residual_double_tax_hkd=Decimal("0.00"),
            treaty_rule_id="DE-FR-DTA-ART23",
            treaty_as_of_date=date(2017, 1, 1),
            treaty_source_citation="DE-FR DTA Art.23 (OECD 2017)",
            credit_method_note="Credit method would cap relief at HKD 162,008.",
            needs_review=False,
        )
        assert flag.conflict_type is ConflictType.SERVICE_PE_DOUBLE_TAX
        assert flag.relief_mechanism is ReliefMechanism.EXEMPTION
        assert flag.residual_double_tax_hkd == Decimal("0.00")

    def test_conflict_flag_invalid_jurisdiction(self) -> None:
        """ConflictFlag rejects a malformed jurisdiction code."""
        with pytest.raises(ValidationError):
            ConflictFlag(
                conflict_id="X",
                conflict_type=ConflictType.SERVICE_PE_DOUBLE_TAX,
                trigger_flow_ids=["T003"],
                entities=["MERID-DE"],
                jurisdictions=["DEU"],  # invalid — three letters
                attributed_base_hkd=Decimal("1.00"),
                residence_jurisdiction="DE",
                pe_jurisdiction="FR",
                pe_tax_hkd=Decimal("0.00"),
                residence_tax_before_relief_hkd=Decimal("0.00"),
                relief_mechanism=ReliefMechanism.EXEMPTION,
                relieved_amount_hkd=Decimal("0.00"),
                residual_double_tax_hkd=Decimal("0.00"),
                treaty_rule_id="X",
                treaty_as_of_date=date(2017, 1, 1),
                treaty_source_citation="X",
                credit_method_note=None,
                needs_review=False,
            )


# ---------------------------------------------------------------------------
# 12. GroupReliefOpportunity (Wave 6b)
# ---------------------------------------------------------------------------

def _make_group_relief_opportunity() -> GroupReliefOpportunity:
    """Return a minimal valid GroupReliefOpportunity for reuse."""
    return GroupReliefOpportunity(
        opportunity_id="GRO-DE-FR-2025",
        income_entity_id="MERID-DE",
        loss_entity_id="MERID-FR",
        income_jurisdiction="DE",
        loss_jurisdiction="FR",
        available_income_hkd=Decimal("500000.00"),
        unused_loss_hkd=Decimal("300000.00"),
        relief_mechanism=GroupReliefMechanism.ORGANSCHAFT,
        applicable_rule_id="DE-GROUP-RELIEF-001",
        as_of_date=date(2024, 1, 1),
        source_citation="KStG §14-19 (Organschaft)",
        conditions_summary="Profit and loss transfer agreement required.",
    )


class TestGroupReliefOpportunity:
    """Tests for the GroupReliefOpportunity model (W6b.1)."""

    def test_valid_instantiation(self) -> None:
        """GroupReliefOpportunity constructs correctly with all required fields."""
        opp = _make_group_relief_opportunity()
        assert opp.opportunity_id == "GRO-DE-FR-2025"
        assert opp.income_entity_id == "MERID-DE"
        assert opp.loss_entity_id == "MERID-FR"
        assert opp.available_income_hkd == Decimal("500000.00")
        assert opp.unused_loss_hkd == Decimal("300000.00")
        assert opp.relief_mechanism == GroupReliefMechanism.ORGANSCHAFT

    def test_needs_review_defaults_true(self) -> None:
        """needs_review defaults to True — always requires professional sign-off."""
        opp = _make_group_relief_opportunity()
        assert opp.needs_review is True

    def test_all_mechanism_values_valid(self) -> None:
        """All GroupReliefMechanism enum values are accessible."""
        assert GroupReliefMechanism.GROUP_RELIEF.value == "group_relief"
        assert GroupReliefMechanism.ORGANSCHAFT.value == "organschaft"
        assert GroupReliefMechanism.INTEGRATION_FISCALE.value == "integration_fiscale"
        assert GroupReliefMechanism.TRANSFER_PRICING_NOTE.value == "transfer_pricing_note"

    def test_missing_required_field_raises(self) -> None:
        """GroupReliefOpportunity missing a required field raises ValidationError."""
        with pytest.raises(ValidationError):
            GroupReliefOpportunity(
                opportunity_id="GRO-001",
                # income_entity_id missing
                loss_entity_id="E2",
                income_jurisdiction="DE",
                loss_jurisdiction="FR",
                available_income_hkd=Decimal("100.00"),
                unused_loss_hkd=Decimal("50.00"),
                relief_mechanism=GroupReliefMechanism.GROUP_RELIEF,
                applicable_rule_id="DE-GR-001",
                as_of_date=date(2024, 1, 1),
                source_citation="KStG",
                conditions_summary="Check.",
            )


class TestEngineRunResultGroupRelief:
    """Tests for the group_relief_opportunities field on EngineRunResult (W6b.2)."""

    def test_group_relief_opportunities_defaults_empty(self) -> None:
        """EngineRunResult.group_relief_opportunities defaults to empty list."""
        result = EngineRunResult(
            run_id="run-001",
            entity_id="MERID-HK",
            fiscal_period=_make_fiscal_period("HK"),
            base_currency="HKD",
            obligations=[],
            threshold_checks=[],
            deadlines=[],
            loss_carryforward_applied=[],
            conflicts=[],
            has_unresolved_items=False,
        )
        assert result.group_relief_opportunities == []

    def test_group_relief_opportunities_populated(self) -> None:
        """EngineRunResult accepts a list of GroupReliefOpportunity objects."""
        opp = _make_group_relief_opportunity()
        result = EngineRunResult(
            run_id="run-002",
            entity_id="MERID-DE",
            fiscal_period=_make_fiscal_period("DE"),
            base_currency="HKD",
            obligations=[],
            threshold_checks=[],
            deadlines=[],
            loss_carryforward_applied=[],
            conflicts=[],
            has_unresolved_items=False,
            group_relief_opportunities=[opp],
        )
        assert len(result.group_relief_opportunities) == 1
        assert result.group_relief_opportunities[0].opportunity_id == "GRO-DE-FR-2025"
