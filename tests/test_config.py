"""Tests for centralized config loader."""
from __future__ import annotations

import pytest

from cxr_mvp.config import load_findings_config, FindingsConfig


@pytest.fixture
def config_path():
    return "config/findings_cxr.yaml"


class TestLoadFindingsConfig:
    def test_loads_config(self, config_path):
        config = load_findings_config(config_path)
        assert isinstance(config, FindingsConfig)

    def test_has_40_findings(self, config_path):
        config = load_findings_config(config_path)
        assert len(config.findings) == 40

    def test_finding_has_required_fields(self, config_path):
        config = load_findings_config(config_path)
        ptx = config.findings["pneumothorax"]
        assert ptx.en == "Pneumothorax"
        assert "pneumotórax" in ptx.pt
        assert ptx.category == "pulmonary"
        assert ptx.priority == "CRITICAL"
        assert ptx.tier == 1

    def test_finding_names(self, config_path):
        config = load_findings_config(config_path)
        assert "tuberculosis" in config.findings
        assert "spondylosis" in config.findings
        assert "endotracheal_tube" in config.findings

    def test_priorities(self, config_path):
        config = load_findings_config(config_path)
        critical = config.findings_by_priority("CRITICAL")
        assert "pneumothorax" in critical
        assert "device_malposition" in critical

    def test_categories(self, config_path):
        config = load_findings_config(config_path)
        devices = config.findings_by_category("device")
        assert "endotracheal_tube" in devices
        assert "cardiac_device" in devices
        assert "device_malposition" in devices

    def test_expected_finding_names(self, config_path):
        config = load_findings_config(config_path)
        names = config.finding_names()
        assert len(names) == 40
        assert isinstance(names, list)

    def test_discovery_config(self, config_path):
        config = load_findings_config(config_path)
        assert config.discovery_threshold > 0
        assert config.discovery_min_count > 0

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_findings_config("/nonexistent.yaml")


class TestFindingMetadata:
    def test_finding_has_type(self, config_path):
        config = load_findings_config(config_path)
        ptx = config.findings["pneumothorax"]
        assert ptx.type == "descriptive"

    def test_pneumonia_is_etiologic(self, config_path):
        config = load_findings_config(config_path)
        assert config.findings["pneumonia"].type == "etiologic"
        assert config.findings["tuberculosis"].type == "etiologic"

    def test_device_types(self, config_path):
        config = load_findings_config(config_path)
        assert config.findings["endotracheal_tube"].type == "device_presence"
        assert config.findings["device_malposition"].type == "device_position"

    def test_finding_has_acuity(self, config_path):
        config = load_findings_config(config_path)
        assert config.findings["pneumothorax"].acuity == "acute"

    def test_chronic_findings(self, config_path):
        config = load_findings_config(config_path)
        assert config.findings["spondylosis"].acuity == "chronic"
        assert config.findings["aortic_atherosclerosis"].acuity == "chronic"

    def test_context_dependent_findings(self, config_path):
        config = load_findings_config(config_path)
        assert config.findings["cardiomegaly"].acuity == "context_dependent"
        assert config.findings["effusion"].acuity == "context_dependent"

    def test_incidental_findings(self, config_path):
        config = load_findings_config(config_path)
        assert config.findings["calcified_granuloma"].acuity == "incidental"

    def test_findings_by_type(self, config_path):
        config = load_findings_config(config_path)
        etiologic = config.findings_by_type("etiologic")
        assert "pneumonia" in etiologic
        assert "tuberculosis" in etiologic
        assert "pneumothorax" not in etiologic

    def test_findings_by_acuity(self, config_path):
        config = load_findings_config(config_path)
        acute = config.findings_by_acuity("acute")
        assert "pneumothorax" in acute
        assert "spondylosis" not in acute


class TestOntologyHierarchy:
    def test_consolidation_parent(self, config_path):
        config = load_findings_config(config_path)
        assert config.findings["consolidation"].parent == "lung_opacity"

    def test_infiltration_parent(self, config_path):
        config = load_findings_config(config_path)
        assert config.findings["infiltration"].parent == "lung_opacity"

    def test_top_level_has_no_parent(self, config_path):
        config = load_findings_config(config_path)
        assert config.findings["pneumothorax"].parent is None
        assert config.findings["lung_opacity"].parent is None

    def test_children_method(self, config_path):
        config = load_findings_config(config_path)
        children = config.children("lung_opacity")
        assert "consolidation" in children
        assert "infiltration" in children
        assert "pneumothorax" not in children

    def test_children_of_leaf(self, config_path):
        config = load_findings_config(config_path)
        assert config.children("spondylosis") == []
