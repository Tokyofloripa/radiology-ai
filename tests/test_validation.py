"""Tests for post-extraction validation — ghost-abnormal, critical override, triage priority."""
from __future__ import annotations

import pytest

from cxr_mvp.validation import validate_extraction, compute_priority
from cxr_mvp.models import ExtractionResult, ValidatedExtraction


@pytest.fixture
def normal_result():
    return ExtractionResult(
        report_hash="h1", classification="normal",
        findings={"cardiomegaly": {"status": "Negative"}, "pneumothorax": {"status": "Absent"}},
        other_findings=[], extraction_model="sonnet", prompt_hash="ph",
        timestamp="t", study_quality="adequate", study_quality_flags=[],
    )


@pytest.fixture
def abnormal_with_findings():
    return ExtractionResult(
        report_hash="h2", classification="abnormal",
        findings={"cardiomegaly": {"status": "Positive", "confidence": "high"},
                  "pneumothorax": {"status": "Absent"}},
        other_findings=[], extraction_model="sonnet", prompt_hash="ph",
        timestamp="t", study_quality="adequate", study_quality_flags=[],
    )


@pytest.fixture
def ghost_abnormal():
    return ExtractionResult(
        report_hash="h3", classification="abnormal",
        findings={"cardiomegaly": {"status": "Negative"}, "pneumothorax": {"status": "Absent"}},
        other_findings=[], extraction_model="sonnet", prompt_hash="ph",
        timestamp="t", study_quality="adequate", study_quality_flags=[],
    )


@pytest.fixture
def normal_with_critical():
    return ExtractionResult(
        report_hash="h4", classification="normal",
        findings={"pneumothorax": {"status": "Positive", "confidence": "high"}},
        other_findings=[], extraction_model="sonnet", prompt_hash="ph",
        timestamp="t", study_quality="adequate", study_quality_flags=[],
    )


class TestValidateExtraction:
    def test_normal_passthrough(self, normal_result):
        v = validate_extraction(normal_result)
        assert isinstance(v, ValidatedExtraction)
        assert v.classification == "normal"
        assert v.needs_review is False
        assert v.priority_level == "NONE"

    def test_abnormal_with_findings(self, abnormal_with_findings):
        v = validate_extraction(abnormal_with_findings)
        assert v.classification == "abnormal"
        assert v.needs_review is False
        assert v.priority_level == "HIGH"  # cardiomegaly = HIGH

    def test_ghost_abnormal_flagged(self, ghost_abnormal):
        v = validate_extraction(ghost_abnormal)
        assert v.classification == "abnormal"  # NOT downgraded
        assert v.needs_review is True
        assert "no_supporting_findings" in v.review_reasons

    def test_critical_finding_upgrades_normal(self, normal_with_critical):
        v = validate_extraction(normal_with_critical)
        assert v.classification == "abnormal"  # UPGRADED
        assert v.needs_review is True
        assert "critical_finding_override" in v.review_reasons
        assert v.original_classification == "normal"
        assert v.priority_level == "CRITICAL"

    def test_ghost_abnormal_with_tier2_positive(self):
        result = ExtractionResult(
            report_hash="h5", classification="abnormal",
            findings={"cardiomegaly": {"status": "Negative"}},
            other_findings=[{"name": "bronchiectasis", "status": "Positive"}],
            extraction_model="sonnet", prompt_hash="ph", timestamp="t",
            study_quality="adequate", study_quality_flags=[],
        )
        v = validate_extraction(result)
        assert v.needs_review is False  # Tier 2 positive = not a ghost


class TestComputePriority:
    def test_critical(self):
        findings = {"pneumothorax": {"status": "Positive"}}
        assert compute_priority(findings, []) == "CRITICAL"

    def test_high(self):
        findings = {"cardiomegaly": {"status": "Positive"}}
        assert compute_priority(findings, []) == "HIGH"

    def test_moderate(self):
        findings = {"fracture": {"status": "Positive"}}
        assert compute_priority(findings, []) == "MODERATE"

    def test_low(self):
        findings = {"spondylosis": {"status": "Positive"}}
        assert compute_priority(findings, []) == "LOW"

    def test_none_when_all_negative(self):
        findings = {"cardiomegaly": {"status": "Negative"}}
        assert compute_priority(findings, []) == "NONE"

    def test_highest_wins(self):
        findings = {
            "spondylosis": {"status": "Positive"},
            "pneumothorax": {"status": "Uncertain"},
        }
        assert compute_priority(findings, []) == "CRITICAL"

    def test_tier2_defaults_to_moderate(self):
        findings = {"cardiomegaly": {"status": "Negative"}}
        other = [{"name": "test", "status": "Positive"}]
        assert compute_priority(findings, other) == "MODERATE"


class TestWidenedReviewTriggers:
    def test_high_uncertainty_triggers_review(self):
        """3+ Uncertain findings should trigger review."""
        result = ExtractionResult(
            report_hash="h_unc", classification="abnormal",
            findings={
                "pneumonia": {"status": "Uncertain"},
                "effusion": {"status": "Uncertain"},
                "consolidation": {"status": "Uncertain"},
            },
            other_findings=[], extraction_model="sonnet", prompt_hash="ph",
            timestamp="t", study_quality="adequate", study_quality_flags=[],
        )
        v = validate_extraction(result)
        assert v.needs_review is True
        assert "high_uncertainty" in v.review_reasons

    def test_critical_on_suboptimal_triggers_review(self):
        """CRITICAL finding on suboptimal study should trigger review."""
        result = ExtractionResult(
            report_hash="h_sub", classification="abnormal",
            findings={"pneumothorax": {"status": "Positive"}},
            other_findings=[], extraction_model="sonnet", prompt_hash="ph",
            timestamp="t", study_quality="suboptimal", study_quality_flags=["bedside"],
        )
        v = validate_extraction(result)
        assert v.needs_review is True
        assert "critical_on_suboptimal" in v.review_reasons

    def test_device_without_position_triggers_review(self):
        """Device present without malposition assessment should trigger review."""
        result = ExtractionResult(
            report_hash="h_dev", classification="abnormal",
            findings={
                "endotracheal_tube": {"status": "Positive"},
                "device_malposition": {"status": "Absent"},
            },
            other_findings=[], extraction_model="sonnet", prompt_hash="ph",
            timestamp="t", study_quality="adequate", study_quality_flags=[],
        )
        v = validate_extraction(result)
        assert v.needs_review is True
        assert "device_without_position" in v.review_reasons

    def test_multiple_reasons_accumulated(self):
        """Multiple triggers should all appear in review_reasons."""
        result = ExtractionResult(
            report_hash="h_multi", classification="abnormal",
            findings={
                "pneumothorax": {"status": "Positive"},
                "pneumonia": {"status": "Uncertain"},
                "effusion": {"status": "Uncertain"},
                "consolidation": {"status": "Uncertain"},
                "endotracheal_tube": {"status": "Positive"},
                "device_malposition": {"status": "Absent"},
            },
            other_findings=[], extraction_model="sonnet", prompt_hash="ph",
            timestamp="t", study_quality="suboptimal", study_quality_flags=["bedside"],
        )
        v = validate_extraction(result)
        assert v.needs_review is True
        assert len(v.review_reasons) >= 3  # high_uncertainty + critical_on_suboptimal + device_without_position

    def test_no_trigger_clean(self):
        """Clean extraction should have empty review_reasons."""
        result = ExtractionResult(
            report_hash="h_clean", classification="abnormal",
            findings={"cardiomegaly": {"status": "Positive"}},
            other_findings=[], extraction_model="sonnet", prompt_hash="ph",
            timestamp="t", study_quality="adequate", study_quality_flags=[],
        )
        v = validate_extraction(result)
        assert v.needs_review is False
        assert v.review_reasons == []


class TestAcuteClassification:
    def test_chronic_only_is_not_acute(self):
        """Report with only chronic findings -> acute_classification='normal'."""
        result = ExtractionResult(
            report_hash="h_chronic", classification="abnormal",
            findings={
                "spondylosis": {"status": "Positive"},
                "aortic_atherosclerosis": {"status": "Positive"},
            },
            other_findings=[], extraction_model="sonnet", prompt_hash="ph",
            timestamp="t", study_quality="adequate", study_quality_flags=[],
        )
        v = validate_extraction(result)
        assert v.classification == "abnormal"
        assert v.acute_classification == "normal"

    def test_acute_finding_is_acute(self):
        """Report with an acute finding -> acute_classification='abnormal'."""
        result = ExtractionResult(
            report_hash="h_acute", classification="abnormal",
            findings={
                "pneumothorax": {"status": "Positive"},
                "spondylosis": {"status": "Positive"},
            },
            other_findings=[], extraction_model="sonnet", prompt_hash="ph",
            timestamp="t", study_quality="adequate", study_quality_flags=[],
        )
        v = validate_extraction(result)
        assert v.classification == "abnormal"
        assert v.acute_classification == "abnormal"

    def test_context_dependent_is_acute(self):
        """Context-dependent findings count as potentially acute."""
        result = ExtractionResult(
            report_hash="h_ctx", classification="abnormal",
            findings={"effusion": {"status": "Positive"}},
            other_findings=[], extraction_model="sonnet", prompt_hash="ph",
            timestamp="t", study_quality="adequate", study_quality_flags=[],
        )
        v = validate_extraction(result)
        assert v.acute_classification == "abnormal"

    def test_incidental_only_not_acute(self):
        """Report with only incidental findings -> acute_classification='normal'."""
        result = ExtractionResult(
            report_hash="h_inc", classification="abnormal",
            findings={"calcified_granuloma": {"status": "Positive"}},
            other_findings=[], extraction_model="sonnet", prompt_hash="ph",
            timestamp="t", study_quality="adequate", study_quality_flags=[],
        )
        v = validate_extraction(result)
        assert v.acute_classification == "normal"

    def test_normal_report_is_normal_acute(self):
        """Normal report -> acute_classification='normal' too."""
        result = ExtractionResult(
            report_hash="h_norm", classification="normal",
            findings={"cardiomegaly": {"status": "Negative"}},
            other_findings=[], extraction_model="sonnet", prompt_hash="ph",
            timestamp="t", study_quality="adequate", study_quality_flags=[],
        )
        v = validate_extraction(result)
        assert v.acute_classification == "normal"

    def test_uncertain_acute_counts(self):
        """Uncertain status on an acute finding -> acute_classification='abnormal'."""
        result = ExtractionResult(
            report_hash="h_unc_acute", classification="abnormal",
            findings={"edema": {"status": "Uncertain"}},
            other_findings=[], extraction_model="sonnet", prompt_hash="ph",
            timestamp="t", study_quality="adequate", study_quality_flags=[],
        )
        v = validate_extraction(result)
        assert v.acute_classification == "abnormal"


class TestHierarchyConsistency:
    def test_child_positive_parent_absent_flags_review(self):
        """If consolidation=Positive but lung_opacity=Absent -> review."""
        result = ExtractionResult(
            report_hash="h_hier", classification="abnormal",
            findings={
                "consolidation": {"status": "Positive"},
                "lung_opacity": {"status": "Absent"},
            },
            other_findings=[], extraction_model="sonnet", prompt_hash="ph",
            timestamp="t", study_quality="adequate", study_quality_flags=[],
        )
        v = validate_extraction(result)
        assert v.needs_review is True
        assert "hierarchy_inconsistency" in v.review_reasons

    def test_child_positive_parent_positive_ok(self):
        """If both consolidation and lung_opacity are Positive -> no flag."""
        result = ExtractionResult(
            report_hash="h_ok", classification="abnormal",
            findings={
                "consolidation": {"status": "Positive"},
                "lung_opacity": {"status": "Positive"},
            },
            other_findings=[], extraction_model="sonnet", prompt_hash="ph",
            timestamp="t", study_quality="adequate", study_quality_flags=[],
        )
        v = validate_extraction(result)
        assert "hierarchy_inconsistency" not in v.review_reasons

    def test_no_hierarchy_findings_ok(self):
        """Findings without parent-child relationship -> no flag."""
        result = ExtractionResult(
            report_hash="h_nohier", classification="abnormal",
            findings={"cardiomegaly": {"status": "Positive"}},
            other_findings=[], extraction_model="sonnet", prompt_hash="ph",
            timestamp="t", study_quality="adequate", study_quality_flags=[],
        )
        v = validate_extraction(result)
        assert "hierarchy_inconsistency" not in v.review_reasons

    def test_child_uncertain_parent_absent_flags(self):
        """Uncertain child with Absent parent -> also inconsistent."""
        result = ExtractionResult(
            report_hash="h_unc_hier", classification="abnormal",
            findings={
                "infiltration": {"status": "Uncertain"},
                "lung_opacity": {"status": "Absent"},
            },
            other_findings=[], extraction_model="sonnet", prompt_hash="ph",
            timestamp="t", study_quality="adequate", study_quality_flags=[],
        )
        v = validate_extraction(result)
        assert "hierarchy_inconsistency" in v.review_reasons
