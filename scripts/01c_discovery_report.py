#!/usr/bin/env python3
"""Stage 1.75: Generate Tier 2 discovery report.
Thin CLI wrapper — all logic in src/cxr_mvp/discovery.py."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cxr_mvp.discovery import generate_discovery_report
from cxr_mvp.config import load_findings_config

OUTPUT_DIR = "output/reference_labels"


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1.75: Discovery report")
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--total-reports", type=int, required=True)
    parser.add_argument("--config", default="config/findings_cxr.yaml")
    args = parser.parse_args()

    config = load_findings_config(args.config)

    report = generate_discovery_report(
        args.output_dir,
        total_reports=args.total_reports,
        threshold=config.discovery_threshold,
        min_count=config.discovery_min_count,
    )

    report_path = Path(args.output_dir) / "discovery_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n{'='*60}")
    print(f"DISCOVERY REPORT")
    print(f"{'='*60}")
    print(f"  Tier 2 findings discovered: {report['tier2_findings_found']}")
    print(f"  Promotion candidates: {len(report['promotion_candidates'])}")
    for name in report["promotion_candidates"]:
        d = report["all_discoveries"][name]
        print(f"    {name}: {d['count']} occurrences ({d['prevalence']:.1%})")
    print(f"\n-> {report_path}")


if __name__ == "__main__":
    main()
