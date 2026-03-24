"""Tier 2 discovery — aggregate other_findings across extractions.

Reads extractions_{model}.jsonl, groups other_findings by name,
computes prevalence, identifies promotion candidates.
Deduplicates synonym names via word-stem canonical keys."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def _canonical_key(name: str) -> str:
    """Canonical key for Tier 2 name deduplication.

    Takes the first 6 chars of each word as a stem, sorts alphabetically.
    This merges word-order and suffix variations:
      convex_diaphragm / diaphragm_convexity → convex_diaphr
      hilar_enlargement / enlarged_hilum     → enlarg_hilar
    But keeps genuinely different findings separate:
      consolidation / congestion             → consol ≠ conges
      aortic_aneurysm / aortic_atherosclerosis → aneury_aortic ≠ aortic_athers
    """
    parts = name.lower().replace("-", "_").split("_")
    stems = sorted(p[:6] for p in parts if p)
    return "_".join(stems)


def aggregate_discoveries(
    output_dir: str,
    synonym_path: str = "config/tier2_synonyms.yaml",
) -> dict[str, dict]:
    """Aggregate all other_findings across extraction files.

    Deduplicates synonym names via word-stem canonical keys.
    Returns {canonical_name: {count, suggested_category, original_terms, samples}}"""
    # Phase 1: collect raw counts per name
    raw_agg: dict[str, dict] = defaultdict(lambda: {
        "count": 0,
        "suggested_category": "other",
        "original_terms": set(),
        "samples": [],
    })

    for path in Path(output_dir).glob("extractions_*.jsonl"):
        with open(path) as f:
            for line in f:
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for finding in data.get("other_findings", []):
                    name = finding.get("name", "unknown")
                    raw_agg[name]["count"] += 1
                    raw_agg[name]["suggested_category"] = finding.get("suggested_category", "other")
                    raw_agg[name]["original_terms"].add(finding.get("original_term", ""))
                    if len(raw_agg[name]["samples"]) < 3:
                        raw_agg[name]["samples"].append({
                            "report_hash": data.get("report_hash", ""),
                            "evidence": finding.get("evidence", ""),
                            "status": finding.get("status", ""),
                        })

    # Phase 1.5: apply synonym map (deterministic, before stem dedup)
    from cxr_mvp.config import load_synonym_map
    syn_map = load_synonym_map(synonym_path)

    # Remap raw names to canonical via synonym map
    remapped: dict[str, dict] = defaultdict(lambda: {
        "count": 0,
        "suggested_category": "other",
        "original_terms": set(),
        "samples": [],
    })
    for name, data in raw_agg.items():
        canonical = syn_map.get(name, name)  # map alias → canonical, or keep as-is
        remapped[canonical]["count"] += data["count"]
        remapped[canonical]["suggested_category"] = data["suggested_category"]
        remapped[canonical]["original_terms"].update(data["original_terms"])
        remaining = 3 - len(remapped[canonical]["samples"])
        if remaining > 0:
            remapped[canonical]["samples"].extend(data["samples"][:remaining])

    raw_agg = remapped

    # Phase 2: merge synonyms by canonical key (stem dedup fallback)
    # Group raw names by their canonical key
    key_to_names: dict[str, list[str]] = defaultdict(list)
    for name in raw_agg:
        key_to_names[_canonical_key(name)].append(name)

    # Pick the most frequent raw name as canonical, merge data
    merged: dict[str, dict] = {}
    for key, names in key_to_names.items():
        # Sort by count descending — most frequent name wins
        names.sort(key=lambda n: -raw_agg[n]["count"])
        canonical_name = names[0]

        combined = {
            "count": 0,
            "suggested_category": raw_agg[canonical_name]["suggested_category"],
            "original_terms": set(),
            "samples": [],
        }
        for name in names:
            combined["count"] += raw_agg[name]["count"]
            combined["original_terms"].update(raw_agg[name]["original_terms"])
            remaining = 3 - len(combined["samples"])
            if remaining > 0:
                combined["samples"].extend(raw_agg[name]["samples"][:remaining])

        merged[canonical_name] = combined

    # Convert sets to lists for JSON serialization
    return {
        name: {**data, "original_terms": sorted(data["original_terms"])}
        for name, data in merged.items()
    }


def generate_discovery_report(
    output_dir: str,
    total_reports: int,
    threshold: float = 0.02,
    min_count: int = 10,
    synonym_path: str = "config/tier2_synonyms.yaml",
) -> dict:
    """Generate discovery report with promotion candidates."""
    agg = aggregate_discoveries(output_dir, synonym_path=synonym_path)

    candidates = []
    for name, data in agg.items():
        prevalence = data["count"] / total_reports if total_reports > 0 else 0
        if prevalence >= threshold and data["count"] >= min_count:
            candidates.append(name)

    return {
        "tier2_findings_found": len(agg),
        "total_reports_analyzed": total_reports,
        "promotion_threshold": threshold,
        "min_absolute_count": min_count,
        "promotion_candidates": sorted(candidates),
        "all_discoveries": {
            name: {
                "count": data["count"],
                "prevalence": round(data["count"] / total_reports, 4) if total_reports > 0 else 0,
                "suggested_category": data["suggested_category"],
                "original_terms": data["original_terms"],
                "samples": data["samples"],
            }
            for name, data in sorted(agg.items(), key=lambda x: -x[1]["count"])
        },
    }
