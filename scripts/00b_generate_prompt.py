#!/usr/bin/env python3
"""Stage 0.5: Generate extraction prompt from findings_cxr.yaml.
Thin CLI wrapper — all logic in src/cxr_mvp/prompt_generator.py."""
from __future__ import annotations

import argparse
from pathlib import Path

from cxr_mvp.prompt_generator import generate_prompt, prompt_hash


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 0.5: Generate prompt")
    parser.add_argument("--config", default="config/findings_cxr.yaml")
    parser.add_argument("--output", default="config/prompts/extract_cxr_pt.txt")
    args = parser.parse_args()

    text = generate_prompt(args.config)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(text)

    h = prompt_hash(args.config)
    print(f"Prompt generated: {args.output}")
    print(f"  Hash: {h}")
    print(f"  Length: {len(text):,} chars")

    # Count findings in prompt
    from cxr_mvp.config import load_findings_config
    config = load_findings_config(args.config)
    print(f"  Findings: {len(config.findings)}")


if __name__ == "__main__":
    main()
