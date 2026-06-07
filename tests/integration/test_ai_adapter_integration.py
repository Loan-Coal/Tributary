"""
Module: test_ai_adapter_integration
Layer: test-integration
Purpose: Integration test wiring AILayerAdapter (wrapping AILayerService + FakeClaudeClient)
    into EngineRunner in place of AttributionStub. Verifies that the adapter seam produces
    structurally equivalent results: same obligation types, same jurisdictions.
    Does NOT assert exact amounts (those are governed by test_engine_golden.py with the stub).
Dependencies: pytest, tributary.ai.adapter, tributary.ai.fake_client, tributary.engine.runner,
    tributary.rules.loader, tests.support.fakes
Used by: make test
"""
from __future__ import annotations

import pytest

from tests.support.fakes import CollectingGraphWriter, FakeGraphReader
from tributary.ai.adapter import AILayerAdapter
from tributary.ai.fake_client import FakeClaudeClient
from tributary.common.models import EngineRunResult, ObligationType
from tributary.engine.attribution_stub import AttributionStub
from tributary.engine.runner import EngineRunner
from tributary.rules.loader import JSONRulePackLoader

_REFERENCE_YEAR = 2025


def _run(ai_impl) -> list[EngineRunResult]:
    reader = FakeGraphReader()
    writer = CollectingGraphWriter()
    loader = JSONRulePackLoader()
    runner = EngineRunner(reader, writer, ai_impl, loader, _REFERENCE_YEAR)
    return runner.run()


@pytest.fixture(scope="module")
def stub_results() -> list[EngineRunResult]:
    """Baseline: golden run with AttributionStub."""
    return _run(AttributionStub())


@pytest.fixture(scope="module")
def adapter_results() -> list[EngineRunResult]:
    """Adapter run: same engine, different AI implementation."""
    loader = JSONRulePackLoader()
    ai = AILayerAdapter(llm_client=FakeClaudeClient(), rule_loader=loader)
    return _run(ai)


class TestAdapterRunProducesResults:
    def test_returns_four_entity_results(self, adapter_results):
        """One result per entity in the golden scenario (HK, DE, FR, US)."""
        assert len(adapter_results) == 4

    def test_all_entities_have_obligations(self, adapter_results):
        """Every entity should have at least a CIT obligation."""
        for result in adapter_results:
            cit = [o for o in result.obligations if o.obligation_type == ObligationType.CIT]
            assert len(cit) >= 1, f"No CIT obligation for {result.entity_id}"

    def test_hk_entity_present(self, adapter_results):
        entity_ids = {r.entity_id for r in adapter_results}
        assert "LENOVO-HK" in entity_ids

    def test_de_entity_present(self, adapter_results):
        entity_ids = {r.entity_id for r in adapter_results}
        assert "LENOVO-DE" in entity_ids

    def test_fr_entity_present(self, adapter_results):
        entity_ids = {r.entity_id for r in adapter_results}
        assert "LENOVO-FR" in entity_ids


class TestAdapterStructurallyMatchesStub:
    def test_same_entity_count(self, stub_results, adapter_results):
        assert len(adapter_results) == len(stub_results)

    def test_same_obligation_types_per_entity(self, stub_results, adapter_results):
        """Each entity should have the same set of obligation types in both runs."""
        stub_by_entity = {r.entity_id: r for r in stub_results}
        for result in adapter_results:
            stub = stub_by_entity[result.entity_id]
            stub_types = {o.obligation_type for o in stub.obligations}
            adapter_types = {o.obligation_type for o in result.obligations}
            assert adapter_types == stub_types, (
                f"{result.entity_id}: obligation types differ\n"
                f"  stub: {stub_types}\n  adapter: {adapter_types}"
            )

    def test_conflict_detected_in_adapter_run(self, adapter_results):
        """The PE Triangle conflict must be detected regardless of AI implementation."""
        all_conflicts = [
            conflict
            for result in adapter_results
            for conflict in result.conflicts
        ]
        assert len(all_conflicts) >= 1, "No cross-border conflict detected with adapter"
