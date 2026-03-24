"""Tests for core data models — the schema contract everything depends on."""
from __future__ import annotations

import pytest

from cxr_mvp.models import (
    Confidence,
    ExamRecord,
    ExtractionResult,
    FindingLabel,
    GroundTruthRow,
    LabelState,
    ModelPrediction,
    OtherFinding,
    ReportExtraction,
    UniqueReport,
    ValidatedExtraction,
)


class TestLabelState:
    def test_all_five_states_exist(self):
        assert len(LabelState) == 5
        assert set(LabelState) == {
            LabelState.POSITIVE,
            LabelState.NEGATIVE,
            LabelState.UNCERTAIN,
            LabelState.ABSENT,
            LabelState.NOT_ASSESSABLE,
        }

    def test_string_values_match_playbook(self):
        assert LabelState.POSITIVE.value == "Positive"
        assert LabelState.NOT_ASSESSABLE.value == "Not_Assessable"


class TestFindingLabel:
    def test_valid_finding(self):
        f = FindingLabel(status="Positive", confidence="high", evidence="Área cardíaca aumentada")
        assert f.status == LabelState.POSITIVE
        assert f.confidence == Confidence.HIGH

    def test_normalizes_portuguese_input(self):
        f = FindingLabel(status="positivo")
        assert f.status == LabelState.POSITIVE

    def test_normalizes_english_lowercase(self):
        f = FindingLabel(status="absent")
        assert f.status == LabelState.ABSENT

    def test_normalizes_present_to_positive(self):
        f = FindingLabel(status="present")
        assert f.status == LabelState.POSITIVE

    def test_rejects_invalid_status(self):
        with pytest.raises(ValueError, match="Input should be"):
            FindingLabel(status="invalid_state")


class TestReportExtraction:
    def test_round_trip(self, sample_findings_abnormal):
        findings = {
            k: FindingLabel(**v) for k, v in sample_findings_abnormal.items()
        }
        extraction = ReportExtraction(
            exam_id="CXR001",
            classification="abnormal",
            findings=findings,
        )
        assert extraction.exam_id == "CXR001"
        assert extraction.findings["cardiomegaly"].status == LabelState.POSITIVE


class TestReportExtractionOptionalExamId:
    def test_exam_id_optional(self):
        """exam_id is optional — extraction is per report_hash, not per exam."""
        extraction = ReportExtraction(
            classification="normal",
            findings={},
        )
        assert extraction.exam_id is None

    def test_exam_id_still_accepted(self, sample_findings_abnormal):
        findings = {k: FindingLabel(**v) for k, v in sample_findings_abnormal.items()}
        extraction = ReportExtraction(
            exam_id="CXR001",
            classification="abnormal",
            findings=findings,
        )
        assert extraction.exam_id == "CXR001"


class TestModelPrediction:
    def test_has_provenance_fields(self):
        pred = ModelPrediction(
            exam_id="CXR001",
            model_name="mock",
            model_version="1.0.0",
            binary_label="abnormal",
            binary_score=0.73,
            config_hash="abc123",
        )
        assert pred.config_hash == "abc123"
        assert pred.model_version == "1.0.0"


class TestGroundTruthRow:
    def test_minimal_creation(self):
        row = GroundTruthRow(
            exam_id="CXR001",
            customer_id="2779",
            classification="normal",
            findings={},
        )
        assert row.exam_id == "CXR001"
        assert row.patient_id is None
        assert row.body_part == "CXR"


class TestGroundTruthRowUpdated:
    def test_patient_id_optional(self):
        """patient_id not available in CSV — optional, populated from DICOM later."""
        row = GroundTruthRow(
            exam_id="CXR001",
            customer_id="2779",
            classification="normal",
            findings={},
        )
        assert row.patient_id is None

    def test_body_part_defaults_to_cxr(self):
        row = GroundTruthRow(
            exam_id="CXR001",
            customer_id="2779",
            classification="normal",
            findings={},
        )
        assert row.body_part == "CXR"

    def test_report_hash_field(self):
        row = GroundTruthRow(
            exam_id="CXR001",
            customer_id="2779",
            classification="normal",
            findings={},
            report_hash="abc123def456",
        )
        assert row.report_hash == "abc123def456"

    def test_agreement_fields_default(self):
        row = GroundTruthRow(
            exam_id="CXR001",
            customer_id="2779",
            classification="normal",
            findings={},
        )
        assert row.inter_model_agreement == 1.0
        assert row.has_disagreement is False
        assert row.disagreement_findings == []
        assert row.primary_model == ""

    def test_agreement_fields_set(self):
        row = GroundTruthRow(
            exam_id="CXR001",
            customer_id="2779",
            classification="abnormal",
            findings={},
            inter_model_agreement=0.85,
            has_disagreement=True,
            disagreement_findings=["cardiomegaly"],
            primary_model="sonnet",
        )
        assert row.inter_model_agreement == 0.85
        assert row.disagreement_findings == ["cardiomegaly"]


class TestExamRecord:
    def test_creation(self):
        record = ExamRecord(
            exam_id="10794085",
            customer_id="2779",
            dicom_filenames=["10794085-PA.dcm", "10794085-LAT.dcm"],
            report_hash="a3f2b7c1d4e5",
            original_label=1,
            report_length=253,
        )
        assert record.exam_id == "10794085"
        assert len(record.dicom_filenames) == 2
        assert record.original_label == 1

    def test_single_dicom(self):
        record = ExamRecord(
            exam_id="10794085",
            customer_id="2779",
            dicom_filenames=["10794085-PA.dcm"],
            report_hash="abc123",
            original_label=2,
            report_length=100,
        )
        assert len(record.dicom_filenames) == 1


class TestUniqueReport:
    def test_creation(self):
        report = UniqueReport(
            report_hash="a3f2b7c1d4e5",
            report_text="Área cardíaca dentro dos limites.",
            exam_count=15,
            sample_exam_id="10794085",
        )
        assert report.exam_count == 15
        assert report.report_hash == "a3f2b7c1d4e5"


class TestExtractionResult:
    def test_creation(self):
        result = ExtractionResult(
            report_hash="a3f2b7c1d4e5",
            classification="normal",
            findings={"cardiomegaly": {"status": "Negative", "confidence": "high"}},
            extraction_model="sonnet",
            prompt_hash="abcdef12",
            timestamp="2026-03-23T12:00:00Z",
        )
        assert result.classification == "normal"
        assert result.extraction_model == "sonnet"

    def test_extraction_model_stores_config_name(self):
        """extraction_model stores config name (e.g., 'sonnet'), not raw model_id."""
        result = ExtractionResult(
            report_hash="abc",
            classification="abnormal",
            findings={},
            extraction_model="opus",
            prompt_hash="xyz",
            timestamp="2026-03-23T12:00:00Z",
        )
        assert result.extraction_model == "opus"


class TestOtherFinding:
    def test_creation(self):
        f = OtherFinding(
            name="bronchiectasis",
            original_term="bronquiectasias",
            status="Positive",
            confidence="high",
            evidence="Bronquiectasias cilíndricas em lobos inferiores",
            suggested_category="pulmonary",
        )
        assert f.name == "bronchiectasis"
        assert f.status == LabelState.POSITIVE

    def test_normalizes_portuguese_status(self):
        f = OtherFinding(name="test", original_term="teste", status="positivo")
        assert f.status == LabelState.POSITIVE

    def test_defaults(self):
        f = OtherFinding(name="test", original_term="teste", status="Positive")
        assert f.confidence == Confidence.MEDIUM
        assert f.suggested_category == "other"
        assert f.evidence is None


class TestReportExtractionV2:
    def test_accepts_other_findings(self, sample_findings_abnormal):
        findings = {k: FindingLabel(**v) for k, v in sample_findings_abnormal.items()}
        extraction = ReportExtraction(
            classification="abnormal",
            findings=findings,
            other_findings=[
                OtherFinding(name="test", original_term="teste", status="Positive"),
            ],
        )
        assert len(extraction.other_findings) == 1

    def test_other_findings_defaults_empty(self):
        extraction = ReportExtraction(classification="normal", findings={})
        assert extraction.other_findings == []

    def test_study_quality_fields(self):
        extraction = ReportExtraction(
            classification="normal",
            findings={},
            study_quality="suboptimal",
            study_quality_flags=["bedside", "rotation"],
        )
        assert extraction.study_quality == "suboptimal"
        assert "bedside" in extraction.study_quality_flags

    def test_study_quality_defaults(self):
        extraction = ReportExtraction(classification="normal", findings={})
        assert extraction.study_quality == "adequate"
        assert extraction.study_quality_flags == []


class TestExtractionResultV2:
    def test_has_other_findings(self):
        result = ExtractionResult(
            report_hash="abc",
            classification="normal",
            findings={},
            other_findings=[{"name": "test", "status": "Positive"}],
            extraction_model="sonnet",
            prompt_hash="ph",
            timestamp="t",
            study_quality="adequate",
            study_quality_flags=[],
        )
        assert len(result.other_findings) == 1
        assert result.study_quality == "adequate"


class TestValidatedExtraction:
    def test_creation(self):
        v = ValidatedExtraction(
            report_hash="abc",
            classification="abnormal",
            findings={},
            other_findings=[],
            extraction_model="sonnet",
            prompt_hash="ph",
            timestamp="t",
            study_quality="adequate",
            study_quality_flags=[],
            priority_level="CRITICAL",
            needs_review=False,
            review_reasons=[],
        )
        assert v.priority_level == "CRITICAL"
        assert v.needs_review is False

    def test_upgraded_classification(self):
        v = ValidatedExtraction(
            report_hash="abc",
            classification="abnormal",
            findings={},
            other_findings=[],
            extraction_model="sonnet",
            prompt_hash="ph",
            timestamp="t",
            study_quality="adequate",
            study_quality_flags=[],
            priority_level="CRITICAL",
            needs_review=True,
            review_reasons=["critical_finding_override"],
            original_classification="normal",
        )
        assert v.original_classification == "normal"
        assert v.classification == "abnormal"


class TestExtractionResultProvenance:
    def test_has_ontology_version(self):
        result = ExtractionResult(
            report_hash="abc",
            classification="normal",
            findings={},
            extraction_model="sonnet",
            prompt_hash="ph",
            timestamp="t",
            ontology_version="2.0.0",
        )
        assert result.ontology_version == "2.0.0"

    def test_ontology_version_default(self):
        result = ExtractionResult(
            report_hash="abc",
            classification="normal",
            findings={},
            extraction_model="sonnet",
            prompt_hash="ph",
            timestamp="t",
        )
        assert result.ontology_version == ""

    def test_extraction_schema_default(self):
        result = ExtractionResult(
            report_hash="abc",
            classification="normal",
            findings={},
            extraction_model="sonnet",
            prompt_hash="ph",
            timestamp="t",
        )
        assert result.extraction_schema == "v2"
