"""
Module: errors
Layer: common
Purpose: Custom exception hierarchy for Tributary.
Dependencies: none
Used by: all layers
"""


class TributaryError(Exception):
    """Base exception for Tributary domain errors."""


class PromptLoaderError(TributaryError):
    """Raised when a prompt cannot be loaded or validated."""


class AIClientError(TributaryError):
    """Raised when the AI client fails or returns invalid structured output."""


class AILayerServiceError(TributaryError):
    """Raised when the AI layer service encounters an unrecoverable error."""
