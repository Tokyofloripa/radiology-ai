# radiology-ai

Reference label extraction engine for Brazilian telemedicine chest X-ray reports.

Transforms anonymized Portuguese radiology reports into structured labels using dual-model LLM extraction (Claude Sonnet + Opus), then provides a framework for evaluating vision AI models against these reference labels.

## Key Features

- **40-finding CXR ontology** with priority, type, acuity, and hierarchy metadata
- **Dual-model extraction** (Sonnet + Opus) with 100% classification agreement
- **6 validation rules** including ghost-abnormal detection, critical override, and hierarchy consistency
- **Portuguese NLP** — negation/hedging/chronicity rule checks for Brazilian medical text
- **Tier 2 discovery** — automatically finds new findings not in the vocabulary
- **Calibrated arbitration** — resolves inter-model disagreements with clinical logic
- **Named label maps** — explicit strategies for downstream consumers (strict, broad, parenchymal_opacity)
- **228 tests**, config-driven, idempotent, resumable

## Pipeline

```
Stage 0:    Ingest CSV          → exam_registry + unique_reports
Stage 0.5:  Generate Prompt     → extraction prompt from YAML config
Stage 1:    Extract (async)     → extractions per model + run_manifest
Stage 1.5:  Validate            → review flags + acute_classification
Stage 1.75: Discovery           → Tier 2 finding aggregation
Stage 1b:   Compare             → inter-model agreement + arbitration
Stage 2:    Reference Labels    → balanced evaluation dataset
Stage 3:    Vision Models       → predictions per backend (future)
Stage 4:    Evaluate            → metrics, plots, comparison (future)
```

## Quick Start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pydantic pyyaml anthropic numpy pytest

# Set API key
export ANTHROPIC_API_KEY=sk-ant-...

# Run tests
python3 -m pytest tests/ -v --tb=short

# Run pipeline
PYTHONPATH=src python3 scripts/00_ingest.py --input your_data.csv
PYTHONPATH=src python3 scripts/00b_generate_prompt.py
PYTHONPATH=src python3 scripts/01_extract_labels.py run --models sonnet --limit 10 --concurrency 10
PYTHONPATH=src python3 scripts/01a_validate_extractions.py
PYTHONPATH=src python3 scripts/01b_compare_extractions.py
```

## E2E Validated (100 reports, Sonnet + Opus)

| Metric | Value |
|--------|-------|
| Classification agreement | 100% |
| Mean finding agreement | 91.0% |
| Arbitration auto-resolved | 74% of disagreements |
| Review triggers firing | 26% of reports |
| Acute vs chronic separation | 17% chronic-only abnormals |

## Documentation

See [MVP-v7-spec.md](MVP-v7-spec.md) for the full 2,440-line design specification.

## License

MIT
