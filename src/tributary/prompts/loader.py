"""
Module: loader
Layer: prompts
Purpose: Load YAML prompt templates for the AI layer.
Dependencies: pathlib, typing, yaml, tributary.common.errors, tributary.common.logging
Used by: ai.service
"""
from pathlib import Path

import yaml

from tributary.common.errors import PromptLoaderError
from tributary.common.logging import get_logger

PROMPTS_DIR = Path(__file__).resolve().parent
AI_CLASSIFICATION_FILE = PROMPTS_DIR / "ai_classification.yaml"
BRIEF_NARRATIVE_FILE = PROMPTS_DIR / "brief_narrative.yaml"

logger = get_logger(__name__)


def load_ai_classification_prompt() -> dict[str, str]:
    """Load the AI classification prompt from YAML."""
    try:
        with AI_CLASSIFICATION_FILE.open("r", encoding="utf-8") as prompt_file:
            raw = yaml.safe_load(prompt_file)
    except FileNotFoundError as exc:
        logger.error("Prompt file not found", exc_info=exc)
        raise PromptLoaderError("AI classification prompt file is missing") from exc
    except yaml.YAMLError as exc:
        logger.error("Prompt file failed to parse", exc_info=exc)
        raise PromptLoaderError("AI classification prompt file is invalid YAML") from exc

    if not isinstance(raw, dict):
        raise PromptLoaderError("AI classification prompt content must be a mapping")

    required_keys = {"system_prompt"}
    if not required_keys.issubset(set(raw.keys())):
        raise PromptLoaderError("AI classification prompt file is missing required keys")

    return {key: str(raw[key]) for key in raw}


def load_brief_narrative_prompts() -> dict[str, str]:
    """Load the brief narrative prompts from YAML.

    Returns:
        Dict with keys 'section_narrative' and 'conflict_narrative'.
    Raises:
        PromptLoaderError: If the file is missing, invalid YAML, or missing required keys.
    """
    try:
        with BRIEF_NARRATIVE_FILE.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError as exc:
        raise PromptLoaderError("Brief narrative prompt file is missing") from exc
    except yaml.YAMLError as exc:
        raise PromptLoaderError("Brief narrative prompt file is invalid YAML") from exc

    if not isinstance(raw, dict):
        raise PromptLoaderError("Brief narrative prompt content must be a mapping")

    required_keys = {"section_narrative", "conflict_narrative"}
    if not required_keys.issubset(set(raw.keys())):
        raise PromptLoaderError("Brief narrative prompt file is missing required keys")

    return {key: str(raw[key]) for key in raw}
