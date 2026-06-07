"""
Module: cached_narrator_client
Layer: ai
Purpose: Caching wrapper around any NarratorClientProtocol. On a cache hit, returns the
    stored narrative without calling the underlying client. On a miss: in read-only mode,
    returns a static fallback; in write mode, calls the underlying client and persists the
    result. Cache is a flat JSON dict: SHA-256(system_prompt + user_message) → narrative.
Dependencies: hashlib, json, pathlib, tributary.common.errors, tributary.common.logging,
    tributary.common.protocols_ai
Used by: engine.cli (wired into BriefNarrator for demo and run-golden)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from tributary.common.errors import AILayerError
from tributary.common.logging import get_logger

if TYPE_CHECKING:
    from tributary.common.protocols_ai import NarratorClientProtocol

logger = get_logger(__name__)

# Static per-type narratives used as offline fallback when the AI cache is cold.
# These are intentionally generic — they confirm the legal basis without hallucinating
# figures (all numbers come from the engine sections above).
_STATIC_NARRATIVES: dict[str, str] = {
    "CIT": (
        "This corporate income tax obligation arises under the jurisdiction's domestic tax "
        "legislation as cited above. The taxable base is computed by the Tributary engine from "
        "the source flows shown; the applicable rate and any loss reliefs are drawn from the "
        "versioned rule pack. A qualified tax professional should verify the income "
        "classification and confirm that all deductible expenses are substantiated before filing."
    ),
    "WHT": (
        "This withholding tax obligation arises on a cross-border payment subject to domestic "
        "withholding rules as cited above. Where a tax treaty applies, the reduced or zero rate "
        "shown has been determined by the engine against the treaty conditions in the rule pack. "
        "A qualified tax professional should confirm the beneficial ownership of the payee and "
        "the availability of any treaty relief claimed before remitting payment."
    ),
    "VAT": (
        "This value-added tax registration obligation is triggered by the turnover threshold "
        "shown above. The registration requirement and applicable threshold are sourced from the "
        "rule pack as cited. The net VAT payable (input/output tax arithmetic) is outside the "
        "current engine scope and must be computed by a local VAT specialist. Quarterly return "
        "obligations apply once registered."
    ),
    "TRADE_TAX": (
        "This trade tax (Gewerbesteuer) obligation arises under German municipal trade tax "
        "legislation as cited. The effective rate reflects the average municipal multiplier "
        "applied to the trade income computed by the engine. The exact multiplier varies by "
        "municipality and should be confirmed with local advisors before filing."
    ),
    "conflict": (
        "This cross-border conflict arises from concurrent taxing rights over the same income "
        "base. The treaty mechanism shown has been applied by the engine to eliminate or reduce "
        "double taxation. A qualified international tax professional should review the treaty "
        "conditions, confirm that all procedural requirements are met, and advise on any "
        "notification or election obligations before the relevant filing deadlines."
    ),
}

_FALLBACK = (
    "AI narrative not available offline. Run `make snapshot-ai` (with TRIBUTARY_AI_ENABLED=1) "
    "to pre-generate narratives, or set TRIBUTARY_AI_ENABLED=1 for live generation."
)


def _static_narrative(system_prompt: str, user_message: str) -> str:
    """Select the best static narrative based on obligation type keywords.

    Args:
        system_prompt: System instruction text.
        user_message: User turn text (contains JSON section summary).
    Returns:
        The most specific static narrative string, or _FALLBACK if no match.
    """
    combined = (system_prompt + " " + user_message).upper()
    if "conflict" in (system_prompt + user_message).lower():
        return _STATIC_NARRATIVES["conflict"]
    for key in ("TRADE_TAX", "VAT", "WHT", "CIT"):
        if key in combined:
            return _STATIC_NARRATIVES[key]
    return _FALLBACK

_SEPARATOR = "\n\x00\n"


def _cache_key(system_prompt: str, user_message: str) -> str:
    """Compute a stable SHA-256 cache key from the two prompt components.

    Args:
        system_prompt: System instruction text.
        user_message: User turn text.
    Returns:
        64-character hex digest.
    """
    raw = system_prompt + _SEPARATOR + user_message
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CachedNarratorClient:
    """NarratorClientProtocol adapter that serves responses from a JSON cache.

    In read_only mode (for ``make demo``): never calls the underlying client;
    returns a fallback string on cache miss.
    In write mode (for ``make snapshot-ai``): calls the underlying client on
    miss and persists the result to the cache file.
    """

    def __init__(
        self,
        underlying: NarratorClientProtocol | None,
        cache_path: Path,
        read_only: bool = True,
    ) -> None:
        """Wire the cache and optional underlying client.

        Args:
            underlying: Real narrator client used on cache miss. Must be provided
                when read_only=False.
            cache_path: Path to the JSON cache file.
            read_only: If True, returns fallback on miss without calling underlying.
        Raises:
            AILayerError: If read_only=False and underlying is None.
        """
        if not read_only and underlying is None:
            raise AILayerError("CachedNarratorClient requires underlying client when read_only=False")
        self._underlying = underlying
        self._cache_path = cache_path
        self._read_only = read_only
        self._cache: dict[str, str] = self._load_cache()

    def _load_cache(self) -> dict[str, str]:
        """Read the JSON cache from disk; return empty dict on first use.

        Returns:
            Dict mapping cache key → narrative string.
        """
        if not self._cache_path.exists():
            return {}
        try:
            return json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("AI cache unreadable; starting empty", extra={"error": str(exc)})
            return {}

    def _persist(self) -> None:
        """Write the in-memory cache dict to disk.

        Raises:
            AILayerError: If the cache file cannot be written.
        """
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps(self._cache, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            raise AILayerError(f"Cannot write AI cache: {exc}") from exc

    def generate(self, system_prompt: str, user_message: str) -> str:
        """Return a cached narrative, or generate and cache one on miss.

        Args:
            system_prompt: System instruction text.
            user_message: User turn text.
        Returns:
            Narrative prose string.
        """
        key = _cache_key(system_prompt, user_message)
        if key in self._cache:
            logger.debug("AI cache hit", extra={"key": key[:12]})
            return self._cache[key]

        if self._read_only:
            logger.info("AI cache miss (read-only) — returning static narrative", extra={"key": key[:12]})
            return _static_narrative(system_prompt, user_message)

        assert self._underlying is not None
        narrative = self._underlying.generate(system_prompt, user_message)
        self._cache[key] = narrative
        self._persist()
        logger.info("AI cache written", extra={"key": key[:12]})
        return narrative
