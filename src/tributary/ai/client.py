"""
Module: client
Layer: ai
Purpose: Anthropic Claude client adapter with structured output enforcement.
Dependencies: json, pydantic, anthropic, tributary.common.errors, tributary.common.logging, tributary.ai.models
Used by: ai.service
"""
from __future__ import annotations

import json

from pydantic import ValidationError

from tributary.common.errors import AIClientError
from tributary.common.logging import get_logger
from tributary.ai.models import AILayerOutput

logger = get_logger(__name__)

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover
    Anthropic = None


class ClaudeClient:
    def __init__(self, api_key: str, model: str = "claude-3.0", temperature: float = 0.0) -> None:
        if Anthropic is None:
            raise AIClientError("Anthropic client library is unavailable")
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.temperature = temperature

    def generate(self, prompt: str, max_tokens: int = 800) -> AILayerOutput:
        """Call Claude and validate the response as AILayerOutput."""
        try:
            response = self.client.completions.create(
                model=self.model,
                prompt=prompt,
                max_tokens_to_sample=max_tokens,
                temperature=self.temperature,
            )
        except Exception as exc:
            logger.error("Claude API call failed", exc_info=exc)
            raise AIClientError("Claude API call failed") from exc

        raw_text = getattr(response, "completion", None)
        if raw_text is None:
            logger.error("Claude response missing completion field", extra={"response": response})
            raise AIClientError("Claude returned an unexpected response format")

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.error("Claude response did not contain valid JSON", exc_info=exc, extra={"raw_text": raw_text})
            raise AIClientError("Claude returned non-JSON output") from exc

        try:
            return AILayerOutput.model_validate(payload)
        except ValidationError as exc:
            logger.error("Claude output validation failed", exc_info=exc, extra={"payload": payload})
            raise AIClientError("Claude returned invalid structured output") from exc
