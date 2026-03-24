#!/usr/bin/env python3
"""Stage 1: Extract labels from Portuguese reports via N extraction models.
Thin CLI wrapper — all logic in src/cxr_mvp/extractors/."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cxr_mvp.extractors.registry import load_extraction_backends
from cxr_mvp.models import UniqueReport

REPORTS_PATH = "output/unique_reports.jsonl"
OUTPUT_DIR = "output/reference_labels"
CONFIG_PATH = "config/extraction_models.yaml"


def load_unique_reports(path: str, limit: int = 0) -> list[UniqueReport]:
    reports = []
    with open(path) as f:
        for line in f:
            data = json.loads(line)
            reports.append(UniqueReport(**data))
    if limit > 0:
        reports = reports[:limit]
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1: Extract labels")
    parser.add_argument("command", choices=["run", "status", "download"])
    parser.add_argument("--models", nargs="+", help="Run specific models")
    parser.add_argument("--limit", type=int, default=0, help="Limit reports (forces sync)")
    parser.add_argument("--config", default=CONFIG_PATH)
    parser.add_argument("--reports", default=REPORTS_PATH)
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--concurrency", type=int, default=1,
                        help="Concurrent API calls (default 1=sync, 20 recommended)")
    args = parser.parse_args()

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    backends = load_extraction_backends(args.config)
    if args.models:
        backends = [b for b in backends if b.name() in args.models]

    if not backends:
        print("No backends available. Check config and installed SDKs.")
        return

    if args.command == "run":
        reports = load_unique_reports(args.reports, args.limit)
        # Load prompt from config
        import yaml
        with open(args.config) as f:
            config = yaml.safe_load(f)
        prompt_path = config.get("prompt_template", "config/prompts/extract_cxr_pt.txt")
        prompt = Path(prompt_path).read_text()

        # Check prompt staleness
        try:
            from cxr_mvp.prompt_generator import prompt_hash
            import hashlib
            expected_hash = prompt_hash()
            actual_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
            if expected_hash != actual_hash:
                print(f"\n  WARNING: Prompt file is STALE!")
                print(f"  File hash:     {actual_hash}")
                print(f"  Expected hash: {expected_hash}")
                print(f"  Run: PYTHONPATH=src python3 scripts/00b_generate_prompt.py")
                print()
        except Exception:
            pass  # Don't block extraction if hash check fails

        print(f"Reports: {len(reports):,} | Models: {', '.join(b.name() for b in backends)}")

        # Emit run manifest
        from cxr_mvp.run_manifest import generate_run_manifest
        manifest = generate_run_manifest(
            models=[b.name() for b in backends],
        )
        manifest_path = Path(args.output_dir) / "run_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"Run manifest: {manifest_path} (run_id={manifest['run_id']})")

        for backend in backends:
            print(f"\n{'='*60}")
            print(f"Extracting with: {backend.name()} ({backend.version()})")
            if args.concurrency > 1:
                print(f"Mode: async concurrent ({args.concurrency} parallel)")
            else:
                print(f"Mode: sync (sequential)")
            print(f"{'='*60}")

            if args.concurrency > 1:
                import asyncio
                results = asyncio.run(
                    backend.extract_async(reports, prompt=prompt,
                                          output_dir=args.output_dir,
                                          concurrency=args.concurrency)
                )
            else:
                results = backend.extract(reports, prompt=prompt,
                                          output_dir=args.output_dir)

            print(f"  Completed: {len(results):,} extractions")

    elif args.command == "status":
        print("Batch status checking — not yet implemented")

    elif args.command == "download":
        print("Batch download — not yet implemented")


if __name__ == "__main__":
    main()
