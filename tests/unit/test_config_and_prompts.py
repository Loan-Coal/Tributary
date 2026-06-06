"""
Module: test_config_and_prompts
Layer: test-unit
Purpose: Coverage tests for config.settings.validate() error paths and
    prompts.loader error paths (FileNotFoundError, YAMLError, invalid content).
Dependencies: os, pathlib, pytest, unittest.mock
Used by: make test
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest


# ===========================================================================
# config.settings — validate() raises ConfigurationError
# ===========================================================================


class TestSettingsValidate:
    def test_raises_configuration_error_when_api_key_missing(self, monkeypatch):
        """validate() raises ConfigurationError when ANTHROPIC_API_KEY absent and backend=claude."""
        from tributary.common.errors import ConfigurationError

        import tributary.config.settings as s

        monkeypatch.setattr(s, "LLM_BACKEND", "claude")
        monkeypatch.setattr(s, "ANTHROPIC_API_KEY", "")
        monkeypatch.setattr(s, "NEO4J_PASSWORD", "test-password")
        monkeypatch.setattr(s, "NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setattr(s, "NEO4J_USER", "neo4j")

        with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
            s.validate()

    def test_raises_configuration_error_lists_all_missing(self, monkeypatch):
        """validate() includes all missing variable names when backend=claude."""
        from tributary.common.errors import ConfigurationError

        import tributary.config.settings as s

        monkeypatch.setattr(s, "LLM_BACKEND", "claude")
        monkeypatch.setattr(s, "ANTHROPIC_API_KEY", "")
        monkeypatch.setattr(s, "NEO4J_PASSWORD", "")
        monkeypatch.setattr(s, "NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setattr(s, "NEO4J_USER", "neo4j")

        with pytest.raises(ConfigurationError) as exc_info:
            s.validate()
        assert "ANTHROPIC_API_KEY" in str(exc_info.value)
        assert "NEO4J_PASSWORD" in str(exc_info.value)

    def test_passes_when_all_vars_set(self, monkeypatch):
        """validate() must not raise when all required variables are non-empty."""
        import tributary.config.settings as s

        monkeypatch.setattr(s, "LLM_BACKEND", "claude")
        monkeypatch.setattr(s, "ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(s, "NEO4J_PASSWORD", "password")
        monkeypatch.setattr(s, "NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setattr(s, "NEO4J_USER", "neo4j")

        s.validate()  # must not raise

    def test_passes_without_api_key_when_backend_is_qwen(self, monkeypatch):
        """validate() must not require ANTHROPIC_API_KEY when TRIBUTARY_LLM=qwen."""
        import tributary.config.settings as s

        monkeypatch.setattr(s, "LLM_BACKEND", "qwen")
        monkeypatch.setattr(s, "ANTHROPIC_API_KEY", "")
        monkeypatch.setattr(s, "NEO4J_PASSWORD", "password")
        monkeypatch.setattr(s, "NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setattr(s, "NEO4J_USER", "neo4j")

        s.validate()  # must not raise


# ===========================================================================
# prompts.loader — error paths
# ===========================================================================


class TestPromptsLoaderErrors:
    def test_raises_on_file_not_found(self):
        """PromptLoaderError raised (not FileNotFoundError) when the YAML file is absent."""
        from tributary.common.errors import PromptLoaderError
        from tributary.prompts import loader as prompt_loader

        with patch.object(
            prompt_loader,
            "AI_CLASSIFICATION_FILE",
            Path("/nonexistent/path/to/prompt.yaml"),
        ):
            with pytest.raises(PromptLoaderError, match="missing"):
                prompt_loader.load_ai_classification_prompt()

    def test_raises_on_invalid_yaml(self, tmp_path):
        """PromptLoaderError raised (not YAMLError) when the file contains invalid YAML."""
        from tributary.common.errors import PromptLoaderError
        from tributary.prompts import loader as prompt_loader

        bad_yaml = tmp_path / "prompt.yaml"
        bad_yaml.write_text("key: [\n  unclosed bracket", encoding="utf-8")

        with patch.object(prompt_loader, "AI_CLASSIFICATION_FILE", bad_yaml):
            with pytest.raises(PromptLoaderError, match="invalid YAML"):
                prompt_loader.load_ai_classification_prompt()

    def test_raises_when_content_not_a_dict(self, tmp_path):
        """PromptLoaderError raised when the YAML root is a list, not a mapping."""
        from tributary.common.errors import PromptLoaderError
        from tributary.prompts import loader as prompt_loader

        list_yaml = tmp_path / "prompt.yaml"
        list_yaml.write_text("- item1\n- item2\n", encoding="utf-8")

        with patch.object(prompt_loader, "AI_CLASSIFICATION_FILE", list_yaml):
            with pytest.raises(PromptLoaderError, match="mapping"):
                prompt_loader.load_ai_classification_prompt()

    def test_raises_when_required_key_missing(self, tmp_path):
        """PromptLoaderError raised when the YAML dict lacks 'system_prompt'."""
        from tributary.common.errors import PromptLoaderError
        from tributary.prompts import loader as prompt_loader

        no_key_yaml = tmp_path / "prompt.yaml"
        no_key_yaml.write_text("other_key: value\n", encoding="utf-8")

        with patch.object(prompt_loader, "AI_CLASSIFICATION_FILE", no_key_yaml):
            with pytest.raises(PromptLoaderError, match="missing required keys"):
                prompt_loader.load_ai_classification_prompt()
