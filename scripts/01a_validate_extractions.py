#!/usr/bin/env python3
"""Stage 1.5: Validate extractions — ghost-abnormal check, priority computation.
Thin CLI wrapper — all logic in src/cxr_mvp/validation.py."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from cxr_mvp.models import ExtractionResult
from cxr_mvp.validation import validate_extraction

OUTPUT_DIR = "output/reference_labels"


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1.5: Validate extractions")
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--models", nargs="+", help="Validate specific models")
    args = parser.parse_args()

    gt_dir = Path(args.output_dir)

    # Find extraction files
    patterns = [f"extractions_{m}.jsonl" for m in args.models] if args.models else ["extractions_*.jsonl"]
    extraction_files = []
    for p in patterns:
        extraction_files.extend(gt_dir.glob(p))

    # Exclude backup files
    extraction_files = [f for f in extraction_files if "backup" not in f.name]

    if not extraction_files:
        print("No extraction files found.")
        return

    # Clear needs_review file for idempotent runs
    review_path = gt_dir / "needs_review.jsonl"
    if review_path.exists():
        review_path.unlink()

    for ext_file in sorted(extraction_files):
        model_name = ext_file.stem.replace("extractions_", "")
        print(f"\nValidating: {model_name}")

        results = []
        with open(ext_file) as f:
            for line in f:
                data = json.loads(line)
                result = ExtractionResult(**data)
                results.append(result)

        validated = [validate_extraction(r) for r in results]

        # Write validated file
        val_path = gt_dir / f"validated_{model_name}.jsonl"
        with open(val_path, "w") as f:
            for v in validated:
                f.write(json.dumps(asdict(v)) + "\n")

        # Write needs_review file
        needs_review = [v for v in validated if v.needs_review]
        if needs_review:
            review_path = gt_dir / "needs_review.jsonl"
            with open(review_path, "a") as f:
                for v in needs_review:
                    f.write(json.dumps({
                        "report_hash": v.report_hash,
                        "model": v.extraction_model,
                        "classification": v.classification,
                        "review_reasons": v.review_reasons,
                        "original_classification": v.original_classification,
                    }) + "\n")

        # Summary
        priorities = Counter(v.priority_level for v in validated)
        print(f"  Total: {len(validated)}")
        print(f"  Priority: {dict(priorities)}")
        print(f"  Needs review: {len(needs_review)}")
        upgrades = sum(1 for v in validated if "critical_finding_override" in v.review_reasons)
        ghosts = sum(1 for v in validated if "no_supporting_findings" in v.review_reasons)
        print(f"  Upgrades (normal->abnormal): {upgrades}")
        print(f"  Ghost abnormals: {ghosts}")
        print(f"  -> {val_path}")


if __name__ == "__main__":
    main()
