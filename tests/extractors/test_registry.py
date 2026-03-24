"""Tests for extraction model registry — config-driven backend instantiation."""
from __future__ import annotations

import pytest
import yaml

from cxr_mvp.extractors.registry import load_config, load_extraction_backends


@pytest.fixture
def valid_config(tmp_path) -> str:
    config = {
        "prompt_template": "config/prompts/extract_cxr_pt.txt",
        "temperature": 0,
        "max_tokens": 1024,
        "models": [
            {"name": "sonnet", "provider": "anthropic",
             "model_id": "claude-sonnet-4-6-20250514", "mode": "batch", "enabled": True},
            {"name": "opus", "provider": "anthropic",
             "model_id": "claude-opus-4-6-20250514", "mode": "batch", "enabled": True},
            {"name": "disabled_model", "provider": "anthropic",
             "model_id": "x", "mode": "sync", "enabled": False},
        ],
    }
    path = tmp_path / "extraction_models.yaml"
    with open(path, "w") as f:
        yaml.dump(config, f)
    return str(path)


@pytest.fixture
def unknown_provider_config(tmp_path) -> str:
    config = {
        "prompt_template": "p.txt",
        "temperature": 0,
        "max_tokens": 1024,
        "models": [
            {"name": "x", "provider": "unknown_provider",
             "model_id": "x", "mode": "sync", "enabled": True},
        ],
    }
    path = tmp_path / "bad_config.yaml"
    with open(path, "w") as f:
        yaml.dump(config, f)
    return str(path)


class TestLoadConfig:
    def test_loads_yaml(self, valid_config):
        config = load_config(valid_config)
        assert config["temperature"] == 0
        assert len(config["models"]) == 3

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path.yaml")


class TestLoadExtractionBackends:
    def test_skips_disabled_models(self, valid_config):
        backends = load_extraction_backends(valid_config)
        names = [b.name() for b in backends]
        assert "disabled_model" not in names

    def test_loads_enabled_anthropic_backends(self, valid_config):
        backends = load_extraction_backends(valid_config)
        names = [b.name() for b in backends]
        assert "sonnet" in names
        assert "opus" in names

    def test_unknown_provider_warns(self, unknown_provider_config):
        """Unknown provider -> skip with warning, don't crash."""
        backends = load_extraction_backends(unknown_provider_config)
        assert len(backends) == 0
