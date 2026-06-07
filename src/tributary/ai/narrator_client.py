"""
Module: narrator_client
Layer: ai
Purpose: Anthropic Claude client that generates free-text prose narratives for filing
    briefs. Returns plain strings, not structured AILayerOutput. Implements
    NarratorClientProtocol.
Dependencies: anthropic, tributary.common.errors, tributary.common.logging,
    tributary.common.protocols_ai, tributary.config.settings
Used by: engine.cli (wired into BriefNarrator)
"""
from __future__ import annotations

from tributary.common.errors import AIClientError
from tributary.common.logging import get_logger
from tributary.config import settings

logger = get_logger(__name__)

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover
    Anthropic = None

_MAX_TOKENS = 512


class ClaudeNarratorClient:
    """Claude client for brief prose narrative generation.

    Returns plain strings, not structured JSON. Suitable for injection into
    BriefNarrator. Distinct from ClaudeClient which returns AILayerOutput.
    """

    def __init__(self, api_key: str, model: str | None = None) -> None:
        """Initialise the narrator Claude client.

        Args:
            api_key: Anthropic API key.
            model: Model ID; defaults to settings.CLAUDE_MODEL.
        Raises:
            AIClientError: If the anthropic library is not installed.
        """
        if Anthropic is None:
            raise AIClientError("Anthropic client library is unavailable")
        self._client = Anthropic(api_key=api_key)
        self._model = model or settings.CLAUDE_MODEL

    def generate(self, system_prompt: str, user_message: str) -> str:
        """Generate prose narrative via the Claude messages API.

        Args:
            system_prompt: Instruction context and section data for the model.
            user_message: Specific request (e.g. "Write the section narrative for CIT.").
        Returns:
            Trimmed prose string from Claude.
        Raises:
            AIClientError: On API failure or empty response.
        """
        try:
            response = self._client.messages.create(
                model=self._model,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                max_tokens=_MAX_TOKENS,
            )
        except Exception as exc:
            logger.error("Claude narrator API call failed", exc_info=exc)
            raise AIClientError("Claude narrator API call failed") from exc

        content = getattr(response, "content", None)
        if not content:
            raise AIClientError("Claude narrator returned empty content")
        return content[0].text.strip()
