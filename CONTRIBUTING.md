# Contributing

Thank you for your interest in radiology-ai.

## Getting Started

1. Fork the repository
2. Create a virtual environment: `python3 -m venv .venv && source .venv/bin/activate`
3. Install dependencies: `pip install pydantic pyyaml anthropic numpy pytest`
4. Run tests: `python3 -m pytest tests/ -v --tb=short`

## Development Workflow

- **TDD required** — write failing tests first, then implement
- **Config-driven** — all vocabulary, thresholds, and prompts live in `config/` YAML files
- **Conventional commits** — `feat:`, `fix:`, `docs:`, `refactor:`, `test:`
- Run `python3 -m pytest tests/` before every commit (228 tests, must all pass)

## Adding a New Finding

1. Add the finding to `config/findings_cxr.yaml` with all required fields (en, pt, category, priority, tier, type, acuity)
2. Run `PYTHONPATH=src python3 scripts/00b_generate_prompt.py` to regenerate the extraction prompt
3. Update tests in `tests/test_config.py`

## Adding a New Vision Backend

1. Create `src/cxr_mvp/backends/your_model.py` implementing `VisionBackend` ABC
2. Add config entry in `config/extraction_models.yaml`
3. Add tests in `tests/backends/test_your_model.py`

## Medical Data

- **NEVER** commit patient data, DICOM files, or radiology reports
- **NEVER** commit `.env` files or API keys
- All output goes to `output/` (gitignored)

## Code Style

- Python 3.11+
- Ruff for linting (`ruff check .`)
- No new dependencies without discussion
- YAGNI — minimum complexity for the current task
