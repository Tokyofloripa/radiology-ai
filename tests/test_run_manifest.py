"""Tests for run manifest generation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cxr_mvp.run_manifest import generate_run_manifest


class TestGenerateRunManifest:
    def test_returns_dict(self):
        manifest = generate_run_manifest(models=["sonnet"])
        assert isinstance(manifest, dict)

    def test_has_required_fields(self):
        manifest = generate_run_manifest(models=["sonnet"])
        assert "run_id" in manifest
        assert "timestamp" in manifest
        assert "models" in manifest
        assert "ontology_version" in manifest
        assert "prompt_hash" in manifest
        assert "code_commit" in manifest

    def test_includes_model_details(self):
        manifest = generate_run_manifest(models=["sonnet", "opus"])
        assert len(manifest["models"]) == 2

    def test_run_id_is_unique(self):
        m1 = generate_run_manifest(models=["sonnet"])
        m2 = generate_run_manifest(models=["sonnet"])
        assert m1["run_id"] != m2["run_id"]

    def test_writes_to_file(self, tmp_path):
        manifest = generate_run_manifest(models=["sonnet"])
        out_path = tmp_path / "run_manifest.json"
        with open(out_path, "w") as f:
            json.dump(manifest, f)
        loaded = json.loads(out_path.read_text())
        assert loaded["ontology_version"] == manifest["ontology_version"]
