"""
Module: test_claude_client
Layer: ai
Purpose: Unit tests for ClaudeClient — messages API, error paths.
Dependencies: unittest.mock, pytest, tributary.ai.client, tributary.common.errors
Used by: pytest, make test
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tributary.ai.client import ClaudeClient
from tributary.common.errors import AIClientError

_VALID_OUTPUT = {
    "transaction_id": "T001",
    "flow_classification": "REVENUE",
    "candidate_jurisdictions": ["HK"],
    "retrieved_rules": [
        {
            "rule_id": "HK-CIT-RATE",
            "source_citation": "IRO Cap.112 s.14",
            "as_of_date": "2024-01-01",
            "confidence": 0.95,
            "reasoning": "Standard profits tax rate applies.",
        }
    ],
    "evidence_requests": [],
    "narrative_template": "Tax of {{engine:tax_amount}} is due.",
    "needs_human_review": False,
    "abstain": False,
}


def _make_mock_response(text: str) -> MagicMock:
    """Build a minimal Anthropic SDK Message mock."""
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


@patch("tributary.ai.client.Anthropic")
def test_generate_happy_path(mock_anthropic_cls: MagicMock) -> None:
    """ClaudeClient.generate() returns AILayerOutput on valid JSON response."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _make_mock_response(
        json.dumps(_VALID_OUTPUT)
    )

    client = ClaudeClient(api_key="test-key")
    result = client.generate("some prompt")

    assert result.transaction_id == "T001"
    assert result.flow_classification == "REVENUE"
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["messages"] == [{"role": "user", "content": "some prompt"}]
    assert "model" in call_kwargs


@patch("tributary.ai.client.Anthropic")
def test_generate_api_failure_raises(mock_anthropic_cls: MagicMock) -> None:
    """ClaudeClient.generate() wraps API exceptions as AIClientError."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.side_effect = RuntimeError("network error")

    client = ClaudeClient(api_key="test-key")
    with pytest.raises(AIClientError, match="Claude API call failed"):
        client.generate("some prompt")


@patch("tributary.ai.client.Anthropic")
def test_generate_invalid_json_raises(mock_anthropic_cls: MagicMock) -> None:
    """ClaudeClient.generate() raises AIClientError on non-JSON response."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _make_mock_response("not valid json {")

    client = ClaudeClient(api_key="test-key")
    with pytest.raises(AIClientError, match="non-JSON"):
        client.generate("some prompt")


@patch("tributary.ai.client.Anthropic")
def test_generate_schema_mismatch_raises(mock_anthropic_cls: MagicMock) -> None:
    """ClaudeClient.generate() raises AIClientError when response fails Pydantic validation."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _make_mock_response(
        json.dumps({"unexpected": "fields"})
    )

    client = ClaudeClient(api_key="test-key")
    with pytest.raises(AIClientError, match="invalid structured output"):
        client.generate("some prompt")
