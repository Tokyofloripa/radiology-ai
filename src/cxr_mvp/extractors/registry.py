"""Config-driven extraction backend registry.

Reads extraction_models.yaml, instantiates backends by provider.
Import-guarded: missing SDK -> skip with warning."""
from __future__ import annotations

import warnings
from pathlib import Path

import yaml

from cxr_mvp.extractors.base import ExtractionBackend


def load_config(config_path: str) -> dict:
    """Load and return extraction_models.yaml."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(path) as f:
        return yaml.safe_load(f)


def load_extraction_backends(config_path: str) -> list[ExtractionBackend]:
    """Instantiate all enabled backends from config.

    Unknown or unavailable providers are skipped with a warning.
    """
    config = load_config(config_path)
    backends: list[ExtractionBackend] = []

    for model_cfg in config.get("models", []):
        if not model_cfg.get("enabled", False):
            continue

        provider = model_cfg["provider"]
        name = model_cfg["name"]
        model_id = model_cfg["model_id"]
        mode = model_cfg.get("mode", "sync")

        if provider == "anthropic":
            try:
                from cxr_mvp.extractors.anthropic_extractor import AnthropicExtractor
                backends.append(AnthropicExtractor(
                    config_name=name,
                    model_id=model_id,
                    mode=mode,
                    temperature=config.get("temperature", 0),
                    max_tokens=config.get("max_tokens", 1024),
                ))
            except ImportError:
                warnings.warn(
                    f"anthropic SDK not installed — skipping model '{name}'",
                    stacklevel=2,
                )
        else:
            warnings.warn(
                f"Unknown provider '{provider}' for model '{name}' — skipping",
                stacklevel=2,
            )

    return backends
