"""
Module: test_attribution_stub
Layer: test-unit
Purpose: Coverage tests for engine.attribution_stub error paths (missing stub file,
    malformed JSON, unknown flow_id, retrieve_applicable_rules).
Dependencies: json, pathlib, pytest, tributary.engine.attribution_stub
Used by: make test
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tributary.common.errors import AIValidationError
from tributary.engine.attribution_stub import AttributionStub


def _stub_path(tmp_path: Path, data: dict) -> Path:
    """Write stub JSON to a temp file and return the path."""
    p = tmp_path / "attributions_stub.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ===========================================================================
# Error paths
# ===========================================================================


class TestAttributionStubErrors:
    def test_raises_when_file_not_found(self, tmp_path):
        """AIValidationError raised when the stub file does not exist."""
        with pytest.raises(AIValidationError, match="not found"):
            AttributionStub(stub_path=tmp_path / "missing.json")

    def test_raises_on_invalid_json(self, tmp_path):
        """AIValidationError raised when the stub file contains invalid JSON."""
        bad = tmp_path / "bad.json"
        bad.write_text("not-json {{", encoding="utf-8")
        with pytest.raises(AIValidationError, match="Invalid"):
            AttributionStub(stub_path=bad)

    def test_raises_on_missing_flows_key(self, tmp_path):
        """AIValidationError raised when the stub JSON has no 'flows' key."""
        p = _stub_path(tmp_path, {"other_key": {}})
        with pytest.raises(AIValidationError, match="Invalid"):
            AttributionStub(stub_path=p)

    def test_raises_on_unknown_flow_id(self, tmp_path):
        """AIValidationError raised when the requested flow_id is not in the stub."""
        import decimal
        from datetime import date
        from tributary.common.models import FlowContext, ActivityType

        p = _stub_path(tmp_path, {"flows": {}})
        stub = AttributionStub(stub_path=p)
        ctx = FlowContext(
            flow_id="NONEXISTENT-FLOW",
            description="test flow",
            amount_hkd=decimal.Decimal("0"),
            flow_date=date(2025, 1, 1),
            source_entity_id="E1",
            source_jurisdiction="HK",
            counterparty_entity_id="E2",
            counterparty_jurisdiction="DE",
            is_intercompany=True,
            activity_type=ActivityType.REVENUE,
            days_present=0,
            has_agent_authority=False,
            available_jurisdictions=["HK"],
        )
        with pytest.raises(AIValidationError, match="No stub attribution"):
            stub.classify_flow(ctx)


# ===========================================================================
# retrieve_applicable_rules — lines 95-100
# ===========================================================================


class TestRetrieveApplicableRules:
    @pytest.fixture
    def stub(self, tmp_path):
        data = {
            "flows": {
                "T-FLOW": {
                    "nature": "revenue",
                    "confidence": "high",
                    "rule_citations": [],
                    "attribution": {
                        "primary_jurisdiction": "HK",
                        "abstain": False,
                        "claims": [],
                    },
                    "applicable_rules": {
                        "HK": [
                            {
                                "rule_id": "HK-PROF-TAX",
                                "jurisdiction": "HK",
                                "rule_type": "rate",
                                "as_of_date": "2024-01-01",
                                "source_citation": "IRO s.14",
                                "relevance_note": "Profits tax applies to revenue earned in HK.",
                            }
                        ]
                    },
                }
            }
        }
        return AttributionStub(stub_path=_stub_path(tmp_path, data))

    def test_returns_rules_for_known_jurisdiction(self, stub):
        """retrieve_applicable_rules returns rules when jurisdiction matches stub data."""
        from tributary.common.models import FlowNature
        result = stub.retrieve_applicable_rules("T-FLOW", "HK", FlowNature.REVENUE)
        assert len(result.applicable_rules) == 1
        assert result.applicable_rules[0].rule_id == "HK-PROF-TAX"
        assert result.abstain is False

    def test_abstains_for_unknown_jurisdiction(self, stub):
        """retrieve_applicable_rules abstains when no rules exist for the jurisdiction."""
        from tributary.common.models import FlowNature
        result = stub.retrieve_applicable_rules("T-FLOW", "DE", FlowNature.REVENUE)
        assert result.applicable_rules == []
        assert result.abstain is True
