# radiology-ai

> Reference label extraction engine for Brazilian telemedicine chest X-ray reports

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-228%20passing-brightgreen.svg)](#testing)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Transforms anonymized Portuguese radiology reports into structured reference labels using dual-model LLM extraction (Claude Sonnet + Opus), with post-extraction validation, Portuguese NLP checks, and a framework for evaluating vision AI models against these labels.

**Important:** These are **silver-standard reference labels**, not gold-standard ground truth. They require human adjudication on a validation subset before clinical use. See [SECURITY.md](SECURITY.md).

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Finding Ontology](#finding-ontology)
- [Pipeline Stages](#pipeline-stages)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Validation Rules](#validation-rules)
- [Portuguese NLP](#portuguese-nlp)
- [Inter-Model Comparison](#inter-model-comparison)
- [Label Maps](#label-maps)
- [E2E Results](#e2e-results)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Configuration](#configuration)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

This pipeline was built for a Brazilian teleradiology company processing 10K+ anonymized CXR reports. It solves the problem of creating structured evaluation datasets from free-text Portuguese radiology reports.

### What it does

1. **Ingests** CSV data with Portuguese radiology reports, deduplicates by text content (SHA-256)
2. **Extracts** structured findings using LLM models (40 CXR findings per report)
3. **Validates** extractions with 6 rule-based checks (ghost abnormals, hierarchy consistency, etc.)
4. **Discovers** new findings not in the vocabulary (Tier 2 dynamic discovery)
5. **Compares** extractions across models with calibrated arbitration
6. **Produces** balanced reference label datasets for vision model evaluation

### What it does NOT do

- Real-time clinical processing
- Image analysis (that's the vision model backends — future stages)
- De-identification (data is pre-anonymized)
- Clinical decision-making (these are research labels)

---

## Architecture

```
src/cxr_mvp/
├── models.py               Data models + get_finding_status() utility
├── config.py               Centralized YAML loader (@lru_cache)
├── ingest.py               Stage 0: CSV parsing, normalization, dedup
├── prompt_generator.py     Stage 0.5: Config-driven prompt generation
├── extractors/
│   ├── base.py             ExtractionBackend ABC (sync + async)
│   ├── registry.py         Config-driven backend instantiation
│   └── anthropic_extractor.py  Claude models: async concurrent + retry
├── validation.py           Stage 1.5: 6 review rules + acute classification
├── pt_rules.py             Portuguese NLP: negation/hedging/chronicity
├── discovery.py            Stage 1.75: Tier 2 aggregation + synonym dedup
├── comparison.py           Stage 1b: Agreement + hierarchical roll-up
├── reference_labels.py     Stage 2: Join, balance, statistics
├── label_maps.py           Named label interpretation strategies
├── run_manifest.py         Frozen version capture for audit trail
└── backends/               Vision model backends (future)

scripts/                    Thin CLI wrappers (one per stage)
config/                     YAML configs (single source of truth)
tests/                      228 tests
```

---

## Finding Ontology

40 CXR findings organized across 4 dimensions:

| Dimension | Values | Example |
|-----------|--------|---------|
| **Priority** | CRITICAL / HIGH / MODERATE / LOW | pneumothorax=CRITICAL, spondylosis=LOW |
| **Type** | descriptive / etiologic / device_presence / device_position | consolidation=descriptive, pneumonia=etiologic |
| **Acuity** | acute / chronic / incidental / context_dependent | edema=acute, aortic_atherosclerosis=chronic |
| **Hierarchy** | parent-child relationships | lung_opacity → consolidation, infiltration |

### Label States (5-state system)

| State | Meaning | Example |
|-------|---------|---------|
| `Positive` | Finding explicitly present | "Cardiomegalia" |
| `Negative` | Finding explicitly denied | "Sem derrame pleural" |
| `Uncertain` | Hedged language | "Nao se pode excluir pneumonia" |
| `Absent` | Finding not mentioned | (no reference in report) |
| `Not_Assessable` | Cannot evaluate | "Avaliacao prejudicada" |

All findings, synonyms, and metadata defined in [`config/findings_cxr.yaml`](config/findings_cxr.yaml).

---

## Pipeline Stages

```
Stage 0      Ingest           exam_registry.jsonl + unique_reports.jsonl     $0
Stage 0.5    Generate Prompt  extraction prompt from YAML config             $0
Stage 1      Extract          extractions_{model}.jsonl + run_manifest       ~$3-6/5K reports
Stage 1.5    Validate         validated_{model}.jsonl + needs_review.jsonl   $0
Stage 1.75   Discovery        discovery_report.json                          $0
Stage 1b     Compare          agreement_report.json + arbitrated labels      $0
Stage 2      Reference Labels labels.jsonl + balanced.csv + statistics       $0
Stage 3      Vision Models    predictions/{model}.jsonl                      varies (future)
Stage 4      Evaluate         comparison tables + plots                      $0 (future)
```

Each stage writes to `output/` with checkpointing. All scripts are resumable and idempotent.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Anthropic API key (for LLM extraction)

### Installation

```bash
git clone https://github.com/Tokyofloripa/radiology-ai.git
cd radiology-ai
python3 -m venv .venv && source .venv/bin/activate
pip install pydantic pyyaml anthropic numpy pytest
```

### Configuration

```bash
cp .env.example .env
# Edit .env with your API key:
# ANTHROPIC_API_KEY=sk-ant-...
```

### Run Tests

```bash
python3 -m pytest tests/ -v --tb=short   # 228 tests
```

### Run Pipeline

```bash
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)

# Stage 0: Ingest
PYTHONPATH=src python3 scripts/00_ingest.py --input your_data.csv

# Stage 0.5: Generate prompt from config
PYTHONPATH=src python3 scripts/00b_generate_prompt.py

# Stage 1: Extract (async, 20 concurrent)
PYTHONPATH=src python3 scripts/01_extract_labels.py run --concurrency 20

# Stage 1.5: Validate
PYTHONPATH=src python3 scripts/01a_validate_extractions.py

# Stage 1b: Compare models
PYTHONPATH=src python3 scripts/01b_compare_extractions.py

# Stage 1.75: Discovery report
PYTHONPATH=src python3 scripts/01c_discovery_report.py --total-reports 1126

# Stage 2: Build reference labels
PYTHONPATH=src python3 scripts/02_build_ground_truth.py
```

---

## Usage

### Extract with a single model (pilot)

```bash
PYTHONPATH=src python3 scripts/01_extract_labels.py run \
    --models sonnet --limit 10 --concurrency 10
```

### Extract with both models (production)

```bash
# Sonnet (fast, concurrency 20)
PYTHONPATH=src python3 scripts/01_extract_labels.py run \
    --models sonnet --concurrency 20

# Opus (slower, concurrency 5 due to rate limits)
PYTHONPATH=src python3 scripts/01_extract_labels.py run \
    --models opus --concurrency 5
```

### Resume interrupted extraction

Just re-run the same command. The checkpoint file (`extractions_{model}.jsonl`) tracks completed report hashes — already-extracted reports are skipped automatically.

---

## Validation Rules

Stage 1.5 applies 6 rules to each extraction, flagging reports for human review:

| Rule | Trigger | Action |
|------|---------|--------|
| Ghost abnormal | `classification=abnormal` with no Positive/Uncertain findings | Flag for review |
| Critical override | `classification=normal` with CRITICAL finding Positive | Upgrade to abnormal + flag |
| High uncertainty | 3+ findings with `Uncertain` status | Flag for review |
| Critical on suboptimal | CRITICAL finding on suboptimal study quality | Flag for review |
| Device without position | Device present but `device_malposition` not assessed | Flag for review |
| Hierarchy inconsistency | Child finding Positive but parent Absent | Flag for review |

Additionally, `acute_classification` separates chronic-only abnormals (e.g., only spondylosis) from acute ones (e.g., effusion, pneumothorax).

---

## Portuguese NLP

`pt_rules.py` provides deterministic rule checks for Brazilian Portuguese medical text:

| Pattern Type | Examples | Action |
|-------------|----------|--------|
| **Negation** | "sem sinais de", "ausencia de", "dentro da normalidade" | Warn if finding marked Positive |
| **Hedging** | "nao se pode excluir", "possivel", "sugestivo de" | Warn if finding marked Positive (should be Uncertain) |
| **Chronicity** | "sequela", "cronico", "residual", "previo" | Flag as chronic finding |

Warnings are stored in `rule_warnings` on each validated extraction.

---

## Inter-Model Comparison

When running Sonnet + Opus on the same reports:

1. **Agreement scoring** with hierarchical roll-up (child Positive covers parent)
2. **Calibrated arbitration** for disagreements:
   - Positive vs Uncertain on etiologic finding → Uncertain (conservative)
   - Absent vs Positive → flag for manual review
   - Negative vs Absent → auto-resolve to Negative (both mean "not present")
   - Not_Assessable vs anything → Not_Assessable (conservative)
3. **Backup file exclusion** — `*_backup*` files are automatically filtered

---

## Label Maps

Downstream consumers need explicit strategies for interpreting the 5-state labels. Three named maps are provided in `label_maps.py`:

```python
from cxr_mvp.label_maps import apply_label_map

binary = apply_label_map(extraction["findings"], "strict")   # Positive only
binary = apply_label_map(extraction["findings"], "broad")    # Positive + Uncertain
composite = apply_label_map(extraction["findings"], "parenchymal_opacity")  # any opacity
```

| Map | Positive → | Uncertain → | Absent/Negative → | Not_Assessable → |
|-----|-----------|------------|-------------------|-----------------|
| `strict` | True | False | False | None (excluded) |
| `broad` | True | True | False | None (excluded) |
| `parenchymal_opacity` | Composite: any of lung_opacity/consolidation/infiltration | | | |

---

## E2E Results

Validated on 100 reports with both Claude Sonnet and Claude Opus:

| Metric | Value |
|--------|-------|
| **Classification agreement** | **100%** (both agree normal/abnormal on all 100) |
| Mean finding agreement | 91.0% |
| Reports with any disagreement | 96/100 |
| Total finding disagreements | 362 |
| Auto-resolved by arbitration | 267 (74%) |
| Flagged for manual review | 95 (26%) |
| Review triggers firing | 26% of reports |
| Acute vs chronic | 17% of abnormals are chronic-only |
| Tier 2 discoveries | 13 unique findings |
| PT rule warnings | 1 in 100 reports |

### Model Personality

| | Sonnet | Opus |
|--|:--:|:--:|
| CRITICAL priority | 40 | 23 |
| Needs review | 26 | 15 |
| Acute abnormal | 68 | 65 |

Sonnet is more sensitive; Opus is more conservative. Both reach identical binary (normal/abnormal) conclusions.

### Hardest Findings (lowest agreement)

| Finding | Agreement |
|---------|:---------:|
| lung_opacity | 74% |
| diaphragm_elevation | 77% |
| pneumonia | 79% |
| infiltration | 82% |

### Notable: Pneumonia is 100% Uncertain

0 Positive, 20 Uncertain in 100 reports. This is clinically correct — Brazilian radiologists hedge on etiologic diagnoses ("nao se pode excluir processo pneumonico"). The finding has `type: etiologic` in the ontology. Use `label_maps.py` for task-specific interpretation.

---

## Project Structure

```
radiology-ai/
├── README.md                    This file
├── MVP-v7-spec.md               Full 2,440-line design specification
├── CLAUDE.md                    AI assistant instructions
├── CONTRIBUTING.md              Contribution guidelines
├── SECURITY.md                  Security and regulatory notice
├── LICENSE                      MIT License
├── pyproject.toml               Project config (pytest, ruff, mypy)
├── .env.example                 API key template
├── .gitignore                   Excludes data, output, secrets
│
├── config/
│   ├── findings_cxr.yaml        40 findings: en, pt, category, priority, type, acuity, parent
│   ├── tier2_synonyms.yaml      Tier 2 synonym map (canonical → aliases)
│   ├── label_mapping.yaml       5-state → binary mapping
│   ├── extraction_models.yaml   Model config: provider, model_id, mode, max_tokens
│   └── prompts/
│       └── extract_cxr_pt.txt   Auto-generated Portuguese extraction prompt
│
├── src/cxr_mvp/                 Library code (18 modules)
│   ├── models.py                Core data models
│   ├── config.py                YAML loader (@lru_cache)
│   ├── ingest.py                CSV ingestion + dedup
│   ├── prompt_generator.py      Prompt generation from config
│   ├── validation.py            6 review rules + acute classification
│   ├── pt_rules.py              Portuguese NLP checks
│   ├── discovery.py             Tier 2 aggregation + dedup
│   ├── comparison.py            Inter-model agreement + arbitration
│   ├── reference_labels.py      Join, balance, statistics
│   ├── label_maps.py            Named label interpretation maps
│   ├── run_manifest.py          Frozen version capture
│   ├── extractors/              LLM extraction backends
│   │   ├── base.py              ExtractionBackend ABC
│   │   ├── registry.py          Config-driven instantiation
│   │   └── anthropic_extractor.py  Claude: sync + async + retry
│   └── backends/                Vision model backends (future)
│       ├── base.py              VisionBackend ABC
│       └── mock_backend.py      Deterministic test backend
│
├── scripts/                     CLI wrappers (one per stage)
│   ├── 00_ingest.py
│   ├── 00b_generate_prompt.py
│   ├── 01_extract_labels.py     Supports --concurrency, --models, --limit
│   ├── 01a_validate_extractions.py
│   ├── 01b_compare_extractions.py
│   ├── 01c_discovery_report.py
│   └── 02_build_ground_truth.py
│
└── tests/                       228 tests
    ├── conftest.py              Shared fixtures (PT reports, findings, DICOM mocks)
    ├── test_models.py
    ├── test_config.py
    ├── test_ingest.py
    ├── test_prompt_generator.py
    ├── test_validation.py
    ├── test_pt_rules.py
    ├── test_discovery.py
    ├── test_comparison.py
    ├── test_ground_truth.py
    ├── test_label_maps.py
    ├── test_run_manifest.py
    ├── extractors/
    │   ├── test_anthropic_extractor.py
    │   ├── test_base.py
    │   └── test_registry.py
    └── backends/
        └── test_mock_backend.py
```

---

## Testing

```bash
# Run all tests
python3 -m pytest tests/ -v --tb=short

# Run specific test modules
python3 -m pytest tests/test_validation.py -v
python3 -m pytest tests/test_pt_rules.py -v

# Run with markers
python3 -m pytest tests/ -m "not slow" -v
```

228 tests covering:
- Data models and label normalization
- Config loading with caching
- CSV ingestion and deduplication
- Prompt generation and hashing
- Extraction validation (6 rules)
- Portuguese NLP rule checks
- Tier 2 discovery with synonym dedup
- Inter-model comparison and arbitration
- Async extraction with retry and concurrency
- Label maps and run manifests

---

## Configuration

All pipeline behavior is controlled by YAML configs in `config/`:

### `findings_cxr.yaml` — Finding Ontology

```yaml
pneumothorax:
  en: "Pneumothorax"
  pt: ["pneumotorax"]
  category: pulmonary
  priority: CRITICAL
  tier: 1
  type: descriptive
  acuity: acute
```

### `extraction_models.yaml` — Model Configuration

```yaml
models:
  - name: sonnet
    provider: anthropic
    model_id: claude-sonnet-4-6
    mode: batch
    enabled: true
```

### `tier2_synonyms.yaml` — Tier 2 Dedup

```yaml
synonyms:
  hilar_prominence:
    - hilar_enlargement
    - enlarged_hilum
    - prominent_hilum
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow and guidelines.

## License

[MIT](LICENSE)
