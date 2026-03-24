"""Centralized config loader for findings_cxr.yaml v2.

Single point of YAML parsing. All consumers import from here —
no raw yaml.safe_load elsewhere."""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class FindingDef:
    """One finding definition from config."""
    en: str
    pt: list[str]
    category: str
    priority: str  # CRITICAL | HIGH | MODERATE | LOW
    tier: int = 1
    type: str = "descriptive"      # descriptive | etiologic | device_presence | device_position
    acuity: str = "context_dependent"  # acute | chronic | incidental | context_dependent
    parent: str | None = None


@dataclass
class FindingsConfig:
    """Parsed findings_cxr.yaml v2."""
    version: str
    findings: dict[str, FindingDef]
    categories: list[str]
    study_quality_flags: list[str]
    discovery_threshold: float
    discovery_min_count: int

    def finding_names(self) -> list[str]:
        """All Tier 1 finding names (sorted)."""
        return sorted(self.findings.keys())

    def findings_by_priority(self, priority: str) -> list[str]:
        """Finding names filtered by priority tier."""
        return [name for name, f in self.findings.items() if f.priority == priority]

    def findings_by_category(self, category: str) -> list[str]:
        """Finding names filtered by category."""
        return [name for name, f in self.findings.items() if f.category == category]

    def pt_synonyms(self, finding_name: str) -> list[str]:
        """Portuguese synonyms for a finding."""
        return self.findings[finding_name].pt

    def findings_by_type(self, finding_type: str) -> list[str]:
        """Finding names filtered by type."""
        return [name for name, f in self.findings.items() if f.type == finding_type]

    def findings_by_acuity(self, acuity: str) -> list[str]:
        """Finding names filtered by acuity."""
        return [name for name, f in self.findings.items() if f.acuity == acuity]

    def children(self, finding_name: str) -> list[str]:
        """Finding names that have this finding as their parent."""
        return [name for name, f in self.findings.items() if f.parent == finding_name]

    def hierarchy(self) -> dict[str, str | None]:
        """Return {finding_name: parent_name_or_None} for all findings."""
        return {name: f.parent for name, f in self.findings.items()}


@functools.lru_cache(maxsize=4)
def load_findings_config(config_path: str = "config/findings_cxr.yaml") -> FindingsConfig:
    """Load and validate findings_cxr.yaml v2."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    findings = {}
    for name, data in raw.get("findings", {}).items():
        findings[name] = FindingDef(
            en=data["en"],
            pt=data["pt"],
            category=data["category"],
            priority=data["priority"],
            tier=data.get("tier", 1),
            type=data.get("type", "descriptive"),
            acuity=data.get("acuity", "context_dependent"),
            parent=data.get("parent"),
        )

    discovery = raw.get("discovery", {})

    return FindingsConfig(
        version=raw.get("version", "2.0.0"),
        findings=findings,
        categories=raw.get("categories", []),
        study_quality_flags=raw.get("study_quality_flags", []),
        discovery_threshold=discovery.get("promotion_threshold", 0.005),
        discovery_min_count=discovery.get("min_absolute_count", 10),
    )


@functools.lru_cache(maxsize=4)
def load_synonym_map(config_path: str = "config/tier2_synonyms.yaml") -> dict[str, str]:
    """Load Tier 2 synonym map. Returns {alias: canonical_name}."""
    path = Path(config_path)
    if not path.exists():
        return {}
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    mapping: dict[str, str] = {}
    for canonical, aliases in raw.get("synonyms", {}).items():
        for alias in (aliases or []):
            mapping[alias] = canonical
    return mapping
