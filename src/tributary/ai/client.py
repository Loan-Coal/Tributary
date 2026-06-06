"""
Module: client
Layer: ai
Purpose: Anthropic Claude client adapter with structured output enforcement.
Dependencies: json, pydantic, anthropic, tributary.common.errors, tributary.common.logging,
              tributary.ai.models, tributary.config.settings
Used by: ai.service
"""
from __future__ import annotations

import json

from pydantic import ValidationError

from tributary.common.errors import AIClientError
from tributary.common.logging import get_logger
from tributary.ai.models import AILayerOutput
from tributary.config import settings

logger = get_logger(__name__)

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover
    Anthropic = None


class ClaudeClient:
    def __init__(self, api_key: str, model: str | None = None, temperature: float = 0.0) -> None:
        """Initialise the Claude client.

        Args:
            api_key: Anthropic API key.
            model: Model ID; defaults to settings.CLAUDE_MODEL.
            temperature: Sampling temperature (0.0 = deterministic).
        Raises:
            AIClientError: If the anthropic library is not installed.
        """
        if Anthropic is None:
            raise AIClientError("Anthropic client library is unavailable")
        self.client = Anthropic(api_key=api_key)
        self.model = model or settings.CLAUDE_MODEL
        self.temperature = temperature

    def generate(self, prompt: str, max_tokens: int = 800) -> AILayerOutput:
        """Call Claude via the messages API and validate the response.

        Args:
            prompt: User-turn prompt text.
            max_tokens: Maximum tokens to generate.
        Returns:
            Validated AILayerOutput from Claude's JSON response.
        Raises:
            AIClientError: On API failure, non-JSON output, or schema mismatch.
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.error("Claude API call failed", exc_info=exc)
            raise AIClientError("Claude API call failed") from exc

        raw_text = self._extract_text(response)
        return self._parse_output(raw_text)

    def _extract_text(self, response: object) -> str:
        """Extract text from the first content block of a messages API response.

        Args:
            response: Anthropic Message object.
        Returns:
            Raw text string from the first content block.
        Raises:
            AIClientError: If content is missing or empty.
        """
        content = getattr(response, "content", None)
        if not content:
            logger.error("Claude response has no content blocks", extra={"response": response})
            raise AIClientError("Claude returned an unexpected response format")
        return content[0].text

    def _parse_output(self, raw_text: str) -> AILayerOutput:
        """Parse and validate JSON text as AILayerOutput.

        Args:
            raw_text: Raw JSON string from Claude.
        Returns:
            Validated AILayerOutput.
        Raises:
            AIClientError: On JSON decode failure or Pydantic validation failure.
        """
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.error("Claude response did not contain valid JSON", exc_info=exc)
            raise AIClientError("Claude returned non-JSON output") from exc

        try:
            return AILayerOutput.model_validate(payload)
        except ValidationError as exc:
            logger.error("Claude output validation failed", exc_info=exc)
            raise AIClientError("Claude returned invalid structured output") from exc
