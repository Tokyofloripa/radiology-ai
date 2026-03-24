#!/usr/bin/env python3
"""Stage 0: Ingest ListaLLM.csv -> exam_registry.jsonl + unique_reports.jsonl.
Thin CLI wrapper — all logic in src/cxr_mvp/ingest.py."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cxr_mvp.ingest import ingest_csv


def main(input_path: str = "ListaLLM.csv", output_dir: str = "output") -> None:
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    exams, reports, errors = ingest_csv(input_path)

    # Write exam registry
    registry_path = f"{output_dir}/exam_registry.jsonl"
    with open(registry_path, "w") as f:
        for e in exams:
            f.write(json.dumps({
                "exam_id": e.exam_id,
                "customer_id": e.customer_id,
                "dicom_filenames": e.dicom_filenames,
                "report_hash": e.report_hash,
                "original_label": e.original_label,
                "report_length": e.report_length,
            }) + "\n")

    # Write unique reports
    reports_path = f"{output_dir}/unique_reports.jsonl"
    with open(reports_path, "w") as f:
        for r in reports:
            f.write(json.dumps({
                "report_hash": r.report_hash,
                "report_text": r.report_text,
                "exam_count": r.exam_count,
                "sample_exam_id": r.sample_exam_id,
            }) + "\n")

    # Write errors
    if errors:
        errors_path = f"{output_dir}/ingest_errors.jsonl"
        with open(errors_path, "w") as f:
            for e in errors:
                f.write(json.dumps(e) + "\n")

    # Summary
    print(f"{'='*60}")
    print(f"Ingestion complete")
    print(f"  Unique exams:   {len(exams):,}")
    print(f"  Unique reports: {len(reports):,}")
    print(f"  Rejected:       {len(errors):,}")
    customers = len(set(e.customer_id for e in exams))
    print(f"  Customers:      {customers:,}")
    print(f"\n-> {registry_path} ({len(exams):,} exams)")
    print(f"-> {reports_path} ({len(reports):,} unique reports)")
    if errors:
        print(f"-> {output_dir}/ingest_errors.jsonl ({len(errors):,} rejects)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 0: Ingest CSV")
    parser.add_argument("--input", default="ListaLLM.csv", help="Path to CSV file")
    parser.add_argument("--output-dir", default="output", help="Output directory")
    args = parser.parse_args()
    main(input_path=args.input, output_dir=args.output_dir)
