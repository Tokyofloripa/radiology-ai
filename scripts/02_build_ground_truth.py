#!/usr/bin/env python3
"""Stage 2: Build ground truth — join, compare flags, balance, compute stats.
Thin CLI wrapper — all logic in src/cxr_mvp/reference_labels.py."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from cxr_mvp.reference_labels import (
    join_extractions_to_exams,
    build_balanced_set,
    compute_statistics,
    compare_flags,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 2: Build ground truth")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ratio", type=float, default=1.0)
    args = parser.parse_args()

    gt_dir = Path(args.output_dir) / "reference_labels"
    gt_dir.mkdir(parents=True, exist_ok=True)

    # JOIN
    labels = join_extractions_to_exams(args.output_dir)
    with open(gt_dir / "labels.jsonl", "w") as f:
        for l in labels:
            f.write(json.dumps(l, default=str) + "\n")
    print(f"Labeled exams: {len(labels):,}")

    # FLAG COMPARISON
    comparison = compare_flags(labels)
    with open(gt_dir / "flag_comparison.json", "w") as f:
        json.dump(comparison, f, indent=2)
    print(f"Flag agreement: {comparison['agreement_rate']:.1%}")

    # BALANCE
    balanced = build_balanced_set(labels, seed=args.seed, ratio=args.ratio)
    fieldnames = ["exam_id", "customer_id", "classification", "dicom_filenames",
                   "findings_json", "original_label", "report_hash",
                   "inter_model_agreement", "has_disagreement"]
    with open(gt_dir / "balanced.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for l in balanced:
            writer.writerow({
                "exam_id": l["exam_id"],
                "customer_id": l["customer_id"],
                "classification": l["classification"],
                "dicom_filenames": json.dumps(l["dicom_filenames"]),
                "findings_json": json.dumps(l["findings"]),
                "original_label": l["original_label"],
                "report_hash": l["report_hash"],
                "inter_model_agreement": l.get("inter_model_agreement", 1.0),
                "has_disagreement": l.get("has_disagreement", False),
            })
    print(f"Balanced set: {len(balanced):,}")

    # STATISTICS
    stats = compute_statistics(labels)
    stats["balanced_size"] = len(balanced)
    with open(gt_dir / "statistics.json", "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\n-> {gt_dir}/labels.jsonl ({len(labels):,})")
    print(f"-> {gt_dir}/flag_comparison.json")
    print(f"-> {gt_dir}/balanced.csv ({len(balanced):,})")
    print(f"-> {gt_dir}/statistics.json")


if __name__ == "__main__":
    main()
