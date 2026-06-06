"""
Module: loader
Layer: prompts
Purpose: Load YAML prompt templates for the AI layer.
Dependencies: pathlib, typing, yaml, tributary.common.errors, tributary.common.logging
Used by: ai.service
"""
from pathlib import Path
from typing import Dict

import yaml

from tributary.common.errors import PromptLoaderError
from tributary.common.logging import get_logger

PROMPTS_DIR = Path(__file__).resolve().parent
AI_CLASSIFICATION_FILE = PROMPTS_DIR / "ai_classification.yaml"

logger = get_logger(__name__)


def load_ai_classification_prompt() -> Dict[str, str]:
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
