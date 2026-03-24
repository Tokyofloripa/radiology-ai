"""Tests for named label interpretation maps."""
from __future__ import annotations

import pytest

from cxr_mvp.label_maps import (
    apply_label_map,
    LABEL_MAPS,
)


@pytest.fixture
def abnormal_findings():
    return {
        "pneumonia": {"status": "Uncertain"},
        "consolidation": {"status": "Positive"},
        "lung_opacity": {"status": "Positive"},
        "cardiomegaly": {"status": "Negative"},
        "spondylosis": {"status": "Positive"},
        "effusion": {"status": "Absent"},
    }


@pytest.fixture
def normal_findings():
    return {
        "pneumonia": {"status": "Absent"},
        "consolidation": {"status": "Negative"},
        "cardiomegaly": {"status": "Negative"},
    }


class TestLabelMaps:
    def test_available_maps(self):
        assert "strict" in LABEL_MAPS
        assert "broad" in LABEL_MAPS
        assert "parenchymal_opacity" in LABEL_MAPS

    def test_strict_positive_only(self, abnormal_findings):
        result = apply_label_map(abnormal_findings, "strict")
        assert result["pneumonia"] is False  # Uncertain excluded
        assert result["consolidation"] is True
        assert result["cardiomegaly"] is False

    def test_broad_includes_uncertain(self, abnormal_findings):
        result = apply_label_map(abnormal_findings, "broad")
        assert result["pneumonia"] is True  # Uncertain included
        assert result["consolidation"] is True

    def test_parenchymal_opacity(self, abnormal_findings):
        result = apply_label_map(abnormal_findings, "parenchymal_opacity")
        assert result["parenchymal_opacity_present"] is True

    def test_parenchymal_opacity_negative(self, normal_findings):
        result = apply_label_map(normal_findings, "parenchymal_opacity")
        assert result["parenchymal_opacity_present"] is False

    def test_unknown_map_raises(self, abnormal_findings):
        with pytest.raises(KeyError):
            apply_label_map(abnormal_findings, "nonexistent_map")

    def test_strict_excludes_not_assessable(self):
        findings = {"pneumonia": {"status": "Not_Assessable"}}
        result = apply_label_map(findings, "strict")
        assert result["pneumonia"] is None  # excluded, not True or False

    def test_broad_excludes_not_assessable(self):
        findings = {"pneumonia": {"status": "Not_Assessable"}}
        result = apply_label_map(findings, "broad")
        assert result["pneumonia"] is None
