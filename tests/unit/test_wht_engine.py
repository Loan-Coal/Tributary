"""
Module: test_wht_engine
Layer: test-unit
Purpose: Regression tests for engine.wht_engine — specifically the W6c.2 move of
    EU_MEMBER_JURISDICTIONS out of engine/ into common/jurisdictions.py (ISSUE-011).
    Also covers _both_eu functional correctness after the refactor.
Dependencies: inspect, decimal, pytest, tributary.common, tributary.engine.wht_engine,
    tributary.common.jurisdictions
Used by: make test
"""
from __future__ import annotations

import inspect
from decimal import Decimal

import pytest

import tributary.engine.wht_engine as wht_engine_module
from tributary.common.models import ActivityType, JurisdictionCode
from tributary.engine.aggregator import OutboundPayment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _payment(payer_jur: JurisdictionCode, payee_jur: JurisdictionCode) -> OutboundPayment:
    return OutboundPayment(
        flow_id="T-TEST",
        activity=ActivityType.DIVIDEND,
        gross_hkd=Decimal("100000"),
        payer_entity_id="PAYER-001",
        payer_jurisdiction=payer_jur,
        payee_entity_id="PAYEE-001",
        payee_jurisdiction=payee_jur,
    )


# ---------------------------------------------------------------------------
# W6c.2 regression: EU_MEMBER_JURISDICTIONS must live in common/, not engine/
# ---------------------------------------------------------------------------

def test_eu_member_jurisdictions_importable_from_common_jurisdictions() -> None:
    """EU_MEMBER_JURISDICTIONS must be importable from tributary.common.jurisdictions (ISSUE-011)."""
    from tributary.common.jurisdictions import EU_MEMBER_JURISDICTIONS  # noqa: PLC0415

    assert isinstance(EU_MEMBER_JURISDICTIONS, frozenset)
    assert len(EU_MEMBER_JURISDICTIONS) >= 27


def test_eu_member_jurisdictions_contains_expected_members() -> None:
    """Known EU members must be in the constant; non-EU jurisdictions must not."""
    from tributary.common.jurisdictions import EU_MEMBER_JURISDICTIONS  # noqa: PLC0415

    assert "FR" in EU_MEMBER_JURISDICTIONS
    assert "DE" in EU_MEMBER_JURISDICTIONS
    assert "AT" in EU_MEMBER_JURISDICTIONS
    # Non-EU jurisdictions must not appear
    assert "HK" not in EU_MEMBER_JURISDICTIONS
    assert "US" not in EU_MEMBER_JURISDICTIONS
    assert "SG" not in EU_MEMBER_JURISDICTIONS


def test_wht_engine_does_not_define_eu_frozenset_inline() -> None:
    """wht_engine.py must not contain a frozenset literal for EU member states (DEC-006 / ISSUE-011).

    This guards against the EU set being re-introduced as a hardcoded literal in the engine layer.
    """
    source = inspect.getsource(wht_engine_module)
    # The constant definition must NOT appear inline in the engine module
    assert "EU_MEMBER_JURISDICTIONS: frozenset" not in source
    assert 'frozenset({' not in source


# ---------------------------------------------------------------------------
# Functional regression: _both_eu still works after the refactor
# ---------------------------------------------------------------------------

def test_both_eu_true_for_two_eu_members() -> None:
    """_both_eu must return True when both payer and payee are EU member states."""
    from tributary.engine.wht_engine import _both_eu  # noqa: PLC0415

    assert _both_eu(_payment("DE", "FR")) is True
    assert _both_eu(_payment("FR", "NL")) is True


def test_both_eu_false_when_payer_not_eu() -> None:
    """_both_eu must return False when the payer is outside the EU."""
    from tributary.engine.wht_engine import _both_eu  # noqa: PLC0415

    assert _both_eu(_payment("HK", "DE")) is False


def test_both_eu_false_when_payee_not_eu() -> None:
    """_both_eu must return False when the payee is outside the EU."""
    from tributary.engine.wht_engine import _both_eu  # noqa: PLC0415

    assert _both_eu(_payment("DE", "HK")) is False


def test_both_eu_false_for_two_non_eu_members() -> None:
    """_both_eu must return False when neither party is in the EU."""
    from tributary.engine.wht_engine import _both_eu  # noqa: PLC0415

    assert _both_eu(_payment("HK", "SG")) is False
