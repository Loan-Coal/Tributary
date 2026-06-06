"""
Module: ollama_client
Layer: ai
Purpose: Ollama HTTP client adapter for structured AI output. Calls a locally running
    Ollama server (default http://localhost:11434) and validates the response as
    AILayerOutput. No torch or transformers dependency — Ollama manages the model.
Dependencies: json, re, urllib.request, tributary.ai.models, tributary.common.errors,
    tributary.common.logging
Used by: engine.cli (_build_llm_client when TRIBUTARY_LLM=ollama)
"""
from __future__ import annotations

import json
import re
import urllib.request
from urllib.error import URLError

from tributary.ai.models import AILayerOutput
from tributary.common.errors import AIClientError
from tributary.common.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"
_CHAT_PATH = "/api/chat"


class OllamaClient:
    """LLMClientProtocol implementation that calls a local Ollama server."""

    def __init__(
        self,
        model: str = "qwen3:8b",
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int = 120,
    ) -> None:
        """Initialise the Ollama client.

        Args:
            model: Ollama model tag (e.g. "qwen3:8b", "qwen3:30b", "llama3.2").
            base_url: Base URL of the Ollama server.
            timeout: HTTP timeout in seconds.
        """
        self.model = model
        self._url = base_url.rstrip("/") + _CHAT_PATH
        self._timeout = timeout

    def generate(self, prompt: str, max_tokens: int = 800) -> AILayerOutput:
        """Send the prompt to Ollama and return a validated AILayerOutput.

        Args:
            prompt: User-turn prompt text (system prompt baked in by AILayerService).
            max_tokens: Maximum tokens for the response.
        Returns:
            Validated AILayerOutput parsed from the model's JSON response.
        Raises:
            AIClientError: On connection failure, non-JSON output, or schema mismatch.
        """
        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"num_predict": max_tokens},
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
            logger.error("Ollama request failed", exc_info=exc)
            raise AIClientError(
                f"Cannot reach Ollama at {self._url}. "
                "Ensure Ollama is running (`ollama serve`) and the model is pulled "
                f"(`ollama pull {self.model}`)."
            ) from exc

        return self._parse_response(raw)

    def _parse_response(self, raw: str) -> AILayerOutput:
        """Extract and validate the JSON payload from an Ollama chat response.

        Args:
            raw: Raw JSON string from Ollama.
        Returns:
            Validated AILayerOutput.
        Raises:
            AIClientError: On JSON decode failure or Pydantic validation failure.
        """
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Ollama response was not JSON", exc_info=exc)
            raise AIClientError("Ollama returned non-JSON envelope") from exc

        content = (
            envelope.get("message", {}).get("content")
            or envelope.get("response")
            or ""
        )
        if not content:
            logger.error("Ollama response had no content", extra={"envelope": envelope})
            raise AIClientError("Ollama returned an empty response")

        payload = self._extract_json(content)
        try:
            return AILayerOutput.model_validate(payload)
        except Exception as exc:
            logger.error("Ollama output failed AILayerOutput validation", exc_info=exc)
            raise AIClientError("Ollama returned invalid structured output") from exc

    def _extract_json(self, content: str) -> dict:
        """Extract the JSON object from model output, stripping markdown fences if present.

        Args:
            content: Raw model output string.
        Returns:
            Parsed dict.
        Raises:
            AIClientError: If no valid JSON object is found.
        """
        content = content.strip()
        fenced = re.search(r"```(?:json)?\s*\n(.*?)\n```", content, re.S)
        if fenced:
            content = fenced.group(1).strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start, end = content.find("{"), content.rfind("}")
            if start == -1 or end == -1 or start >= end:
                logger.error("No JSON object found in Ollama output", extra={"content": content})
                raise AIClientError("Ollama returned output with no JSON object") from None
            try:
                return json.loads(content[start:end + 1])
            except json.JSONDecodeError as exc:
                raise AIClientError("Ollama returned malformed JSON") from exc
