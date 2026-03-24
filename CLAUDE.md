# radiology-ai — Radiology Report Reference Label Engine

**Repository:** https://github.com/Tokyofloripa/radiology-ai
**Version:** 0.7.0 | **Tests:** 228 | **Python:** 3.11+

## Mission
Transform 10K anonymized Portuguese radiology reports into structured reference labels,
then evaluate which AI vision model best classifies the corresponding X-ray images.
**Reference labels = radiologist report text extracted via LLM (silver standard).**
**Vision models are candidates tested AGAINST these labels.**
Phase 1: CXR (1,126 unique reports from 6,541 exams). Phase 2: MSK/spine.

## Critical Rules
- All stage outputs are schema-validated JSONL with provenance metadata (ontology_version, extraction_schema)
- Every script MUST be resumable and idempotent — checkpoint via report_hash, append-per-result
- NEVER infer label mappings, thresholds, or prompt text from code — config YAML only
- Extract findings from achados/impressão sections ONLY — never from indicação/história
- Split and balance by PatientID, never by StudyInstanceUID (prevents data leakage)
- These are **reference labels** (silver standard), not ground truth — validated via inter-model agreement + human adjudication

## Design Philosophy
1. **Config-driven** — `findings_cxr.yaml` is the single source of truth for vocabulary, priority, type, acuity, hierarchy
2. **Portuguese-native** — All prompts and NLP rules designed for Brazilian Portuguese reports
3. **Model-agnostic** — New extraction model = one file implementing `ExtractionBackend`; new vision model = `VisionBackend`
4. **Auditable** — Run manifests, provenance fields, deterministic synonym maps, evidence spans on every finding

## Git Workflow
- **Branch:** `main` is the primary branch
- **Remote:** `origin` → `https://github.com/Tokyofloripa/radiology-ai.git`
- **Commits:** Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`)
- **PRs:** Use the PR template (`.github/pull_request_template.md`) — includes test checklist
- **Issues:** Bug reports and finding requests have templates in `.github/ISSUE_TEMPLATE/`
- **No data in repo:** CSV, DICOM, output, and .env are all gitignored. Never commit patient data.

## Architecture
```
src/cxr_mvp/
├── models.py               ← Core data models + get_finding_status() utility:
│                              LabelState, Confidence, FindingLabel, OtherFinding,
│                              ReportExtraction, ExtractionResult, ValidatedExtraction,
│                              ExamRecord, UniqueReport, GroundTruthRow, ModelPrediction, RunManifest
├── config.py               ← Centralized YAML loader (@lru_cache):
│                              FindingDef (en, pt, category, priority, tier, type, acuity, parent),
│                              FindingsConfig (finding_names, by_priority, by_category, by_type,
│                              by_acuity, hierarchy, children, pt_synonyms),
│                              load_findings_config(), load_synonym_map()
├── ingest.py               ← Stage 0: CSV parsing, text normalization, SHA-256 dedup
├── prompt_generator.py     ← Stage 0.5: Config-driven prompt generation + SHA-256 hash
├── extractors/             ← Stage 1: Text extraction backends
│   ├── base.py              ← ExtractionBackend ABC (extract, extract_async, supports_batch)
│   ├── registry.py          ← Config-driven instantiation from extraction_models.yaml
│   └── anthropic_extractor.py ← Any claude-* model. Sync + async concurrent + retry.
│                                Parses other_findings + study_quality. Uses _result_to_dict(asdict).
├── validation.py           ← Stage 1.5: 6 review rules + acute_classification + PT rules integration
│                              Rules: ghost_abnormal, critical_override, high_uncertainty,
│                              critical_on_suboptimal, device_without_position, hierarchy_inconsistency
├── pt_rules.py             ← Portuguese NLP: negation/hedging/chronicity pattern matching
├── discovery.py            ← Stage 1.75: Tier 2 aggregation (synonym map → stem dedup fallback)
├── comparison.py           ← Stage 1b: Inter-model agreement with hierarchical roll-up + arbitration
├── reference_labels.py     ← Stage 2: Join extractions→exams, balance, statistics
├── label_maps.py           ← Named label interpretation maps (strict, broad, parenchymal_opacity)
├── run_manifest.py         ← Run manifest generation (frozen versions for audit trail)
├── backends/               ← Vision model backends (future)
│   ├── base.py              ← VisionBackend ABC (predict → ModelPrediction)
│   ├── registry.py          ← Auto-discovery, lazy imports
│   └── mock_backend.py      ← Deterministic scores for testing
├── body_part_router.py     ← DICOM → body part detection (future)
├── image_utils.py          ← DICOM → normalized array (future)
└── evaluation.py           ← Confusion matrix, AUROC, AUPRC (future)

scripts/                     ← Thin CLI wrappers calling src/ library functions
├── 00_ingest.py             ← CSV → exam_registry.jsonl + unique_reports.jsonl
├── 00b_generate_prompt.py   ← Generate extraction prompt from findings_cxr.yaml
├── 01_extract_labels.py     ← Multi-model extraction (--concurrency 20, run manifest, staleness check)
├── 01a_validate_extractions.py ← 6 review rules, acute_classification, PT rule warnings
├── 01b_compare_extractions.py ← Inter-model agreement report + select primary
├── 01c_discovery_report.py  ← Tier 2 finding aggregation + promotion candidates
├── 02_build_ground_truth.py ← Join, compare flags, balance, compute stats

config/
├── findings_cxr.yaml        ← 40 findings v3: en, pt, category, priority, tier, type, acuity, parent
├── tier2_synonyms.yaml      ← Tier 2 synonym map (canonical → aliases, auditable dedup)
├── label_mapping.yaml       ← 5-state → binary mapping (configurable abnormal_states)
├── extraction_models.yaml   ← Multi-model config: provider, model_id, mode, enabled, max_tokens
└── prompts/extract_cxr_pt.txt ← Auto-generated PT extraction prompt (40 findings + PT synonyms)
```

## Pipeline Stages
```
Stage 0:    Ingest        → exam_registry.jsonl + unique_reports.jsonl       (local, $0)
Stage 0.5:  Gen Prompt    → config/prompts/extract_cxr_pt.txt               (local, $0)
Stage 1:    Extract       → extractions_{model}.jsonl + run_manifest.json    (Sonnet+Opus, ~$3-6/5K)
Stage 1.5:  Validate      → validated_{model}.jsonl + needs_review.jsonl     (local, $0)
Stage 1.75: Discovery     → discovery_report.json                            (local, $0)
Stage 1b:   Compare       → agreement_report.json + selected_extractions     (local, $0)
Stage 2:    Ref Labels    → labels.jsonl + balanced.csv + statistics.json     (local, $0)
Stage 3:    Run models    → predictions/{model}.jsonl per backend            (varies)
Stage 4:    Evaluate      → evaluation/comparison_table.csv + plots          (local, $0)
```
Each stage writes `output/` checkpoint. Scripts are thin CLI → library calls.

## Finding Ontology (v3)

40 findings organized by:
- **Priority:** CRITICAL (7) | HIGH (8) | MODERATE (13) | LOW (12)
- **Type:** descriptive (30) | etiologic (2: pneumonia, tuberculosis) | device_presence (7) | device_position (1)
- **Acuity:** acute (8) | chronic (9) | incidental (3) | context_dependent (20)
- **Hierarchy:** lung_opacity → consolidation, infiltration

## Label System
```
LabelState: Positive | Negative | Uncertain | Absent | Not_Assessable

Named label maps (label_maps.py):
  strict:               Positive only → True
  broad:                Positive + Uncertain → True
  parenchymal_opacity:  any of lung_opacity/consolidation/infiltration Positive → True

Binary mapping (config/label_mapping.yaml):
  abnormal_states: [Positive, Uncertain]  ← configurable
  excluded_states: [Not_Assessable]       ← excluded from metrics
```

## Validation Rules (Stage 1.5)
1. **Ghost abnormal** — classification=abnormal with no Positive/Uncertain findings
2. **Critical override** — classification=normal with CRITICAL Positive finding → upgrade to abnormal
3. **High uncertainty** — 3+ Uncertain findings → needs review
4. **Critical on suboptimal** — CRITICAL finding on suboptimal study → needs review
5. **Device without position** — device present without malposition assessment → needs review
6. **Hierarchy inconsistency** — child Positive but parent Absent (e.g., consolidation=Positive, lung_opacity=Absent)

## Commands
```bash
source .venv/bin/activate
python3 -m pytest tests/ -v --tb=short                                    # 228 tests

# Full pipeline
PYTHONPATH=src python3 scripts/00_ingest.py --input ListaLLM.csv
PYTHONPATH=src python3 scripts/00b_generate_prompt.py
PYTHONPATH=src python3 scripts/01_extract_labels.py run --concurrency 20  # both models
PYTHONPATH=src python3 scripts/01_extract_labels.py run --models sonnet --limit 10 --concurrency 10
PYTHONPATH=src python3 scripts/01a_validate_extractions.py
PYTHONPATH=src python3 scripts/01b_compare_extractions.py
PYTHONPATH=src python3 scripts/01c_discovery_report.py --total-reports 1126
PYTHONPATH=src python3 scripts/02_build_ground_truth.py
```

## E2E Validated Results (100 reports, Sonnet + Opus)
- Classification agreement: **100%** (both agree normal/abnormal)
- Mean finding agreement: **91.0%**
- Arbitration auto-resolved: **74%** of 362 disagreements
- 26% review rate (Sonnet), 15% review rate (Opus)
- Sonnet more sensitive (40 CRITICAL), Opus more conservative (23 CRITICAL)
- Tier 2 discovery: 13 unique findings, top candidate `bronchial_wall_thickening` at 6%
- Portuguese NLP rules: 1 warning in 100 reports (hedging conflict)

## Things That Will Bite You
- Reference labels = silver standard (LLM-extracted). NOT ground truth. Needs human adjudication.
- DICOM MONOCHROME1 must be inverted to MONOCHROME2 before model inference
- Apply Window Center/Width before converting to 8-bit — raw 12-16 bit destroys contrast
- RescaleSlope/RescaleIntercept must be applied before windowing
- Portuguese negation ≠ English negation. "sem sinais de" ≠ "no signs of" structurally.
- pt_rules.py catches negation/hedging conflicts — check rule_warnings in validated output
- Extract from achados/impressão ONLY — indicação/história will poison labels
- Balanced set: ALL abnormals + equal random normals, split by PatientID
- pneumonia is 100% Uncertain in our data (radiologists hedge; type=etiologic). Use label_maps.py for task-specific interpretation.
- Opus rate limit is 30K input TPM — use --concurrency 5 for Opus (vs 20 for Sonnet)
- NEVER use "accuracy" alone — sensitivity, specificity, AUROC minimum
- config/label_mapping.yaml defines which states = abnormal. Never assume in code.
- Triage priority is deterministic from finding states — but 40 vs 23 CRITICAL (Sonnet vs Opus) shows sensitivity gap.

## Key Documentation
- `README.md` — Quick start, architecture overview, E2E results
- `MVP-v7-spec.md` — Full 2,440-line design specification
- `CONTRIBUTING.md` — Dev workflow, adding findings/backends
- `SECURITY.md` — Medical data policy, regulatory notice
- `CLAUDE.md` — This file (AI assistant instructions)
