"""Stage 2: Ground truth assembly — join, flag comparison, balance, statistics.

Reads selected_extractions.jsonl + exam_registry.jsonl + agreement_report.json.
Produces labels.jsonl, flag_comparison.json, balanced.csv, statistics.json."""
from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path


def join_extractions_to_exams(output_dir: str) -> list[dict]:
    """Join extractions (by report_hash) back to exam records."""
    # Load exam registry
    exams = []
    with open(Path(output_dir) / "exam_registry.jsonl") as f:
        for line in f:
            exams.append(json.loads(line))

    # Load selected extractions (keyed by report_hash)
    extractions: dict[str, dict] = {}
    gt_dir = Path(output_dir) / "reference_labels"
    with open(gt_dir / "selected_extractions.jsonl") as f:
        for line in f:
            r = json.loads(line)
            extractions[r["report_hash"]] = r

    # Load agreement report (optional)
    agreement: dict = {}
    agreement_path = gt_dir / "agreement_report.json"
    if agreement_path.exists():
        with open(agreement_path) as f:
            agreement = json.load(f)

    disagreement_hashes = set(agreement.get("disagreement_report_hashes", []))

    # Load per-report agreement scores (if available)
    per_report_path = gt_dir / "per_report_agreement.json"
    per_report_scores: dict[str, float] = {}
    if per_report_path.exists():
        with open(per_report_path) as f:
            per_report_scores = json.load(f)

    # Join
    labels = []
    for exam in exams:
        extraction = extractions.get(exam["report_hash"])
        if not extraction:
            continue

        labels.append({
            "exam_id": exam["exam_id"],
            "customer_id": exam["customer_id"],
            "dicom_filenames": exam["dicom_filenames"],
            "classification": extraction["classification"],
            "findings": extraction["findings"],
            "original_label": exam["original_label"],
            "report_hash": exam["report_hash"],
            "extraction_model": extraction["extraction_model"],
            "prompt_hash": extraction["prompt_hash"],
            "inter_model_agreement": per_report_scores.get(
                exam["report_hash"], agreement.get("mean_finding_agreement", 1.0)
            ),
            "has_disagreement": exam["report_hash"] in disagreement_hashes,
            "primary_model": extraction["extraction_model"],
        })

    return labels


def build_balanced_set(
    labels: list[dict],
    seed: int = 42,
    ratio: float = 1.0,
) -> list[dict]:
    """Build balanced evaluation set: all abnormals + equal random normals."""
    rng = random.Random(seed)

    abnormals = [l for l in labels if l["classification"] == "abnormal"]
    normals = [l for l in labels if l["classification"] == "normal"]

    n_sample = min(int(len(abnormals) * ratio), len(normals))
    sampled_normals = rng.sample(normals, n_sample)

    balanced = abnormals + sampled_normals
    rng.shuffle(balanced)
    return balanced


def compute_statistics(labels: list[dict]) -> dict:
    """Compute dataset statistics — finding prevalence, abnormal rates, etc."""
    abnormals = [l for l in labels if l["classification"] == "abnormal"]
    normals = [l for l in labels if l["classification"] == "normal"]

    finding_counts: Counter = Counter()
    for l in labels:
        for finding, data in l.get("findings", {}).items():
            if isinstance(data, dict) and data.get("status") == "Positive":
                finding_counts[finding] += 1

    # Priority distribution
    priority_counts = Counter(l.get("priority_level", "NONE") for l in labels)

    # Study quality
    quality_counts = Counter(l.get("study_quality", "adequate") for l in labels)
    quality_flag_counts: Counter = Counter()
    for l in labels:
        for flag in l.get("study_quality_flags", []):
            quality_flag_counts[flag] += 1

    # Needs review
    needs_review_count = sum(1 for l in labels if l.get("needs_review", False))

    return {
        "total_labeled": len(labels),
        "total_abnormal": len(abnormals),
        "total_normal": len(normals),
        "abnormal_rate_sonnet": round(len(abnormals) / len(labels), 4) if labels else 0,
        "abnormal_rate_original": round(
            sum(1 for l in labels if l.get("original_label") == 2) / len(labels), 4
        ) if labels else 0,
        "customers": len(set(l["customer_id"] for l in labels)),
        "finding_prevalence": {
            finding: {"count": count, "rate": round(count / len(labels), 4)}
            for finding, count in finding_counts.most_common()
        },
        "priority_distribution": dict(priority_counts),
        "study_quality": {
            "adequate": quality_counts.get("adequate", 0),
            "suboptimal": quality_counts.get("suboptimal", 0),
            "reasons": dict(quality_flag_counts),
        },
        "needs_review": needs_review_count,
    }


def compare_flags(labels: list[dict]) -> dict:
    """Compare Sonnet classification vs original CSV label flag."""
    agree, disagree_sonnet_normal, disagree_sonnet_abnormal = 0, 0, 0

    for l in labels:
        original = "normal" if l.get("original_label") == 1 else "abnormal"
        sonnet = l["classification"]
        if original == sonnet:
            agree += 1
        elif sonnet == "normal":
            disagree_sonnet_normal += 1
        else:
            disagree_sonnet_abnormal += 1

    return {
        "total": len(labels),
        "agreement": agree,
        "agreement_rate": round(agree / len(labels), 4) if labels else 0,
        "disagree_sonnet_normal_flag_abnormal": disagree_sonnet_normal,
        "disagree_sonnet_abnormal_flag_normal": disagree_sonnet_abnormal,
    }
