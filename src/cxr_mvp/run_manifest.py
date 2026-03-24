"""Run manifest generation for reproducibility and audit trail.

Captures frozen versions of all pipeline components at run time."""
from __future__ import annotations

import hashlib
import subprocess
import time
import uuid
from pathlib import Path

from cxr_mvp.config import load_findings_config
from cxr_mvp.prompt_generator import prompt_hash


def generate_run_manifest(
    models: list[str],
    config_path: str = "config/findings_cxr.yaml",
    extraction_config_path: str = "config/extraction_models.yaml",
) -> dict:
    """Generate a run manifest with frozen versions of all pipeline components."""
    # Load config versions
    try:
        config = load_findings_config(config_path)
        ontology_version = config.version
    except FileNotFoundError:
        ontology_version = "unknown"

    try:
        phash = prompt_hash(config_path)
    except FileNotFoundError:
        phash = "unknown"

    # YAML hash
    yaml_hash = ""
    yaml_path = Path(config_path)
    if yaml_path.exists():
        yaml_hash = hashlib.sha256(yaml_path.read_bytes()).hexdigest()[:16]

    # Git commit
    try:
        code_commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        code_commit = "unknown"

    return {
        "run_id": str(uuid.uuid4())[:8],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "models": models,
        "ontology_version": ontology_version,
        "prompt_hash": phash,
        "yaml_hash": yaml_hash,
        "code_commit": code_commit,
        "extraction_schema": "v2",
        "pipeline_version": "v3",
    }
