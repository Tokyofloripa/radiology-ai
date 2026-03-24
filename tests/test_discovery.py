"""Tests for Tier 2 discovery — aggregation and promotion candidates."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cxr_mvp.discovery import (
    aggregate_discoveries,
    generate_discovery_report,
    _canonical_key,
)


@pytest.fixture
def extraction_dir(tmp_path) -> str:
    gt_dir = tmp_path / "reference_labels"
    gt_dir.mkdir()
    extractions = [
        {"report_hash": "h1", "other_findings": [
            {"name": "bronchiectasis", "original_term": "bronquiectasias",
             "status": "Positive", "confidence": "high",
             "evidence": "Bronquiectasias em lobos inferiores",
             "suggested_category": "pulmonary"},
        ]},
        {"report_hash": "h2", "other_findings": [
            {"name": "bronchiectasis", "original_term": "bronquiectasia",
             "status": "Positive", "confidence": "medium",
             "evidence": "Bronquiectasia cilíndrica",
             "suggested_category": "pulmonary"},
        ]},
        {"report_hash": "h3", "other_findings": [
            {"name": "pericardial_effusion", "original_term": "derrame pericárdico",
             "status": "Positive", "confidence": "high",
             "evidence": "Derrame pericárdico moderado",
             "suggested_category": "vascular"},
        ]},
        {"report_hash": "h4", "other_findings": []},
        {"report_hash": "h5", "other_findings": []},
    ]
    with open(gt_dir / "extractions_sonnet.jsonl", "w") as f:
        for e in extractions:
            f.write(json.dumps({**e, "classification": "abnormal",
                                "findings": {}, "extraction_model": "sonnet",
                                "prompt_hash": "ph", "timestamp": "t",
                                "study_quality": "adequate", "study_quality_flags": []}) + "\n")
    return str(gt_dir)


class TestAggregateDiscoveries:
    def test_counts_occurrences(self, extraction_dir):
        agg = aggregate_discoveries(extraction_dir)
        assert agg["bronchiectasis"]["count"] == 2
        assert agg["pericardial_effusion"]["count"] == 1

    def test_includes_sample_evidence(self, extraction_dir):
        agg = aggregate_discoveries(extraction_dir)
        assert "evidence" in agg["bronchiectasis"]["samples"][0]

    def test_includes_category(self, extraction_dir):
        agg = aggregate_discoveries(extraction_dir)
        assert agg["bronchiectasis"]["suggested_category"] == "pulmonary"


class TestGenerateDiscoveryReport:
    def test_produces_report(self, extraction_dir):
        report = generate_discovery_report(extraction_dir, total_reports=5)
        assert "tier2_findings_found" in report
        assert report["tier2_findings_found"] == 2

    def test_identifies_promotion_candidates(self, extraction_dir):
        # threshold 0.2 = 20% of 5 reports = 1 report min; bronchiectasis has 2
        report = generate_discovery_report(
            extraction_dir, total_reports=5, threshold=0.2, min_count=1,
        )
        assert "bronchiectasis" in report["promotion_candidates"]

    def test_below_threshold_not_promoted(self, extraction_dir):
        # threshold 0.5 = 50% of 5 = 2.5; pericardial_effusion has 1
        report = generate_discovery_report(
            extraction_dir, total_reports=5, threshold=0.5, min_count=2,
        )
        assert "pericardial_effusion" not in report["promotion_candidates"]


class TestCanonicalKey:
    def test_identical_names(self):
        assert _canonical_key("bronchiectasis") == _canonical_key("bronchiectasis")

    def test_word_order_swap(self):
        assert _canonical_key("convex_diaphragm") == _canonical_key("diaphragm_convexity")

    def test_suffix_variation(self):
        # Same root, different suffix (enlargement/enlarged)
        assert _canonical_key("hilar_enlargement") == _canonical_key("hilar_enlarged")
        # elevation/elevated
        assert _canonical_key("diaphragm_elevation") == _canonical_key("elevated_diaphragm")

    def test_different_findings_stay_different(self):
        assert _canonical_key("consolidation") != _canonical_key("congestion")
        assert _canonical_key("atelectasis") != _canonical_key("atherosclerosis")
        assert _canonical_key("aortic_aneurysm") != _canonical_key("aortic_atherosclerosis")

    def test_single_word(self):
        assert _canonical_key("bronchiectasis") == _canonical_key("bronchiectasis")

    def test_case_insensitive(self):
        assert _canonical_key("Hilar_Enlargement") == _canonical_key("hilar_enlargement")


class TestSynonymDedup:
    def test_merges_synonym_names(self, tmp_path):
        """convex_diaphragm and diaphragm_convexity should merge."""
        gt_dir = tmp_path / "reference_labels"
        gt_dir.mkdir()
        extractions = [
            {"report_hash": "h1", "other_findings": [
                {"name": "convex_diaphragm", "original_term": "Diafragma convexo",
                 "status": "Positive", "suggested_category": "structural"},
            ]},
            {"report_hash": "h2", "other_findings": [
                {"name": "diaphragm_convexity", "original_term": "Diafragma convexo",
                 "status": "Positive", "suggested_category": "structural"},
            ]},
            {"report_hash": "h3", "other_findings": [
                {"name": "convex_diaphragm", "original_term": "Diafragma convexo",
                 "status": "Positive", "suggested_category": "structural"},
            ]},
        ]
        with open(gt_dir / "extractions_sonnet.jsonl", "w") as f:
            for e in extractions:
                f.write(json.dumps({**e, "classification": "abnormal",
                                    "findings": {}, "extraction_model": "sonnet",
                                    "prompt_hash": "ph", "timestamp": "t",
                                    "study_quality": "adequate",
                                    "study_quality_flags": []}) + "\n")

        agg = aggregate_discoveries(str(gt_dir), synonym_path="/nonexistent.yaml")
        # Should merge into one entry with count=3 via stem dedup
        # The canonical name should be the most frequent raw name
        assert len(agg) == 1
        canonical = list(agg.keys())[0]
        assert agg[canonical]["count"] == 3
        assert canonical == "convex_diaphragm"  # most frequent (2 vs 1)

    def test_does_not_merge_different_findings(self, tmp_path):
        """Different findings should stay separate."""
        gt_dir = tmp_path / "reference_labels"
        gt_dir.mkdir()
        extractions = [
            {"report_hash": "h1", "other_findings": [
                {"name": "bronchiectasis", "original_term": "bronquiectasias",
                 "status": "Positive", "suggested_category": "pulmonary"},
                {"name": "pericardial_effusion", "original_term": "derrame pericárdico",
                 "status": "Positive", "suggested_category": "vascular"},
            ]},
        ]
        with open(gt_dir / "extractions_sonnet.jsonl", "w") as f:
            for e in extractions:
                f.write(json.dumps({**e, "classification": "abnormal",
                                    "findings": {}, "extraction_model": "sonnet",
                                    "prompt_hash": "ph", "timestamp": "t",
                                    "study_quality": "adequate",
                                    "study_quality_flags": []}) + "\n")

        agg = aggregate_discoveries(str(gt_dir))
        assert len(agg) == 2

    def test_merged_count_in_discovery_report(self, tmp_path):
        """Merged synonyms should have combined count for promotion."""
        gt_dir = tmp_path / "reference_labels"
        gt_dir.mkdir()
        extractions = [
            {"report_hash": f"h{i}", "other_findings": [
                {"name": "convex_diaphragm" if i % 2 == 0 else "diaphragm_convexity",
                 "original_term": "Diafragma convexo",
                 "status": "Positive", "suggested_category": "structural"},
            ]}
            for i in range(6)
        ]
        with open(gt_dir / "extractions_sonnet.jsonl", "w") as f:
            for e in extractions:
                f.write(json.dumps({**e, "classification": "abnormal",
                                    "findings": {}, "extraction_model": "sonnet",
                                    "prompt_hash": "ph", "timestamp": "t",
                                    "study_quality": "adequate",
                                    "study_quality_flags": []}) + "\n")

        report = generate_discovery_report(
            str(gt_dir), total_reports=10, threshold=0.3, min_count=3,
        )
        # 6 occurrences across 10 reports = 60% > 30% threshold
        # Without dedup: 3 + 3 — both might miss a higher threshold
        # With dedup: 6 — clearly above threshold
        assert len(report["promotion_candidates"]) == 1


class TestSynonymMap:
    def test_mapped_synonym_merged(self, tmp_path):
        """Synonym map merges known aliases before stem dedup."""
        gt_dir = tmp_path / "ground_truth"
        gt_dir.mkdir()
        # Write a synonym config
        syn_path = tmp_path / "synonyms.yaml"
        syn_path.write_text(yaml.dump({"synonyms": {
            "hilar_prominence": ["hilar_enlargement", "enlarged_hilum"]
        }}))

        extractions = [
            {"report_hash": "h1", "other_findings": [
                {"name": "hilar_enlargement", "original_term": "hilos proeminentes",
                 "status": "Positive", "suggested_category": "vascular"},
            ]},
            {"report_hash": "h2", "other_findings": [
                {"name": "hilar_prominence", "original_term": "proeminência hilar",
                 "status": "Positive", "suggested_category": "vascular"},
            ]},
            {"report_hash": "h3", "other_findings": [
                {"name": "enlarged_hilum", "original_term": "hilos aumentados",
                 "status": "Positive", "suggested_category": "vascular"},
            ]},
        ]
        with open(gt_dir / "extractions_sonnet.jsonl", "w") as f:
            for e in extractions:
                f.write(json.dumps({**e, "classification": "abnormal",
                                    "findings": {}, "extraction_model": "sonnet",
                                    "prompt_hash": "ph", "timestamp": "t",
                                    "study_quality": "adequate",
                                    "study_quality_flags": []}) + "\n")

        agg = aggregate_discoveries(str(gt_dir), synonym_path=str(syn_path))
        # All three should merge into hilar_prominence
        assert len(agg) == 1
        assert "hilar_prominence" in agg
        assert agg["hilar_prominence"]["count"] == 3

    def test_unmapped_falls_back_to_stem_dedup(self, tmp_path):
        """Unknown pairs still get deduplicated by stem fallback."""
        gt_dir = tmp_path / "ground_truth"
        gt_dir.mkdir()
        # Empty synonym map — no mappings
        syn_path = tmp_path / "synonyms.yaml"
        syn_path.write_text(yaml.dump({"synonyms": {}}))

        extractions = [
            {"report_hash": "h1", "other_findings": [
                {"name": "convex_diaphragm", "original_term": "Diafragma convexo",
                 "status": "Positive", "suggested_category": "structural"},
            ]},
            {"report_hash": "h2", "other_findings": [
                {"name": "diaphragm_convexity", "original_term": "Convexidade diafragma",
                 "status": "Positive", "suggested_category": "structural"},
            ]},
        ]
        with open(gt_dir / "extractions_sonnet.jsonl", "w") as f:
            for e in extractions:
                f.write(json.dumps({**e, "classification": "abnormal",
                                    "findings": {}, "extraction_model": "sonnet",
                                    "prompt_hash": "ph", "timestamp": "t",
                                    "study_quality": "adequate",
                                    "study_quality_flags": []}) + "\n")

        agg = aggregate_discoveries(str(gt_dir), synonym_path=str(syn_path))
        # Stem dedup should still merge these (convex_diaphr)
        assert len(agg) == 1

    def test_missing_synonym_file_no_error(self, tmp_path):
        """Missing synonym file should not crash — just skip synonym phase."""
        gt_dir = tmp_path / "ground_truth"
        gt_dir.mkdir()
        extractions = [
            {"report_hash": "h1", "other_findings": [
                {"name": "bronchiectasis", "original_term": "bronquiectasias",
                 "status": "Positive", "suggested_category": "pulmonary"},
            ]},
        ]
        with open(gt_dir / "extractions_sonnet.jsonl", "w") as f:
            for e in extractions:
                f.write(json.dumps({**e, "classification": "abnormal",
                                    "findings": {}, "extraction_model": "sonnet",
                                    "prompt_hash": "ph", "timestamp": "t",
                                    "study_quality": "adequate",
                                    "study_quality_flags": []}) + "\n")

        # Point to non-existent file
        agg = aggregate_discoveries(str(gt_dir), synonym_path="/nonexistent/path.yaml")
        assert len(agg) == 1
        assert agg["bronchiectasis"]["count"] == 1
