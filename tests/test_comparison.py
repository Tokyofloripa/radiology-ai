"""Tests for inter-model comparison and agreement scoring."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cxr_mvp.comparison import arbitrate_finding, compare_extractions, select_primary


@pytest.fixture
def comparison_dir(tmp_path) -> str:
    """Directory with sonnet + opus extractions (1 disagreement on bbb/effusion)."""
    gt_dir = tmp_path / "reference_labels"
    gt_dir.mkdir()

    sonnet = [
        {"report_hash": "aaa", "classification": "normal",
         "findings": {"cardiomegaly": {"status": "Negative"}, "effusion": {"status": "Absent"}},
         "extraction_model": "sonnet", "prompt_hash": "ph", "timestamp": "t"},
        {"report_hash": "bbb", "classification": "abnormal",
         "findings": {"cardiomegaly": {"status": "Positive"}, "effusion": {"status": "Positive"}},
         "extraction_model": "sonnet", "prompt_hash": "ph", "timestamp": "t"},
    ]
    opus = [
        {"report_hash": "aaa", "classification": "normal",
         "findings": {"cardiomegaly": {"status": "Negative"}, "effusion": {"status": "Absent"}},
         "extraction_model": "opus", "prompt_hash": "ph", "timestamp": "t"},
        {"report_hash": "bbb", "classification": "abnormal",
         "findings": {"cardiomegaly": {"status": "Positive"}, "effusion": {"status": "Uncertain"}},
         "extraction_model": "opus", "prompt_hash": "ph", "timestamp": "t"},
    ]

    with open(gt_dir / "extractions_sonnet.jsonl", "w") as f:
        for line in sonnet:
            f.write(json.dumps(line) + "\n")
    with open(gt_dir / "extractions_opus.jsonl", "w") as f:
        for line in opus:
            f.write(json.dumps(line) + "\n")

    return str(gt_dir)


class TestCompareExtractions:
    def test_returns_agreement_report(self, comparison_dir):
        result = compare_extractions(comparison_dir)
        assert "models" in result
        assert "classification_agreement_rate" in result
        assert result["n_unique_reports"] == 2

    def test_detects_models(self, comparison_dir):
        result = compare_extractions(comparison_dir)
        assert set(result["models"]) == {"sonnet", "opus"}

    def test_classification_agreement(self, comparison_dir):
        result = compare_extractions(comparison_dir)
        # Both models agree on classification for both reports
        assert result["classification_agreement_rate"] == 1.0

    def test_finding_disagreement_detected(self, comparison_dir):
        result = compare_extractions(comparison_dir)
        # bbb has effusion disagreement (Positive vs Uncertain)
        assert result["n_any_disagreement"] >= 1

    def test_writes_disagreements_file(self, comparison_dir):
        compare_extractions(comparison_dir)
        disagreements_path = Path(comparison_dir) / "disagreements.jsonl"
        assert disagreements_path.exists()
        with open(disagreements_path) as f:
            lines = [json.loads(l) for l in f]
        assert len(lines) >= 1
        assert lines[0]["report_hash"] == "bbb"

    def test_writes_agreement_report_file(self, comparison_dir):
        compare_extractions(comparison_dir)
        report_path = Path(comparison_dir) / "agreement_report.json"
        assert report_path.exists()


class TestCompareExtractionsV2:
    def test_ignores_other_findings_in_agreement(self, tmp_path):
        """Tier 2 other_findings should not affect agreement scoring."""
        gt_dir = tmp_path / "reference_labels"
        gt_dir.mkdir()

        # Same Tier 1 findings, different other_findings
        sonnet = [
            {"report_hash": "aaa", "classification": "abnormal",
             "findings": {"cardiomegaly": {"status": "Positive"}},
             "other_findings": [{"name": "bronchiectasis", "status": "Positive"}],
             "extraction_model": "sonnet", "prompt_hash": "ph", "timestamp": "t"},
        ]
        opus = [
            {"report_hash": "aaa", "classification": "abnormal",
             "findings": {"cardiomegaly": {"status": "Positive"}},
             "other_findings": [{"name": "pericardial_effusion", "status": "Positive"}],
             "extraction_model": "opus", "prompt_hash": "ph", "timestamp": "t"},
        ]

        with open(gt_dir / "extractions_sonnet.jsonl", "w") as f:
            f.write(json.dumps(sonnet[0]) + "\n")
        with open(gt_dir / "extractions_opus.jsonl", "w") as f:
            f.write(json.dumps(opus[0]) + "\n")

        result = compare_extractions(str(gt_dir))
        # Tier 1 findings agree perfectly — Tier 2 differences should NOT cause disagreement
        assert result["n_any_disagreement"] == 0
        assert result["mean_finding_agreement"] == 1.0

    def test_excludes_backup_files(self, tmp_path):
        """Backup files like extractions_sonnet_v1_backup.jsonl should be excluded."""
        gt_dir = tmp_path / "reference_labels"
        gt_dir.mkdir()

        sonnet = [
            {"report_hash": "aaa", "classification": "normal",
             "findings": {"cardiomegaly": {"status": "Negative"}},
             "extraction_model": "sonnet", "prompt_hash": "ph", "timestamp": "t"},
        ]
        # A backup file that should be ignored
        backup = [
            {"report_hash": "aaa", "classification": "abnormal",
             "findings": {"cardiomegaly": {"status": "Positive"}},
             "extraction_model": "sonnet_v1_backup", "prompt_hash": "ph", "timestamp": "t"},
        ]

        with open(gt_dir / "extractions_sonnet.jsonl", "w") as f:
            f.write(json.dumps(sonnet[0]) + "\n")
        with open(gt_dir / "extractions_sonnet_v1_backup.jsonl", "w") as f:
            f.write(json.dumps(backup[0]) + "\n")

        result = compare_extractions(str(gt_dir))
        # Should only detect 1 model (sonnet), not the backup
        assert result["n_models"] == 1
        assert "sonnet_v1_backup" not in result["models"]


class TestArbitrateFinding:
    def test_both_agree_accepted(self):
        status, review = arbitrate_finding("Positive", "Positive")
        assert status == "Positive"
        assert review is False

    def test_positive_vs_uncertain_etiologic(self):
        """Etiologic finding: Positive vs Uncertain -> Uncertain (conservative)."""
        status, review = arbitrate_finding("Positive", "Uncertain", finding_type="etiologic")
        assert status == "Uncertain"
        assert review is False

    def test_positive_vs_uncertain_descriptive(self):
        """Descriptive finding: Positive vs Uncertain -> needs review."""
        status, review = arbitrate_finding("Positive", "Uncertain", finding_type="descriptive")
        assert review is True

    def test_absent_vs_positive_review(self):
        """Absent vs Positive is a major disagreement -> review."""
        status, review = arbitrate_finding("Absent", "Positive")
        assert review is True

    def test_negative_vs_absent_accepted(self):
        """Negative vs Absent is minor -- both mean 'not there'."""
        status, review = arbitrate_finding("Negative", "Absent")
        assert review is False

    def test_not_assessable_wins(self):
        """Not_Assessable vs Negative -> Not_Assessable (conservative)."""
        status, review = arbitrate_finding("Not_Assessable", "Negative")
        assert status == "Not_Assessable"
        assert review is False

    def test_symmetric(self):
        """Order shouldn't matter."""
        s1, r1 = arbitrate_finding("Positive", "Uncertain", finding_type="etiologic")
        s2, r2 = arbitrate_finding("Uncertain", "Positive", finding_type="etiologic")
        assert s1 == s2
        assert r1 == r2


class TestHierarchicalAgreement:
    def test_child_positive_matches_parent_positive(self, tmp_path):
        """If one model says consolidation=Positive and another says
        lung_opacity=Positive, this should NOT count as a disagreement
        on lung_opacity (parent is covered by child)."""
        gt_dir = tmp_path / "reference_labels"
        gt_dir.mkdir()

        # Sonnet: consolidation=Positive, lung_opacity=Absent
        # Opus: consolidation=Absent, lung_opacity=Positive
        sonnet = [{"report_hash": "aaa", "classification": "abnormal",
                    "findings": {
                        "consolidation": {"status": "Positive"},
                        "lung_opacity": {"status": "Absent"},
                    },
                    "extraction_model": "sonnet", "prompt_hash": "ph", "timestamp": "t"}]
        opus = [{"report_hash": "aaa", "classification": "abnormal",
                 "findings": {
                     "consolidation": {"status": "Absent"},
                     "lung_opacity": {"status": "Positive"},
                 },
                 "extraction_model": "opus", "prompt_hash": "ph", "timestamp": "t"}]

        with open(gt_dir / "extractions_sonnet.jsonl", "w") as f:
            f.write(json.dumps(sonnet[0]) + "\n")
        with open(gt_dir / "extractions_opus.jsonl", "w") as f:
            f.write(json.dumps(opus[0]) + "\n")

        result = compare_extractions(str(gt_dir))
        # With hierarchical roll-up, consolidation(Positive) covers lung_opacity
        # So lung_opacity should NOT be in disagreements
        # Only consolidation disagrees (Positive vs Absent)
        disag_path = gt_dir / "disagreements.jsonl"
        with open(disag_path) as f:
            disag = [json.loads(l) for l in f]
        if disag:
            # lung_opacity should not be flagged as disagreement
            for d in disag:
                disagreeing = d.get("disagreement_findings", [])
                assert "lung_opacity" not in disagreeing, \
                    "lung_opacity should not disagree when child consolidation is Positive"


class TestSelectPrimary:
    def test_creates_selected_extractions(self, comparison_dir):
        compare_extractions(comparison_dir)  # must run first to detect models
        select_primary(comparison_dir, primary_model="sonnet")
        selected = Path(comparison_dir) / "selected_extractions.jsonl"
        assert selected.exists()
        with open(selected) as f:
            lines = [json.loads(l) for l in f]
        assert len(lines) == 2
        assert all(l["extraction_model"] == "sonnet" for l in lines)
