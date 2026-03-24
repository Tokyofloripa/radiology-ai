"""Tests for ground truth assembly — join, flag comparison, balance, statistics."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cxr_mvp.reference_labels import join_extractions_to_exams, build_balanced_set, compute_statistics, compare_flags


@pytest.fixture
def gt_inputs(tmp_path) -> dict:
    """Create exam_registry.jsonl + selected_extractions.jsonl + agreement_report.json."""
    out = tmp_path / "output"
    gt = out / "reference_labels"
    gt.mkdir(parents=True)

    # Exam registry
    exams = [
        {"exam_id": "E1", "customer_id": "C1", "dicom_filenames": ["e1.dcm"],
         "report_hash": "h1", "original_label": 1, "report_length": 100},
        {"exam_id": "E2", "customer_id": "C1", "dicom_filenames": ["e2.dcm"],
         "report_hash": "h2", "original_label": 2, "report_length": 200},
        {"exam_id": "E3", "customer_id": "C2", "dicom_filenames": ["e3.dcm"],
         "report_hash": "h1", "original_label": 1, "report_length": 100},  # same report as E1
        {"exam_id": "E4", "customer_id": "C2", "dicom_filenames": ["e4.dcm"],
         "report_hash": "h3", "original_label": 2, "report_length": 150},
    ]
    with open(out / "exam_registry.jsonl", "w") as f:
        for e in exams:
            f.write(json.dumps(e) + "\n")

    # Selected extractions (keyed by report_hash)
    extractions = [
        {"report_hash": "h1", "classification": "normal",
         "findings": {"cardiomegaly": {"status": "Negative"}},
         "extraction_model": "sonnet", "prompt_hash": "ph", "timestamp": "t"},
        {"report_hash": "h2", "classification": "abnormal",
         "findings": {"cardiomegaly": {"status": "Positive"}},
         "extraction_model": "sonnet", "prompt_hash": "ph", "timestamp": "t"},
        {"report_hash": "h3", "classification": "abnormal",
         "findings": {"cardiomegaly": {"status": "Uncertain"}},
         "extraction_model": "sonnet", "prompt_hash": "ph", "timestamp": "t"},
    ]
    with open(gt / "selected_extractions.jsonl", "w") as f:
        for e in extractions:
            f.write(json.dumps(e) + "\n")

    # Agreement report
    agreement = {
        "n_unique_reports": 3, "n_models": 2, "models": ["sonnet", "opus"],
        "classification_agreement_rate": 1.0,
        "per_finding_agreement_rate": {"cardiomegaly": 1.0},
        "mean_finding_agreement": 1.0,
        "n_any_disagreement": 0, "disagreement_report_hashes": [],
    }
    with open(gt / "agreement_report.json", "w") as f:
        json.dump(agreement, f)

    return {"output_dir": str(out), "gt_dir": str(gt)}


class TestJoinExtractionsToExams:
    def test_produces_one_row_per_exam(self, gt_inputs):
        labels = join_extractions_to_exams(gt_inputs["output_dir"])
        assert len(labels) == 4  # E1, E2, E3, E4

    def test_joins_on_report_hash(self, gt_inputs):
        labels = join_extractions_to_exams(gt_inputs["output_dir"])
        by_id = {l["exam_id"]: l for l in labels}
        # E1 and E3 share h1 -> both get "normal"
        assert by_id["E1"]["classification"] == "normal"
        assert by_id["E3"]["classification"] == "normal"
        assert by_id["E2"]["classification"] == "abnormal"

    def test_unmatched_exams_skipped(self, gt_inputs):
        # All exams have matching extractions -> 4 labels
        labels = join_extractions_to_exams(gt_inputs["output_dir"])
        assert len(labels) == 4


class TestBuildBalancedSet:
    def test_balances_abnormal_and_normal(self, gt_inputs):
        labels = join_extractions_to_exams(gt_inputs["output_dir"])
        balanced = build_balanced_set(labels, seed=42)
        abnormal = [l for l in balanced if l["classification"] == "abnormal"]
        normal = [l for l in balanced if l["classification"] == "normal"]
        assert len(abnormal) == len(normal)

    def test_deterministic_with_seed(self, gt_inputs):
        labels = join_extractions_to_exams(gt_inputs["output_dir"])
        b1 = build_balanced_set(labels, seed=42)
        b2 = build_balanced_set(labels, seed=42)
        assert [l["exam_id"] for l in b1] == [l["exam_id"] for l in b2]


class TestComputeStatistics:
    def test_includes_finding_prevalence(self, gt_inputs):
        labels = join_extractions_to_exams(gt_inputs["output_dir"])
        stats = compute_statistics(labels)
        assert "finding_prevalence" in stats
        assert "cardiomegaly" in stats["finding_prevalence"]

    def test_abnormal_rate(self, gt_inputs):
        labels = join_extractions_to_exams(gt_inputs["output_dir"])
        stats = compute_statistics(labels)
        # 2 abnormal out of 4
        assert stats["abnormal_rate_sonnet"] == 0.5


class TestCompareFlags:
    def test_agreement_when_matching(self, gt_inputs):
        labels = join_extractions_to_exams(gt_inputs["output_dir"])
        comparison = compare_flags(labels)
        # E1(normal,1), E2(abnormal,2), E3(normal,1) agree; E4(abnormal,2) agrees
        assert comparison["agreement"] == comparison["total"]

    def test_disagree_sonnet_abnormal(self):
        labels = [{"classification": "abnormal", "original_label": 1}]
        comparison = compare_flags(labels)
        assert comparison["disagree_sonnet_abnormal_flag_normal"] == 1

    def test_disagree_sonnet_normal(self):
        labels = [{"classification": "normal", "original_label": 2}]
        comparison = compare_flags(labels)
        assert comparison["disagree_sonnet_normal_flag_abnormal"] == 1
