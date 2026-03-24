#!/usr/bin/env python3
"""Stage 1b: Compare extraction results across models.
Thin CLI wrapper — all logic in src/cxr_mvp/comparison.py."""
from __future__ import annotations

import argparse

from cxr_mvp.comparison import compare_extractions, select_primary

OUTPUT_DIR = "output/reference_labels"


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1b: Compare extractions")
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--primary", default=None, help="Primary model name (default: first)")
    args = parser.parse_args()

    results = compare_extractions(args.output_dir)

    print(f"\n{'='*60}")
    print(f"INTER-MODEL AGREEMENT")
    print(f"{'='*60}")
    print(f"  Models: {', '.join(results['models'])}")
    print(f"  Reports compared: {results['n_unique_reports']:,}")
    print(f"  Classification agreement: {results['classification_agreement_rate']:.1%}")
    print(f"  Mean finding agreement: {results['mean_finding_agreement']:.1%}")
    print(f"  Reports with ANY disagreement: {results['n_any_disagreement']:,}")

    select_primary(args.output_dir, primary_model=args.primary)

    print(f"\n-> {args.output_dir}/agreement_report.json")
    print(f"-> {args.output_dir}/disagreements.jsonl")
    print(f"-> {args.output_dir}/selected_extractions.jsonl")


if __name__ == "__main__":
    main()
