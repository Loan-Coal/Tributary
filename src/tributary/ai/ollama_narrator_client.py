"""
Module: ollama_narrator_client
Layer: ai
Purpose: Ollama HTTP client that generates free-text prose narratives for filing briefs.
    Returns plain strings (not structured AILayerOutput). Implements NarratorClientProtocol.
    Distinct from OllamaClient, which returns structured AILayerOutput for the AI layer.
Dependencies: json, urllib.request, tributary.common.errors, tributary.common.logging
Used by: engine.cli (_build_narrator when TRIBUTARY_LLM=ollama)
"""
from __future__ import annotations

import json
import urllib.request
from urllib.error import URLError

from tributary.common.errors import AIClientError
from tributary.common.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"
_CHAT_PATH = "/api/chat"
_MAX_TOKENS = 512


class OllamaNarratorClient:
    """NarratorClientProtocol implementation that generates prose via a local Ollama server.

    Returns plain strings, not structured AILayerOutput. Suitable for injection into
    BriefNarrator. Distinct from OllamaClient which returns AILayerOutput.
    """

    def __init__(
        self,
        model: str = "qwen3:8b",
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int = 120,
    ) -> None:
        """Initialise the Ollama narrator client.

        Args:
            model: Ollama model tag (e.g. "qwen2.5:14b", "llama3.2").
            base_url: Base URL of the Ollama server.
            timeout: HTTP timeout in seconds.
        """
        self.model = model
        self._url = base_url.rstrip("/") + _CHAT_PATH
        self._timeout = timeout

    def generate(self, system_prompt: str, user_message: str) -> str:
        """Generate prose narrative via the Ollama chat API.

        Args:
            system_prompt: Instruction context for the model.
            user_message: Specific generation request.
        Returns:
            Trimmed prose string from the model.
        Raises:
            AIClientError: On connection failure or empty response.
        """
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "options": {"num_predict": _MAX_TOKENS},
        }).encode()

        req = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode()
        except URLError as exc:
            logger.error("Ollama narrator request failed", exc_info=exc)
            raise AIClientError(
                f"Cannot reach Ollama at {self._url}. "
                "Ensure Ollama is running (`ollama serve`) and the model is pulled "
                f"(`ollama pull {self.model}`)."
            ) from exc

        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Ollama narrator response was not JSON", exc_info=exc)
            raise AIClientError("Ollama narrator returned non-JSON envelope") from exc

        content = (
            envelope.get("message", {}).get("content")
            or envelope.get("response")
            or ""
        )
        if not content:
            logger.error("Ollama narrator response had no content", extra={"envelope": envelope})
            raise AIClientError("Ollama narrator returned an empty response")
        return content.strip()
