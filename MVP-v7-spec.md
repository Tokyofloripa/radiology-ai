# MVP v7 (FINAL): X-Ray Reference Label Engine + Model Evaluation Framework
## Portuguese Reports → Structured Reference Labels → Vision Model Bakeoff

**Validated by**: 10 MI2 research agents, 4 AI Council rounds (GPT 5.4, Gemini 3.1 Pro, Grok 4.20, Claude Opus 4.6), 6 MVP iterations (v1→v6), CXR Foundation investigation, MedSigLIP implementation research, 228 unit tests, E2E validation on 100 reports
**Supersedes**: MVP-v1 through MVP-v6
**Feeds into**: Playbook v4 (production discrepancy pipeline)

---

## Mission

Transform 10,000 anonymized Portuguese radiology reports into structured reference labels, then systematically evaluate which AI vision model best classifies the corresponding X-ray images. This MVP generates standalone value (a labeled dataset + model benchmarks on YOUR data) while producing the inputs the production pipeline needs (calibrated thresholds, validated model choice, Portuguese prompt templates).

**Critical distinction:** LLM-extracted labels are **silver standard** reference labels, not gold standard ground truth. They require human adjudication on a subset before clinical use. This terminology is used consistently throughout.

### What This MVP Produces

1. **Reference label dataset**: 10K reports → structured labels (normal/abnormal + per-finding classification)
2. **Balanced evaluation set**: ~1,000 studies (equal abnormal + normal) for unbiased model testing
3. **Model bakeoff**: N vision models scored against the same reference labels with standard metrics
4. **Confusion matrices + AUROC**: Per-model, per-finding performance on YOUR population
5. **Winning model + calibrated thresholds**: Ready to plug into the production pipeline
6. **Portuguese medical NLP templates**: Validated prompts for Brazilian radiology report extraction
7. **Multi-model extraction validation**: Inter-model agreement report confirming Sonnet is sufficient for label extraction
8. **Post-extraction validation**: Automated triage rules, Portuguese NLP checks, Tier 2 finding discovery
9. **Run manifests**: Frozen version capture for full reproducibility

### What This MVP Does NOT Do

- Real-time processing (that's the Playbook)
- DICOM server integration (that's Orthanc in the Playbook)
- De-identification (data is already anonymized)
- Workflow alerts or prioritization (that's production)
- DICOM SR or viewer output (that's OHIF in the Playbook)
- Human adjudication (planned for controlled 1,126 run)

---

## Design Philosophy

1. **Reference labels first** — LLM-extracted text labels from expert radiologist reports are silver-standard reference labels. Vision models are candidates being tested against them. Human adjudication on a subset validates the silver standard.
2. **Config-driven** — `findings_cxr.yaml` is the single source of truth for vocabulary, priority, type, acuity, hierarchy. Prompt is auto-generated from config. No hardcoded finding lists.
3. **Model-agnostic** — Adding a new vision model = one Python file. Adding a new extraction model = one YAML entry. The evaluation pipeline doesn't change.
4. **Both tracks** — Binary (normal/abnormal) AND sub-classification (40 findings) from a single extraction pass. Compare complexity vs value.
5. **Portuguese-native** — All prompts, terminology, and NLP designed for Brazilian Portuguese radiology reports.
6. **Playbook-compatible** — Label vocabulary, quality flags, backend interface, and output formats are designed to plug directly into the production Playbook v4 pipeline.
7. **Standalone value** — Each stage produces a useful artifact. You don't need to run the full pipeline to get value from Stage 1 alone.
8. **Simplicity** — No training, no adapters, no calibration pipelines within the MVP. Models classify out of the box.
9. **Auditable** — Run manifests, provenance fields (ontology_version, extraction_schema), deterministic synonym maps, evidence spans on every finding.

---

## Data Reality (from ListaLLM.csv analysis)

The CSV was analyzed in detail during the design session. Key findings that shaped the pipeline design:

### CSV Structure

| Column | Index | Meaning | Example |
|---|---|---|---|
| exam_id | [0] | Study identifier | `10794085` |
| customer_id | [1] | Hospital/clinic | `2779` |
| dicom_url | [2] | DICOM download link (files already downloaded locally) | `http://clirea.ptmdocs.com.br/prd/10794085-...dcm` |
| report_text | [3] | Radiologist's Portuguese report | `"RADIOGRAFIA DO TÓRAX EM PA..."` |
| label | [4] | Normal(1) / Abnormal(2) flag — **unreliable, keep for comparison only** | `1` |

- **No header row.** Column order is hardcoded.
- **Semicolon-delimited.** Report text is double-quoted (may contain semicolons internally).
- **UTF-8 with BOM.** Must use `encoding='utf-8-sig'` when reading.

### Key Statistics

| Metric | Value |
|---|---|
| Total CSV rows | 10,000 |
| Unique exam_ids | 6,542 (duplicates = PA + lateral DICOM views per exam) |
| Unique report texts (after normalization) | **1,163** (radiologists use templates heavily) |
| Customers (clinics/hospitals) | 96 |
| Original label distribution (exam-level) | normal(1)=5,759 / abnormal(2)=780 / mixed=3 |
| Garbage reports (empty or <10 chars) | 2 |
| DICOM filenames with PHI (patient names) | 432 (noted for DICOM phase) |
| Report length | min=0, median=253 chars, max=1,808 chars |

### Critical Implications

1. **Only 1,163 Sonnet API calls needed** — not 10,000 or 6,542. Dedup by deterministic SHA-256 of normalized text, then map extractions back to all 6,542 exams. Saves ~85% on API cost.
2. **Original label is unreliable** — radiologists click the flag but often ignore it and just write the report. 28 identical reports appear under both labels. LLM extraction is the reference label; original label kept only for later comparison.
3. **No patient_id in CSV** — only available from DICOM metadata. Patient-level splitting deferred to vision model phase.
4. **96 customers, not 96 patients** — column[1] is hospital/clinic ID, not patient ID.
5. **Duplicate rows = multiple DICOM views** — same exam_id appears 2+ times when the exam includes PA + lateral views. Same report text, different DICOM files.

### Text Deduplication Rule

Deterministic, no LLM inference:
1. `text.strip()` — leading/trailing whitespace only
2. `re.sub(r'\s+', ' ', text)` — collapse internal whitespace to single space
3. `unicodedata.normalize('NFC', text)` — canonical Unicode normalization for PT accents
4. No case change — preserve original casing
5. `hashlib.sha256(text.encode('utf-8')).hexdigest()` → `report_hash`

Two reports with the same `report_hash` get the exact same extraction. Reports differing by even one character get their own extraction.

---

## v6 → v7 Changes

| v6 Feature | v7 Decision | Why |
|---|---|---|
| "Ground truth" terminology | **"Reference labels" (silver standard)** | LLM-extracted labels are not gold standard. Honest terminology; human adjudication validates the silver standard. |
| 18 CXR findings vocabulary | **40 findings with metadata (priority, type, acuity, hierarchy)** | Added musculoskeletal, vascular, device, structural, soft_tissue. Config-driven with CRITICAL/HIGH/MODERATE/LOW tiers. |
| Hardcoded prompt text | **Config-driven prompt generation (Stage 0.5)** | `prompt_generator.py` reads `findings_cxr.yaml`, generates prompt with all 40 findings + PT synonyms. Change YAML → regenerate prompt. |
| max_tokens=1024 | **max_tokens=4096** | 40 findings + other_findings + study_quality need more output space. |
| No post-extraction validation | **6 validation rules + acute_classification (Stage 1.5)** | Ghost-abnormal, critical override, high uncertainty, critical on suboptimal, device without position, hierarchy inconsistency. |
| No Tier 2 discovery | **Tier 2 discovery aggregation (Stage 1.75)** | `other_findings` parsed from LLM, aggregated with synonym map + stem dedup. Promotion candidates identified. |
| No PT NLP rules | **Portuguese NLP rule checks** | `pt_rules.py` catches negation/hedging/chronicity conflicts in evidence spans. |
| Sync extraction only | **Async concurrent extraction (20 concurrent, configurable)** | `extract_async()` with semaphore, exponential backoff retry (3 retries). 1,163 reports in ~4 min. |
| Single ExtractionResult model | **ValidatedExtraction inherits ExtractionResult** | Adds priority_level, needs_review, review_reasons, acute_classification, rule_warnings. |
| Status access varies per module | **`get_finding_status()` centralized in models.py** | Single utility for all status access. No more ad-hoc `data.get("status", "Absent")`. |
| No ontology versioning | **Provenance fields: ontology_version, extraction_schema** | Every extraction record carries the ontology version and schema version used. |
| No run manifest | **Run manifest emitted per run** | `run_manifest.py` captures frozen versions (git commit, YAML hash, prompt hash, model versions). |
| No label interpretation maps | **Named label maps (strict, broad, parenchymal_opacity)** | `label_maps.py` prevents ad-hoc 5-state → binary interpretation in notebooks. |
| Basic inter-model comparison | **Hierarchical agreement roll-up + calibrated arbitration** | Child Positive covers parent (consolidation → lung_opacity). Etiologic findings downgrade conservatively. |
| Backup files in glob results | **Backup file exclusion from extraction globs** | `comparison.py` skips files with "backup" or "_v1_" in name. |
| 82 tests | **228 tests** | Full coverage for config, validation, discovery, PT rules, label maps, comparison, arbitration. |
| `dataclass.to_dict()` custom methods | **`dataclasses.asdict()` for serialization** | Standard library, consistent serialization. |
| Config loaded per module | **Config loaded once via `@lru_cache`, passed through** | `config.py` centralizes all YAML parsing. No raw `yaml.safe_load` elsewhere. |
| Device findings hardcoded | **Device findings derived from config type=device_presence** | Adding a device = one YAML entry. No code changes needed. |
| No study quality assessment | **study_quality + study_quality_flags in extraction** | LLM assesses technical quality. 7 defined flags (bedside, rotation, hyperinflation, etc.). |
| `ground_truth/` output directory | **`reference_labels/` output directory** | Terminology alignment. These are reference labels, not ground truth. |

---

## Architecture

### Master Diagram: End-to-End Pipeline

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                      ║
║    YOUR TELEMEDICINE DATABASE (anonymized, 500K+ exams)                              ║
║    ┌─────────────────────────────────────────────────────┐                           ║
║    │  exam_id │ report_text (PT)  │ dicom_path           │                           ║
║    │  CXR001  │ "Tórax normal..." │ dicoms/CXR001.dcm   │                           ║
║    │  CXR002  │ "Cardiomegalia.." │ dicoms/CXR002.dcm   │                           ║
║    │  ...     │ ...               │ ...                  │  Phase 1: 5K CXR          ║
║    │  MSK001  │ "Fratura de..."   │ dicoms/MSK001.dcm   │  Phase 2: 5K other        ║
║    └─────────────────────────────────────────────────────┘                           ║
║                          │                                                           ║
╚══════════════════════════╪═══════════════════════════════════════════════════════════╝
                           │
      ┌────────────────────┼────────────────────┐
      │                    │                    │
      ▼                    ▼                    ▼
  report_text         dicom_path            metadata
  (Portuguese)        (DICOM files)         (tags, quality)
      │                    │                    │
      │                    └────────┬───────────┘
      │                             │
      │                             ▼
      │               ┌──────────────────────────────────────────────┐
      │               │  STEP 0: VALIDATE                            │
      │               │  scripts/00_ingest.py                        │
      │               │  ┌────────────────────────────────────────┐  │
      │               │  │ ✓ CSV integrity (missing fields?)      │  │
      │               │  │ ✓ Report text normalization + SHA-256   │  │
      │               │  │ ✓ DICOM filename extraction from URL   │  │
      │               │  │ ✓ Exam-level grouping (6,542 exams)    │  │
      │               │  │ ✓ Report deduplication (1,163 unique)  │  │
      │               │  │ ✓ Garbage report rejection (<10 chars) │  │
      │               │  └────────────────────────────────────────┘  │
      │               │  Local CPU │ Instant │ $0                    │
      │               └──────────┬───────────────────────────────────┘
      │                          │
      │                          ├──→ output/exam_registry.jsonl (6,542 exams)
      │                          └──→ output/unique_reports.jsonl (1,163 unique)
      │                          │
╔═════╪══════════════════════════╪════════════════════════════════════════════════════╗
║     │    STAGE 0.5: GENERATE EXTRACTION PROMPT                                     ║
║     │                          │                                                    ║
║     │                          ▼                                                    ║
║     │  ┌────────────────────────────────────────────────────────────────────────┐   ║
║     │  │  scripts/00b_generate_prompt.py                                       │   ║
║     │  │                                                                        │   ║
║     │  │  config/findings_cxr.yaml ──→ prompt_generator.py ──→ extract_cxr_pt  │   ║
║     │  │                                                                        │   ║
║     │  │  • Reads 40 findings from YAML (categories, PT synonyms, devices)     │   ║
║     │  │  • Generates prompt with all Tier 1 finding names                      │   ║
║     │  │  • Includes PT synonym hints per category                              │   ║
║     │  │  • Adds device tracking instructions                                   │   ║
║     │  │  • Adds study quality assessment section                               │   ║
║     │  │  • Adds Tier 2 other_findings discovery instruction                   │   ║
║     │  │  • Computes SHA-256 prompt hash for staleness detection                │   ║
║     │  │                                                                        │   ║
║     │  │  Local CPU │ Instant │ $0                                              │   ║
║     │  └────────────────────────────────────────────────────────────────────────┘   ║
║     │                          │                                                    ║
║     │                          └──→ config/prompts/extract_cxr_pt.txt              ║
║     │                          │                                                    ║
╚═════╪══════════════════════════╪════════════════════════════════════════════════════╝
      │                          │
╔═════╪══════════════════════════╪════════════════════════════════════════════════════╗
║     │    STAGE 1: EXTRACT REFERENCE LABELS (Text → Structured Labels)              ║
║     │                          │                                                    ║
║     ▼                          │                                                    ║
║  ┌──────────────────────────────────────────────────────────────────────────────┐   ║
║  │  STEP 1: EXTRACT LABELS                                                      │   ║
║  │  scripts/01_extract_labels.py                                                │   ║
║  │                                                                              │   ║
║  │  ┌─────────────────────┐     ┌──────────────────────────────────────────┐   │   ║
║  │  │ Portuguese Report   │     │  ExtractionBackend (ABC)                │   │   ║
║  │  │                     │     │  ┌──────────────┐  ┌──────────────┐     │   │   ║
║  │  │ "Área cardíaca      │────▶│  │ Sonnet 4.6   │  │  Opus 4.6   │     │   │   ║
║  │  │  dentro dos limites.│     │  │ (primary)    │  │ (validation) │     │   │   ║
║  │  │  Campos pulmonares  │     │  └──────────────┘  └──────────────┘     │   │   ║
║  │  │  sem opacidades.    │     │                                          │   │   ║
║  │  │  Seios costofrênicos│     │  Config: extraction_models.yaml          │   │   ║
║  │  │  livres."           │     │  Async concurrent (20 parallel)          │   │   ║
║  │  │                     │     │  Retry: 3x exponential backoff           │   │   ║
║  │  └─────────────────────┘     │                                          │   │   ║
║  │                              │  Extraction Prompt (auto-generated):      │   │   ║
║  │                              │  1. Classification: normal/abnormal       │   │   ║
║  │                              │  2. 40 findings × status (5-state)       │   │   ║
║  │                              │  3. other_findings (Tier 2 discovery)     │   │   ║
║  │                              │  4. study_quality + flags                 │   │   ║
║  │                              │  5. Evidence: exact PT quote              │   │   ║
║  │                              │                                          │   │   ║
║  │                              │  Handles PT negation:                    │   │   ║
║  │                              │  "sem sinais de", "não se observa",     │   │   ║
║  │                              │  "ausência de", "dentro dos limites"    │   │   ║
║  │                              │                                          │   │   ║
║  │                              │  Handles PT uncertainty:                 │   │   ║
║  │                              │  "não se pode excluir", "possível",     │   │   ║
║  │                              │  "sugestivo de", "a esclarecer"         │   │   ║
║  │                              └──────────────────────────────────────────┘   │   ║
║  │                                           │                                │   ║
║  │                                           ▼                                │   ║
║  │  ┌───────────────────────────────────────────────────────────────────┐     │   ║
║  │  │ Output per report:                                                │     │   ║
║  │  │ {                                                                 │     │   ║
║  │  │   "report_hash": "a1b2c3...",                                    │     │   ║
║  │  │   "classification": "normal",          ◄── Track A: Binary       │     │   ║
║  │  │   "findings": {                        ◄── Track B: Sub-class    │     │   ║
║  │  │     "cardiomegaly": {                                             │     │   ║
║  │  │       "status": "Negative",                                       │     │   ║
║  │  │       "confidence": "high",                                       │     │   ║
║  │  │       "evidence": "Área cardíaca dentro dos limites"              │     │   ║
║  │  │     },                                                            │     │   ║
║  │  │     "effusion": {"status": "Negative", ...},                      │     │   ║
║  │  │     "pneumothorax": {"status": "Absent", ...},                    │     │   ║
║  │  │     ...40 findings total...                                       │     │   ║
║  │  │   },                                                              │     │   ║
║  │  │   "other_findings": [...],             ◄── Tier 2 discovery      │     │   ║
║  │  │   "study_quality": "adequate",         ◄── Quality assessment    │     │   ║
║  │  │   "study_quality_flags": [],                                      │     │   ║
║  │  │   "ontology_version": "2.0.0",         ◄── Provenance            │     │   ║
║  │  │   "extraction_schema": "v2"                                       │     │   ║
║  │  │ }                                                                 │     │   ║
║  │  └───────────────────────────────────────────────────────────────────┘     │   ║
║  │                                                                            │   ║
║  │  + Run manifest emitted (frozen versions for audit)                        │   ║
║  │  + Prompt staleness warning if config changed since last generation        │   ║
║  │                                                                            │   ║
║  │  Anthropic API │ ~$3-6 for 5K (Sonnet+Opus) │ ~4 min (async) │ temp=0    │   ║
║  └──────────────────────────────────────────────────────────────────────────────┘   ║
║                              │                                                      ║
╚══════════════════════════════╪══════════════════════════════════════════════════════╝
                               │
╔══════════════════════════════╪══════════════════════════════════════════════════════╗
║     STAGE 1.5: POST-EXTRACTION VALIDATION                                           ║
║                              │                                                      ║
║                              ▼                                                      ║
║  ┌──────────────────────────────────────────────────────────────────────────────┐   ║
║  │  scripts/01a_validate_extractions.py                                         │   ║
║  │                                                                              │   ║
║  │  6 REVIEW RULES (never downgrade, only upgrade):                            │   ║
║  │                                                                              │   ║
║  │  1. Ghost-abnormal — classification=abnormal, no Positive/Uncertain         │   ║
║  │     → flag for review                                                        │   ║
║  │                                                                              │   ║
║  │  2. Critical-finding override — classification=normal, CRITICAL finding      │   ║
║  │     → upgrade to abnormal, flag for review                                   │   ║
║  │                                                                              │   ║
║  │  3. High uncertainty — 3+ Uncertain findings                                │   ║
║  │     → flag for review                                                        │   ║
║  │                                                                              │   ║
║  │  4. Critical on suboptimal — CRITICAL finding on suboptimal study           │   ║
║  │     → flag for review                                                        │   ║
║  │                                                                              │   ║
║  │  5. Device without position — device present, malposition not assessed      │   ║
║  │     → flag for review                                                        │   ║
║  │                                                                              │   ║
║  │  6. Hierarchy inconsistency — child Positive, parent Absent                 │   ║
║  │     (e.g., consolidation=Positive but lung_opacity=Absent)                   │   ║
║  │     → flag for review                                                        │   ║
║  │                                                                              │   ║
║  │  PLUS:                                                                       │   ║
║  │  • Triage priority (CRITICAL/HIGH/MODERATE/LOW/NONE) from highest finding   │   ║
║  │  • Acute classification (abnormal if any acute/context_dependent Positive)   │   ║
║  │  • PT rule checks (negation/hedging consistency via pt_rules.py)            │   ║
║  │                                                                              │   ║
║  │  ExtractionResult → ValidatedExtraction (inherits, adds triage fields)      │   ║
║  │  Local CPU │ Instant │ $0                                                    │   ║
║  └──────────────────────────────────────────────────────────────────────────────┘   ║
║                              │                                                      ║
║                              ├──→ output/reference_labels/validated_{model}.jsonl   ║
║                              └──→ output/reference_labels/needs_review.jsonl        ║
║                              │                                                      ║
╚══════════════════════════════╪══════════════════════════════════════════════════════╝
                               │
╔══════════════════════════════╪══════════════════════════════════════════════════════╗
║     STAGE 1.75: TIER 2 DISCOVERY AGGREGATION                                       ║
║                              │                                                      ║
║                              ▼                                                      ║
║  ┌──────────────────────────────────────────────────────────────────────────────┐   ║
║  │  scripts/01c_discovery_report.py                                             │   ║
║  │                                                                              │   ║
║  │  Aggregates other_findings across all extraction files:                      │   ║
║  │                                                                              │   ║
║  │  1. Synonym map (config/tier2_synonyms.yaml) — deterministic first pass     │   ║
║  │     hilar_enlargement → hilar_prominence                                     │   ║
║  │     peribronchial_thickening → bronchial_wall_thickening                     │   ║
║  │                                                                              │   ║
║  │  2. Stem dedup (fallback) — word-stem canonical keys                        │   ║
║  │     convex_diaphragm + diaphragm_convexity → same canonical key             │   ║
║  │     Most frequent name wins as canonical                                     │   ║
║  │                                                                              │   ║
║  │  3. Promotion candidates — prevalence >= 2%, count >= 10                    │   ║
║  │     Candidates for promotion to Tier 1 in next ontology version              │   ║
║  │                                                                              │   ║
║  │  Local CPU │ Instant │ $0                                                    │   ║
║  └──────────────────────────────────────────────────────────────────────────────┘   ║
║                              │                                                      ║
║                              └──→ output/reference_labels/discovery_report.json     ║
║                              │                                                      ║
╚══════════════════════════════╪══════════════════════════════════════════════════════╝
                               │
╔══════════════════════════════╪══════════════════════════════════════════════════════╗
║     STAGE 1b: INTER-MODEL COMPARISON                                                ║
║                              │                                                      ║
║                              ▼                                                      ║
║  ┌──────────────────────────────────────────────────────────────────────────────┐   ║
║  │  scripts/01b_compare_extractions.py                                          │   ║
║  │                                                                              │   ║
║  │  Compare Sonnet vs Opus (or N models):                                      │   ║
║  │                                                                              │   ║
║  │  1. Hierarchical agreement roll-up                                          │   ║
║  │     consolidation=Positive covers lung_opacity → agreement not penalized     │   ║
║  │                                                                              │   ║
║  │  2. Calibrated arbitration rules (comparison.py):                           │   ║
║  │     • Agreement → accept                                                     │   ║
║  │     • Positive vs Uncertain on etiologic → Uncertain (conservative)          │   ║
║  │     • Positive vs Uncertain on descriptive → needs review                    │   ║
║  │     • Absent vs Positive → keep Positive, flag for review                    │   ║
║  │     • Negative vs Absent → accept Negative (more specific)                   │   ║
║  │     • Not_Assessable vs anything → Not_Assessable (conservative)             │   ║
║  │                                                                              │   ║
║  │  3. Select primary model → selected_extractions.jsonl                       │   ║
║  │                                                                              │   ║
║  │  Local CPU │ Instant │ $0                                                    │   ║
║  └──────────────────────────────────────────────────────────────────────────────┘   ║
║                              │                                                      ║
║                              ├──→ output/reference_labels/agreement_report.json     ║
║                              ├──→ output/reference_labels/disagreements.jsonl       ║
║                              ├──→ output/reference_labels/per_report_agreement.json ║
║                              └──→ output/reference_labels/selected_extractions.jsonl║
║                              │                                                      ║
╚══════════════════════════════╪══════════════════════════════════════════════════════╝
                               │
╔══════════════════════════════╪══════════════════════════════════════════════════════╗
║     STAGE 2: BUILD BALANCED EVALUATION DATASET                                      ║
║                              │                                                      ║
║                              ▼                                                      ║
║  ┌──────────────────────────────────────────────────────────────────────────────┐   ║
║  │  STEP 2: BUILD REFERENCE LABELS                                              │   ║
║  │  scripts/02_build_ground_truth.py                                            │   ║
║  │                                                                              │   ║
║  │  5K labeled reports                                                          │   ║
║  │       │                                                                      │   ║
║  │       ├──→ Count: ~250 abnormal (5%) + ~4,750 normal (95%)   ◄── hypothesis │   ║
║  │       │                                                                      │   ║
║  │       ▼                                                                      │   ║
║  │  ┌────────────────────────────────────────────────────────────────┐          │   ║
║  │  │  BALANCED SET (for unbiased evaluation):                       │          │   ║
║  │  │                                                                │          │   ║
║  │  │  ALL abnormals ──────────────────────────── ~250 studies       │          │   ║
║  │  │       +                                                        │          │   ║
║  │  │  Random sample of normals ───────────────── ~250 studies       │          │   ║
║  │  │       =                                                        │          │   ║
║  │  │  Balanced reference labels ────────────────── ~500 studies     │          │   ║
║  │  │  (50% abnormal / 50% normal)                                   │          │   ║
║  │  │                                                                │          │   ║
║  │  │  Stratified by:                                                │          │   ║
║  │  │  • finding type (which pathologies present)                    │          │   ║
║  │  │  • quality flags (bedside, rotation, etc.)                     │          │   ║
║  │  │  • view position (PA vs AP)                                    │          │   ║
║  │  │  • priority level (CRITICAL/HIGH/MODERATE/LOW)                 │          │   ║
║  │  └────────────────────────────────────────────────────────────────┘          │   ║
║  │                                                                              │   ║
║  │  Also produces:                                                              │   ║
║  │  • Finding prevalence table (which findings appear, how often)               │   ║
║  │  • Quality distribution (how many suboptimal, which flags)                   │   ║
║  │  • Priority distribution (CRITICAL/HIGH/MODERATE/LOW)                        │   ║
║  │  • Needs-review count                                                        │   ║
║  │  • Flag comparison (Sonnet vs original CSV label)                            │   ║
║  │                                                                              │   ║
║  │  Local CPU │ Instant │ $0                                                    │   ║
║  └──────────────────────────────────────────────────────────────────────────────┘   ║
║                              │                                                      ║
║                              ├──→ output/reference_labels/labels.jsonl              ║
║                              ├──→ output/reference_labels/balanced.csv              ║
║                              ├──→ output/reference_labels/statistics.json           ║
║                              └──→ output/reference_labels/flag_comparison.json      ║
║                              │                                                      ║
╚══════════════════════════════╪══════════════════════════════════════════════════════╝
                               │
                               │  balanced.csv = THE CORE EVALUATION ASSET
                               │  (exam_id + classification + findings + metadata)
                               │
╔══════════════════════════════╪══════════════════════════════════════════════════════╗
║     STAGE 3: VISION MODEL BAKEOFF                                                   ║
║                              │                                                      ║
║                              ▼                                                      ║
║  ┌──────────────────────────────────────────────────────────────────────────────┐   ║
║  │  STEP 3: RUN VISION MODELS                                                   │   ║
║  │  scripts/03_run_models.py                                                    │   ║
║  │                                                                              │   ║
║  │  For each DICOM in balanced set, run ALL registered backends:                │   ║
║  │                                                                              │   ║
║  │  DICOM ──→ load pixels ──→ preprocess ──┬──────────────────────────────────  │   ║
║  │                                         │                                    │   ║
║  │         ┌───────────────────────────────┐│                                   │   ║
║  │         │                               ││                                   │   ║
║  │         ▼                               ▼│                                   │   ║
║  │  ┌─────────────────┐  ┌─────────────────┐│  ┌─────────────────┐             │   ║
║  │  │  MedSigLIP      │  │  TorchXRayVision││  │  MedGemma 4B    │             │   ║
║  │  │  (zero-shot)    │  │  (18-class)     ││  │  (multimodal)   │             │   ║
║  │  │                 │  │                 ││  │                 │             │   ║
║  │  │  PyTorch + MPS  │  │  PyTorch + CPU  ││  │  GCP Vertex AI  │             │   ║
║  │  │  ~500ms/img     │  │  ~100ms/img     ││  │  ~2s/img        │             │   ║
║  │  │  84.4% mAUC     │  │  81.1% mAUC     ││  │  VLM-based      │             │   ║
║  │  │  $0             │  │  $0             ││  │  ~$2/run        │             │   ║
║  │  │                 │  │                 ││  │                 │             │   ║
║  │  │  sigmoid scores │  │  sigmoid scores ││  │  JSON labels    │             │   ║
║  │  │  per finding    │  │  per finding    ││  │  per finding    │             │   ║
║  │  └────────┬────────┘  └────────┬────────┘│  └────────┬────────┘             │   ║
║  │           │                    │          │           │                      │   ║
║  │           ▼                    ▼          │           ▼                      │   ║
║  │  ┌─────────────────┐  ┌─────────────────┐│  ┌─────────────────┐             │   ║
║  │  │  GPT Vision     │  │  Gemini Vision  ││  │  (Future model) │             │   ║
║  │  │  (optional)     │  │  (optional)     ││  │                 │             │   ║
║  │  │  OpenAI API     │  │  Google API     ││  │  Add 1 file in  │             │   ║
║  │  │  ~$10/run       │  │  ~$5/run        ││  │  src/backends/  │             │   ║
║  │  └────────┬────────┘  └────────┬────────┘│  └────────┬────────┘             │   ║
║  │           │                    │          │           │                      │   ║
║  │           └──────────┬─────────┘──────────┘───────────┘                     │   ║
║  │                      │                                                      │   ║
║  │                      ▼                                                      │   ║
║  │           Common output format per model:                                   │   ║
║  │           {                                                                 │   ║
║  │             "exam_id": "CXR001",                                            │   ║
║  │             "model_name": "medsiglip",                                      │   ║
║  │             "binary_label": "abnormal",                                     │   ║
║  │             "binary_score": 0.73,                                           │   ║
║  │             "findings": {                                                   │   ║
║  │               "cardiomegaly": {"label": "Positive", "score": 0.73},         │   ║
║  │               "effusion": {"label": "Negative", "score": 0.12},             │   ║
║  │               ...                                                           │   ║
║  │             }                                                               │   ║
║  │           }                                                                 │   ║
║  │                                                                              │   ║
║  │  Checkpointed per image │ Resume on failure │ One JSONL per model            │   ║
║  └──────────────────────────────────────────────────────────────────────────────┘   ║
║                              │                                                      ║
║                              ├──→ output/predictions/medsiglip.jsonl                ║
║                              ├──→ output/predictions/torchxrayvision.jsonl           ║
║                              ├──→ output/predictions/medgemma_vision.jsonl           ║
║                              └──→ output/predictions/{new_model}.jsonl               ║
║                              │                                                      ║
╚══════════════════════════════╪══════════════════════════════════════════════════════╝
                               │
╔══════════════════════════════╪══════════════════════════════════════════════════════╗
║     STAGE 4: EVALUATE & COMPARE                                                     ║
║                              │                                                      ║
║         reference_labels/    │   predictions/                                       ║
║              balanced.csv ───┼──→ *.jsonl (per model)                               ║
║                              │                                                      ║
║                              ▼                                                      ║
║  ┌──────────────────────────────────────────────────────────────────────────────┐   ║
║  │  STEP 4: EVALUATE                                                            │   ║
║  │  scripts/04_evaluate.py                                                      │   ║
║  │                                                                              │   ║
║  │  ┌────────────────────────────────────────────────────────────────────┐      │   ║
║  │  │  TRACK A: Binary Evaluation (normal vs abnormal)                   │      │   ║
║  │  │                                                                    │      │   ║
║  │  │  Per model:                                                        │      │   ║
║  │  │  ┌─────────────────────────────────────┐                           │      │   ║
║  │  │  │         CONFUSION MATRIX            │                           │      │   ║
║  │  │  │                                     │                           │      │   ║
║  │  │  │              Predicted               │                           │      │   ║
║  │  │  │              Normal  Abnormal        │                           │      │   ║
║  │  │  │  Actual  ┌────────┬──────────┐      │                           │      │   ║
║  │  │  │  Normal  │   TN   │    FP    │      │                           │      │   ║
║  │  │  │          ├────────┼──────────┤      │                           │      │   ║
║  │  │  │  Abnml   │   FN   │    TP    │      │                           │      │   ║
║  │  │  │          └────────┴──────────┘      │                           │      │   ║
║  │  │  │                                     │                           │      │   ║
║  │  │  │  Metrics: Sensitivity, Specificity, │                           │      │   ║
║  │  │  │  PPV, NPV, F1, AUROC                │                           │      │   ║
║  │  │  └─────────────────────────────────────┘                           │      │   ║
║  │  └────────────────────────────────────────────────────────────────────┘      │   ║
║  │                                                                              │   ║
║  │  ┌────────────────────────────────────────────────────────────────────┐      │   ║
║  │  │  TRACK B: Per-Finding Evaluation (40 chest findings)               │      │   ║
║  │  │                                                                    │      │   ║
║  │  │  Per model × per finding:                                          │      │   ║
║  │  │  ┌──────────────────────────────────────────────────────────┐     │      │   ║
║  │  │  │ Finding          │ AUROC │ AUPRC │ Sens  │ Spec  │ N+   │     │      │   ║
║  │  │  │──────────────────┼───────┼───────┼───────┼───────┼──────│     │      │   ║
║  │  │  │ cardiomegaly     │ 0.891 │ 0.723 │ 0.847 │ 0.912 │  85  │     │      │   ║
║  │  │  │ effusion         │ 0.923 │ 0.812 │ 0.890 │ 0.934 │  62  │     │      │   ║
║  │  │  │ atelectasis      │ 0.834 │ 0.601 │ 0.781 │ 0.876 │  43  │     │      │   ║
║  │  │  │ pneumothorax     │ 0.912 │ 0.654 │ 0.857 │ 0.945 │  14  │     │      │   ║
║  │  │  │ ...              │  ...  │  ...  │  ...  │  ...  │ ...  │     │      │   ║
║  │  │  │ MEAN             │ 0.878 │  ---  │  ---  │  ---  │  --- │     │      │   ║
║  │  │  └──────────────────────────────────────────────────────────┘     │      │   ║
║  │  └────────────────────────────────────────────────────────────────────┘      │   ║
║  │                                                                              │   ║
║  │  ┌────────────────────────────────────────────────────────────────────┐      │   ║
║  │  │  CROSS-MODEL COMPARISON TABLE                                      │      │   ║
║  │  │                                                                    │      │   ║
║  │  │  Model            │ Binary  │ Binary │ Binary │ Findings │         │      │   ║
║  │  │                   │ AUROC   │ Sens   │ Spec   │ mAUROC   │         │      │   ║
║  │  │  ─────────────────┼─────────┼────────┼────────┼──────────│         │      │   ║
║  │  │  MedSigLIP        │  0.892  │ 0.856  │ 0.901  │  0.878   │ ◄ ?    │      │   ║
║  │  │  TorchXRayVision  │  0.841  │ 0.812  │ 0.867  │  0.823   │        │      │   ║
║  │  │  MedGemma 4B      │  0.878  │ 0.834  │ 0.889  │  0.861   │        │      │   ║
║  │  │  GPT Vision       │  0.901  │ 0.867  │ 0.912  │  0.889   │ ◄ ?    │      │   ║
║  │  │  Gemini Vision    │  0.889  │ 0.845  │ 0.905  │  0.871   │        │      │   ║
║  │  │                                   (example numbers — TBD)          │      │   ║
║  │  └────────────────────────────────────────────────────────────────────┘      │   ║
║  │                                                                              │   ║
║  │  ┌────────────────────────────────────────────────────────────────────┐      │   ║
║  │  │  RECOMMENDED THRESHOLDS (for Playbook v4)                          │      │   ║
║  │  │                                                                    │      │   ║
║  │  │  Per finding, from best model, Youden's J optimal:                 │      │   ║
║  │  │  {                                                                 │      │   ║
║  │  │    "cardiomegaly": {"optimal": 0.42, "low": 0.29, "high": 0.42}, │      │   ║
║  │  │    "effusion":     {"optimal": 0.38, "low": 0.27, "high": 0.38}, │      │   ║
║  │  │    ...                                                             │      │   ║
║  │  │  }                                                                 │      │   ║
║  │  │  → feeds directly into Playbook v4 config/thresholds.yaml         │      │   ║
║  │  └────────────────────────────────────────────────────────────────────┘      │   ║
║  │                                                                              │   ║
║  │  + ROC curve plots (PNG per model per finding)                               │   ║
║  │  + Confusion matrix plots (PNG per model)                                    │   ║
║  │                                                                              │   ║
║  │  Local CPU │ Instant │ $0                                                    │   ║
║  └──────────────────────────────────────────────────────────────────────────────┘   ║
║                              │                                                      ║
╚══════════════════════════════╪══════════════════════════════════════════════════════╝
                               │
                               ▼
╔══════════════════════════════════════════════════════════════════════════════════════╗
║     MVP v7 OUTPUTS (standalone value)                                                ║
║                                                                                      ║
║  output/                                                                             ║
║  ├── exam_registry.jsonl              ← Step 0: one row per exam_id (6,542)         ║
║  ├── unique_reports.jsonl             ← Step 0: one row per report_hash (1,163)     ║
║  ├── ingest_errors.jsonl              ← Step 0: rejected reports                    ║
║  ├── reference_labels/                                                               ║
║  │   ├── extractions_{model}.jsonl    ← Step 1: per-model extraction results       ║
║  │   ├── extraction_errors_{model}.jsonl  ← Step 1: failed extractions              ║
║  │   ├── run_manifest.json            ← Step 1: frozen version metadata             ║
║  │   ├── validated_{model}.jsonl      ← Step 1.5: post-validation with triage       ║
║  │   ├── needs_review.jsonl           ← Step 1.5: extractions needing review        ║
║  │   ├── discovery_report.json        ← Step 1.75: Tier 2 aggregation              ║
║  │   ├── agreement_report.json        ← Step 1b: inter-model agreement stats       ║
║  │   ├── disagreements.jsonl          ← Step 1b: per-report disagreement details    ║
║  │   ├── per_report_agreement.json    ← Step 1b: per-hash agreement scores         ║
║  │   ├── selected_extractions.jsonl   ← Step 1b: primary model selected labels     ║
║  │   ├── labels.jsonl                 ← Step 2: one row per exam_id (labeled)       ║
║  │   ├── flag_comparison.json         ← Step 2: Sonnet vs original flag agreement   ║
║  │   ├── balanced.csv                 ← Step 2: balanced eval set (THE asset)       ║
║  │   └── statistics.json              ← Step 2: dataset composition + prevalence    ║
║  ├── predictions/                                                                    ║
║  │   ├── medsiglip.jsonl              ← per-model predictions on balanced set       ║
║  │   ├── torchxrayvision.jsonl                                                       ║
║  │   └── {new_model}.jsonl            ← add model = add file here                  ║
║  ├── evaluation/                                                                     ║
║  │   ├── bakeoff_binary.json          ← Track A: which model best for normal/abnml? ║
║  │   ├── bakeoff_findings.json        ← Track B: which model best per finding?      ║
║  │   ├── comparison_table.csv         ← ALL models side by side (THE answer)        ║
║  │   ├── recommended_thresholds.json  ← ready for Playbook v4 config               ║
║  │   ├── confusion_matrices/          ← visual proof per model                      ║
║  │   └── roc_curves/                  ← visual proof per finding                    ║
║  └── run_manifest.json                ← full reproducibility metadata               ║
║                                                                                      ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
                               │
                               │  FEEDS INTO
                               ▼
╔══════════════════════════════════════════════════════════════════════════════════════╗
║     PLAYBOOK v4 (Production Pipeline — FUTURE)                                       ║
║                                                                                      ║
║  MVP v7 output                │  Playbook v4 component                               ║
║  ─────────────────────────── │ ──────────────────────────                            ║
║  comparison_table.csv        → Winning model selection                               ║
║  recommended_thresholds.json → config/thresholds.yaml (per-finding)                  ║
║  Portuguese prompt templates → config/prompts.yaml (PT extraction)                   ║
║  reference_labels/balanced.csv → Phase 7.1 validation set (shadow mode)              ║
║  VisionBackend interface     → Same backends plug in (code reuse)                    ║
║  quality_flags               → Quality gate routing rules                            ║
║  finding_prevalence          → Adjudication rule priorities                           ║
║  validation_rules            → Post-extraction QA pipeline                            ║
║  label_maps                  → Task-specific interpretation                           ║
║                                                                                      ║
║  ┌──────────────────────────────────────────────────────────────────────────┐        ║
║  │  Orthanc (DICOM) → Quality Gate → Triage → Vision Model → Adjudicator  │        ║
║  │  → DICOM SR → OHIF Viewer → Radiologist Review → Audit Log             │        ║
║  └──────────────────────────────────────────────────────────────────────────┘        ║
║                                                                                      ║
║  Future workflows enabled by MVP v7 reference labels:                                ║
║  • Alert when text and vision disagree (discrepancy detection)                       ║
║  • Prioritize critical findings in worklist (CRITICAL/HIGH triage)                   ║
║  • Retrospective analysis of 500K+ historical images                                ║
║  • Sub-notification detection (findings that were missed)                            ║
║  • Per-radiologist quality metrics                                                   ║
║  • Multi-body-part model selection (different model per anatomy)                     ║
║                                                                                      ║
╚══════════════════════════════════════════════════════════════════════════════════════╝


MODEL-AGNOSTIC BACKEND ARCHITECTURE (adding a new model):

    src/cxr_mvp/backends/
    ├── __init__.py          ← auto-discovery registry
    ├── base.py              ← VisionBackend ABC
    ├── mock_backend.py      ← deterministic test backend
    ├── medsiglip.py         ← implements VisionBackend
    ├── torchxrayvision.py   ← implements VisionBackend
    ├── medgemma_vision.py   ← implements VisionBackend
    ├── gpt_vision.py        ← implements VisionBackend
    ├── gemini_vision.py     ← implements VisionBackend
    └── your_new_model.py    ← ADD THIS FILE, pipeline works automatically

    class VisionBackend(ABC):
        def name(self) -> str: ...
        def predict(self, pixel_array, dicom_meta) -> {
            "binary_label": "normal" | "abnormal",
            "binary_score": float,
            "findings": {finding: {"label": str, "score": float}},
        }


EXTRACTION BACKEND ARCHITECTURE (adding a new extraction model):

    src/cxr_mvp/extractors/
    ├── __init__.py                ← package init
    ├── base.py                    ← ExtractionBackend ABC
    ├── registry.py                ← config-driven instantiation from extraction_models.yaml
    └── anthropic_extractor.py     ← handles ALL claude-* models (sync + async + retry)

    class ExtractionBackend(ABC):
        def name(self) -> str: ...
        def version(self) -> str: ...              # full model_id for provenance
        def extract(reports, prompt, output_dir) -> list[ExtractionResult]
        def supports_batch(self) -> bool: ...
        async def extract_async(reports, prompt, output_dir, concurrency=20)


DATA FLOW SUMMARY:

    CSV + DICOMs ──→ Ingest ──→ Gen Prompt ──→ Extract (N models, async)
                                                    │
                                                    ├──→ Validate (6 rules + PT checks)
                                                    ├──→ Discover (Tier 2 aggregation)
                                                    └──→ Compare (agreement + arbitrate)
                                                              │
                                                              ▼
                                                    Build Reference Labels
                                                    (join, balance, stats)
                                                              │
                                                 ┌────────────┼────────────┐
                                                 ▼            ▼            ▼
                                             MedSigLIP      TXV      MedGemma 4B  ... N
                                                 │            │            │
                                                 └────────────┼────────────┘
                                                              │
                                                              ▼
                                                         EVALUATE
                                                  (compare all vs ref labels)
                                                              │
                                                              ▼
                                                comparison_table.csv
                                                confusion_matrices/
                                                recommended_thresholds.json
                                                              │
                                                              ▼
                                                PLAYBOOK v4 (production)
```

---

## Ontology: Finding Vocabulary v2

### Label States (aligned with Playbook v3)

```python
class LabelState(str, Enum):
    """5-state label vocabulary. Matches Playbook v3 adjudication rules."""
    POSITIVE = "Positive"           # finding explicitly present
    NEGATIVE = "Negative"           # finding explicitly denied
    UNCERTAIN = "Uncertain"         # hedged language
    ABSENT = "Absent"               # finding not mentioned at all
    NOT_ASSESSABLE = "Not_Assessable"  # report incomplete or unreadable
```

### Named Label Interpretation Maps (`label_maps.py`)

Different downstream tasks need different interpretations of the 5-state labels:

```python
LABEL_MAPS = {
    "strict":               # Positive only → True
    "broad":                # Positive + Uncertain → True
    "parenchymal_opacity":  # any of lung_opacity/consolidation/infiltration Positive → True
}

# Usage:
from cxr_mvp.label_maps import apply_label_map
binary = apply_label_map(extraction["findings"], "broad")
# → {"cardiomegaly": True, "effusion": False, "pneumonia": None, ...}
```

### Binary Mapping (from `config/label_mapping.yaml`)

```yaml
binary_mapping:
  abnormal_states: [Positive, Uncertain]    # conservative: uncertain = abnormal
  normal_states: [Negative, Absent]
  excluded_states: [Not_Assessable]         # excluded from binary metrics
```

### Chest Findings (40) — Full Ontology

Organized by priority, with metadata for type, acuity, category, and hierarchy:

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║  FINDING ONTOLOGY v2 — 40 Findings by Priority                                      ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                      ║
║  CRITICAL (7) — Life-threatening, immediate alert                                    ║
║  ┌───────────────────────┬──────────┬─────────────┬───────────────────┬────────────┐ ║
║  │ Finding               │ Category │ Type        │ Acuity            │ Parent     │ ║
║  ├───────────────────────┼──────────┼─────────────┼───────────────────┼────────────┤ ║
║  │ pneumothorax          │ pulmon.  │ descriptive │ acute             │            │ ║
║  │ effusion              │ pulmon.  │ descriptive │ context_dependent │            │ ║
║  │ pneumonia             │ infect.  │ etiologic   │ acute             │            │ ║
║  │ consolidation         │ pulmon.  │ descriptive │ acute             │ lung_opac. │ ║
║  │ edema                 │ pulmon.  │ descriptive │ acute             │            │ ║
║  │ tuberculosis          │ infect.  │ etiologic   │ acute             │            │ ║
║  │ device_malposition    │ device   │ dev_posit.  │ acute             │            │ ║
║  └───────────────────────┴──────────┴─────────────┴───────────────────┴────────────┘ ║
║                                                                                      ║
║  HIGH (8) — Clinically significant, prioritize reading                               ║
║  ┌───────────────────────┬──────────┬─────────────┬───────────────────┬────────────┐ ║
║  │ cardiomegaly          │ pulmon.  │ descriptive │ context_dependent │            │ ║
║  │ mass                  │ pulmon.  │ descriptive │ context_dependent │            │ ║
║  │ nodule                │ pulmon.  │ descriptive │ context_dependent │            │ ║
║  │ atelectasis           │ pulmon.  │ descriptive │ context_dependent │            │ ║
║  │ lung_lesion           │ pulmon.  │ descriptive │ context_dependent │            │ ║
║  │ aortic_aneurysm       │ vascular │ descriptive │ context_dependent │            │ ║
║  │ mediastinal_shift     │ struct.  │ descriptive │ acute             │            │ ║
║  │ pulmonary_hypertension│ vascular │ descriptive │ context_dependent │            │ ║
║  └───────────────────────┴──────────┴─────────────┴───────────────────┴────────────┘ ║
║                                                                                      ║
║  MODERATE (13) — Important, standard reporting                                       ║
║  ┌───────────────────────┬──────────┬─────────────┬───────────────────┬────────────┐ ║
║  │ lung_opacity          │ pulmon.  │ descriptive │ context_dependent │            │ ║
║  │ infiltration          │ pulmon.  │ descriptive │ context_dependent │ lung_opac. │ ║
║  │ enlarged_cardiomed.   │ struct.  │ descriptive │ context_dependent │            │ ║
║  │ pleural_thickening    │ pulmon.  │ descriptive │ chronic           │            │ ║
║  │ fracture              │ msk      │ descriptive │ context_dependent │            │ ║
║  │ vascular_congestion   │ vascular │ descriptive │ acute             │            │ ║
║  │ diaphragm_elevation   │ struct.  │ descriptive │ context_dependent │            │ ║
║  │ subcutaneous_emphysema│ soft_tis │ descriptive │ acute             │            │ ║
║  │ endotracheal_tube     │ device   │ dev_pres.   │ context_dependent │            │ ║
║  │ central_line          │ device   │ dev_pres.   │ context_dependent │            │ ║
║  │ feeding_tube          │ device   │ dev_pres.   │ context_dependent │            │ ║
║  │ chest_drain           │ device   │ dev_pres.   │ context_dependent │            │ ║
║  │ cardiac_device        │ device   │ dev_pres.   │ context_dependent │            │ ║
║  └───────────────────────┴──────────┴─────────────┴───────────────────┴────────────┘ ║
║                                                                                      ║
║  LOW (12) — Chronic/incidental, population health value                              ║
║  ┌───────────────────────┬──────────┬─────────────┬───────────────────┬────────────┐ ║
║  │ emphysema             │ pulmon.  │ descriptive │ chronic           │            │ ║
║  │ fibrosis              │ pulmon.  │ descriptive │ chronic           │            │ ║
║  │ hernia                │ struct.  │ descriptive │ chronic           │            │ ║
║  │ spondylosis           │ msk      │ descriptive │ chronic           │            │ ║
║  │ aortic_atherosclerosis│ vascular │ descriptive │ chronic           │            │ ║
║  │ aortic_elongation     │ vascular │ descriptive │ chronic           │            │ ║
║  │ osteoporosis          │ msk      │ descriptive │ chronic           │            │ ║
║  │ scoliosis             │ msk      │ descriptive │ chronic           │            │ ║
║  │ vertebral_compression │ msk      │ descriptive │ context_dependent │            │ ║
║  │ rib_anomaly           │ msk      │ descriptive │ incidental        │            │ ║
║  │ calcified_granuloma   │ pulmon.  │ descriptive │ incidental        │            │ ║
║  │ surgical_hardware     │ device   │ dev_pres.   │ incidental        │            │ ║
║  └───────────────────────┴──────────┴─────────────┴───────────────────┴────────────┘ ║
║                                                                                      ║
║  Hierarchy:  lung_opacity → consolidation, infiltration                              ║
║              (child Positive implies parent Positive)                                ║
║                                                                                      ║
║  Type summary:  descriptive=30  etiologic=2  device_presence=7  device_position=1   ║
║  Acuity summary: acute=8  chronic=9  incidental=3  context_dependent=20             ║
║  Categories: pulmonary(14) infectious(2) msk(6) vascular(4) device(8) structural(4) ║
║              soft_tissue(1) + Tier 2 "other"                                         ║
║                                                                                      ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
```

### Tier 2 Dynamic Discovery

Findings not in the 40-finding vocabulary are captured in `other_findings` and aggregated:

```
Tier 1 (vocab):  40 named findings — always extracted, always in output
Tier 2 (discovered): LLM-surfaced additional findings — aggregated across runs

Deduplication pipeline:
  1. Synonym map (config/tier2_synonyms.yaml) — deterministic, auditable
  2. Word-stem canonical keys — fallback for unknown pairs
  3. Most frequent name wins as canonical

Promotion: prevalence >= 2% AND count >= 10 → candidate for Tier 1 in next version
```

### Portuguese Medical Terminology — Negation, Uncertainty, Chronicity

```python
# Portuguese negation patterns (critical for accurate extraction)
PT_NEGATION = [
    "sem sinais de", "sem evidência de", "ausência de",
    "não se observa", "não há", "não se identifica",
    "dentro dos limites", "dentro da normalidade",
    "sem alterações", "aspecto normal", "preservado(s)",
    "contornos preservados", "de aspecto normal",
]

# Portuguese uncertainty patterns
PT_UNCERTAINTY = [
    "não se pode excluir", "não se pode afastar",
    "possível", "provável", "sugestivo de",
    "a esclarecer", "a critério clínico", "a correlacionar",
    "não se descarta",
]

# Chronicity patterns (suggests old/chronic finding)
PT_CHRONICITY = [
    "sequela", "residual", "crônico/a", "antigo/a",
    "prévio/a", "degenerativo/a", "consolidado/a",
]
```

### Study Quality Flags

```yaml
study_quality_flags:
  - bedside        # estudo no leito
  - rotation       # rotacionado
  - hyperinflation # hipoinsuflação/expiração
  - underexposure  # penetração inadequada
  - overexposure   # hiperpenetrado
  - motion         # borramento por movimento
  - incomplete     # laudo incompleto ou ilegível
```

### MSK Findings (10 — Phase 2)

```python
MSK_FINDINGS = {
    "fracture":              {"en": "Fracture",              "pt": ["fratura", "traço de fratura"]},
    "dislocation":           {"en": "Dislocation",           "pt": ["luxação"]},
    "subluxation":           {"en": "Subluxation",           "pt": ["subluxação"]},
    "joint_effusion":        {"en": "Joint Effusion",        "pt": ["derrame articular"]},
    "bone_lesion":           {"en": "Bone Lesion",           "pt": ["lesão óssea"]},
    "osteopenia":            {"en": "Osteopenia",            "pt": ["osteopenia", "osteoporose", "rarefação óssea"]},
    "soft_tissue_swelling":  {"en": "Soft Tissue Swelling",  "pt": ["aumento de partes moles"]},
    "foreign_body":          {"en": "Foreign Body",          "pt": ["corpo estranho"]},
    "hardware":              {"en": "Hardware",              "pt": ["material de síntese", "prótese", "parafuso"]},
    "degenerative_changes":  {"en": "Degenerative Changes",  "pt": ["alterações degenerativas", "artrose", "osteófitos"]},
}
```

### Spine Findings (8 — Phase 2)

```python
SPINE_FINDINGS = {
    "compression_fracture":       {"en": "Compression Fracture",       "pt": ["fratura por compressão", "achatamento vertebral"]},
    "vertebral_height_loss":      {"en": "Vertebral Height Loss",      "pt": ["redução da altura do corpo vertebral"]},
    "degenerative_disc_disease":  {"en": "Degenerative Disc Disease",  "pt": ["discopatia degenerativa", "redução do espaço discal"]},
    "spondylolisthesis":          {"en": "Spondylolisthesis",          "pt": ["espondilolistese", "listese"]},
    "scoliosis":                  {"en": "Scoliosis",                  "pt": ["escoliose", "desvio lateral"]},
    "disc_space_narrowing":       {"en": "Disc Space Narrowing",       "pt": ["pinçamento discal", "redução do espaço discal"]},
    "hardware":                   {"en": "Hardware",                   "pt": ["material de síntese", "artrodese"]},
    "osteopenia":                 {"en": "Osteopenia",                 "pt": ["osteopenia", "rarefação óssea difusa"]},
}
```

---

## Project Structure

```
cxr-mvp/
├── pyproject.toml                   # pytest, ruff, mypy config
├── .env.example                     # API key template
├── ListaLLM.csv                     # 10K rows: exam_id;customer_id;dicom_url;report_text;label
├── config/
│   ├── findings_cxr.yaml           # 40 CXR findings v2 (PT + EN, category, priority, type, acuity, hierarchy)
│   ├── label_mapping.yaml          # 5-state → binary mapping (configurable abnormal_states)
│   ├── extraction_models.yaml      # Multi-model config: provider, model_id, mode, enabled, max_tokens
│   ├── tier2_synonyms.yaml         # Tier 2 synonym map (canonical → aliases, auditable dedup)
│   ├── body_parts.yaml             # DICOM tag → body part routing (Phase 2)
│   └── prompts/
│       ├── extract_cxr_pt.txt      # Auto-generated PT CXR extraction prompt (40 findings)
│       ├── extract_msk_pt.txt      # Portuguese MSK prompt (Phase 2)
│       └── extract_spine_pt.txt    # Portuguese spine prompt (Phase 2)
├── src/cxr_mvp/
│   ├── __init__.py
│   ├── models.py                    # Core data models:
│   │                                #   LabelState, Confidence, FindingLabel, OtherFinding,
│   │                                #   ReportExtraction, ExtractionResult, ValidatedExtraction,
│   │                                #   ExamRecord, UniqueReport, GroundTruthRow,
│   │                                #   ModelPrediction, RunManifest, get_finding_status()
│   ├── config.py                    # Centralized YAML loader (@lru_cache):
│   │                                #   FindingDef, FindingsConfig (by_priority, by_category,
│   │                                #   by_type, by_acuity, hierarchy, children, pt_synonyms)
│   │                                #   load_findings_config(), load_synonym_map()
│   ├── ingest.py                    # Stage 0: CSV parse, normalize, SHA-256 dedup, filename extract
│   ├── prompt_generator.py          # Stage 0.5: Config-driven prompt generation + SHA-256 hash
│   ├── extractors/                  # Stage 1: Text extraction backends
│   │   ├── __init__.py
│   │   ├── base.py                  # ExtractionBackend ABC (extract, extract_async, supports_batch)
│   │   ├── registry.py              # Config-driven instantiation from extraction_models.yaml
│   │   └── anthropic_extractor.py   # Any claude-* model. Sync + async concurrent + retry.
│   │                                #   Parses other_findings + study_quality. dataclasses.asdict().
│   ├── validation.py                # Stage 1.5: 6 review rules + acute_classification + PT rules
│   │                                #   compute_priority(), validate_extraction()
│   ├── pt_rules.py                  # Portuguese NLP: negation/hedging/chronicity pattern matching
│   │                                #   check_negation_consistency(), check_hedging_consistency(),
│   │                                #   check_chronicity(), check_extraction()
│   ├── discovery.py                 # Stage 1.75: Tier 2 aggregation (synonym map + stem dedup)
│   │                                #   aggregate_discoveries(), generate_discovery_report()
│   ├── comparison.py                # Stage 1b: Inter-model agreement + hierarchical roll-up
│   │                                #   + calibrated arbitration + select_primary()
│   ├── reference_labels.py          # Stage 2: Join extractions→exams, balance, statistics
│   │                                #   join_extractions_to_exams(), build_balanced_set(),
│   │                                #   compute_statistics(), compare_flags()
│   ├── label_maps.py                # Named label maps (strict, broad, parenchymal_opacity)
│   │                                #   apply_label_map()
│   ├── run_manifest.py              # Run manifest generation (frozen versions for audit trail)
│   │                                #   generate_run_manifest()
│   ├── body_part_router.py          # DICOM tag + PT text → body part detection (Phase 2)
│   ├── image_utils.py               # DICOM → normalized pixel array (Phase 2)
│   ├── evaluation.py                # Confusion matrix, AUROC, AUPRC, plots (Phase 2)
│   └── backends/                    # Vision model backends
│       ├── __init__.py              # Auto-discovery registry
│       ├── base.py                  # VisionBackend ABC
│       ├── mock_backend.py          # Deterministic test backend
│       ├── medsiglip.py             # MedSigLIP zero-shot (local MPS)
│       ├── torchxrayvision.py       # TXV DenseNet-121 (local CPU)
│       └── ...                      # One file per additional model
├── scripts/
│   ├── 00_ingest.py                 # CLI → ingest.py (CSV parse + dedup)
│   ├── 00b_generate_prompt.py       # CLI → prompt_generator.py (config → prompt + hash)
│   ├── 01_extract_labels.py         # CLI → extractors (--concurrency 20, --models, --limit)
│   ├── 01a_validate_extractions.py  # CLI → validation.py (6 rules + PT checks)
│   ├── 01b_compare_extractions.py   # CLI → comparison.py (agreement + select primary)
│   ├── 01c_discovery_report.py      # CLI → discovery.py (Tier 2 aggregation)
│   ├── 02_build_ground_truth.py     # CLI → reference_labels.py (join, compare, balance)
│   ├── 03_run_models.py             # CLI → run N vision backends (Phase 2)
│   ├── 04_evaluate.py               # CLI → metrics, plots, comparison (Phase 2)
│   └── run_extraction.sh            # Stages 0-2 orchestration
├── tests/
│   ├── conftest.py                  # Shared fixtures (PT report samples, dummy DICOM)
│   ├── test_models.py               # Schema validation tests
│   ├── test_config.py               # Config loading tests
│   ├── test_ingest.py               # CSV parsing, normalization, dedup tests
│   ├── test_prompt_generator.py     # Prompt generation + hash tests
│   ├── test_ground_truth.py         # Join, comparison, balancing tests
│   ├── test_validation.py           # 6 validation rules + acute classification
│   ├── test_pt_rules.py             # Portuguese NLP rule tests
│   ├── test_discovery.py            # Tier 2 discovery aggregation tests
│   ├── test_label_maps.py           # Named label map tests
│   ├── test_comparison.py           # Inter-model agreement + arbitration tests
│   ├── test_run_manifest.py         # Run manifest tests
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── test_base.py             # ExtractionBackend contract tests
│   │   ├── test_anthropic_extractor.py  # Anthropic backend tests
│   │   └── test_registry.py         # Registry + config loading tests
│   └── backends/
│       ├── __init__.py
│       └── test_mock_backend.py     # Vision backend contract tests
├── data/
│   └── dicoms/                      # Downloaded DICOM files (gitignored)
└── output/                          # All pipeline outputs (gitignored)
    ├── exam_registry.jsonl          # Step 0: one row per exam_id (6,542)
    ├── unique_reports.jsonl         # Step 0: one row per report_hash (1,163)
    ├── ingest_errors.jsonl          # Step 0: rejected reports
    └── reference_labels/
        ├── extractions_{model}.jsonl    # Step 1: per-model extractions
        ├── extraction_errors_{model}.jsonl  # Step 1: failed extractions
        ├── run_manifest.json            # Step 1: frozen versions
        ├── validated_{model}.jsonl      # Step 1.5: post-validation
        ├── needs_review.jsonl           # Step 1.5: flagged for review
        ├── discovery_report.json        # Step 1.75: Tier 2 aggregation
        ├── agreement_report.json        # Step 1b: inter-model agreement
        ├── disagreements.jsonl          # Step 1b: per-report disagreements
        ├── per_report_agreement.json    # Step 1b: per-hash scores
        ├── selected_extractions.jsonl   # Step 1b: primary model selected
        ├── labels.jsonl                 # Step 2: one row per exam_id (labeled)
        ├── flag_comparison.json         # Step 2: Sonnet vs original flag
        ├── balanced.csv                 # Step 2: balanced evaluation set
        └── statistics.json              # Step 2: dataset composition + prevalence
```

---

## Setup

```bash
mkdir -p cxr-mvp/{config/prompts,src/cxr_mvp/{extractors,backends},scripts,data/dicoms,output/{reference_labels,predictions,evaluation/{confusion_matrices,roc_curves}},tests/{extractors,backends}}
cd cxr-mvp

python3.11 -m venv .venv
source .venv/bin/activate

cat > requirements.txt << 'EOF'
# Core
torch==2.3.1
pydicom==3.0.1
pandas==2.2.3
numpy==1.26.4
Pillow==11.1.0
pyyaml==6.0.2
pydantic==2.8.2
tqdm==4.67.1

# Evaluation
scikit-learn==1.6.1
matplotlib==3.9.2
seaborn==0.13.2

# MedSigLIP (CXR zero-shot)
transformers==4.46.2
tensorflow>=2.15.0

# TorchXRayVision (CXR baseline)
torchxrayvision==0.0.45

# Anthropic API (text extraction — sync + async)
anthropic==0.43.0

# GCP (MedGemma vision, Phase 2 non-CXR)
google-cloud-aiplatform==1.74.0
httpx==0.27.2

# OpenAI + xAI (optional vision backends)
openai==1.62.0

# Google Gemini (optional vision backend)
google-genai==1.14.0

# Retry logic
tenacity==9.0.0
EOF

pip install -r requirements.txt
pip freeze > frozen-$(date +%Y%m%d).txt
```

### API Keys Required

```bash
# In ~/.config/lifeos/.env or project .env:
ANTHROPIC_API_KEY=sk-ant-...     # Required: text extraction via Sonnet/Opus API
OPENAI_API_KEY=sk-...            # Optional: GPT vision backend
GOOGLE_API_KEY=AIza...           # Optional: Gemini vision backend
XAI_API_KEY=xai-...              # Optional: Grok vision backend (future)

# GCP (for MedGemma vision backend, Phase 2)
gcloud auth application-default login
```

---

## Core Data Model: `src/cxr_mvp/models.py`

```python
"""Core data models. Every component reads/writes these typed structures.
Label states aligned with Playbook v3 for seamless production transition."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pydantic import BaseModel, field_validator


# === Label Vocabulary (Playbook v3 compatible) ===

class LabelState(str, Enum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    UNCERTAIN = "Uncertain"
    ABSENT = "Absent"
    NOT_ASSESSABLE = "Not_Assessable"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# === CSV Ingestion Models ===

@dataclass
class ExamRecord:
    """One exam from the CSV after ingestion and deduplication."""
    exam_id: str
    customer_id: str
    dicom_filenames: list  # PA, lateral, etc. (extracted from URL path)
    report_hash: str       # SHA-256 of normalized report text (join key)
    original_label: int    # 1=normal, 2=abnormal (from CSV, unreliable)
    report_length: int


@dataclass
class UniqueReport:
    """One unique report text for extraction (keyed by report_hash)."""
    report_hash: str
    report_text: str
    exam_count: int        # how many exams share this exact text
    sample_exam_id: str    # one example exam_id for reference


# === Extraction Result (persisted output of Stage 1) ===

@dataclass
class ExtractionResult:
    """One completed extraction, keyed by report_hash (not exam_id).
    Written to extractions_{model_name}.jsonl."""
    report_hash: str
    classification: str           # "normal" | "abnormal"
    findings: dict                # {finding: {status, confidence, evidence}}
    extraction_model: str         # config name: "sonnet", "opus"
    prompt_hash: str              # SHA-256 of prompt used
    timestamp: str                # ISO 8601
    other_findings: list = field(default_factory=list)    # Tier 2 discoveries
    study_quality: str = "adequate"                       # "adequate" | "suboptimal"
    study_quality_flags: list = field(default_factory=list)  # ["bedside", "rotation", ...]
    ontology_version: str = ""                            # "2.0.0" from config
    extraction_schema: str = "v2"                         # schema version


@dataclass
class ValidatedExtraction(ExtractionResult):
    """Post-validation extraction with computed triage fields (Stage 1.5)."""
    priority_level: str = "NONE"       # CRITICAL | HIGH | MODERATE | LOW | NONE
    needs_review: bool = False
    review_reasons: list = field(default_factory=list)
    original_classification: str = ""  # set when classification is upgraded
    acute_classification: str = "normal"  # "abnormal" if acute findings present
    rule_warnings: list = field(default_factory=list)  # PT NLP warnings


# === Text Extraction Output (LLM JSON response validation) ===

_STATUS_ALIASES: dict[str, str] = {
    "present": "Positive", "absent": "Absent",
    "positive": "Positive", "negative": "Negative",
    "uncertain": "Uncertain", "normal": "Negative",
    "positivo": "Positive", "negativo": "Negative",
    "ausente": "Absent", "incerto": "Uncertain",
}


def _normalize_status_value(v: str) -> str:
    """Normalize LLM status output variations (English, Portuguese, lowercase)."""
    if isinstance(v, str):
        return _STATUS_ALIASES.get(v.lower(), v)
    return v


class FindingLabel(BaseModel):
    """One finding extracted from a Portuguese radiology report."""
    status: LabelState
    confidence: Confidence = Confidence.MEDIUM
    evidence: Optional[str] = None  # exact PT quote from report

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: str) -> str:
        return _normalize_status_value(v)


class OtherFinding(BaseModel):
    """Tier 2 discovered finding from LLM response."""
    name: str
    original_term: str
    status: LabelState
    confidence: Confidence = Confidence.MEDIUM
    evidence: Optional[str] = None
    suggested_category: str = "other"

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: str) -> str:
        return _normalize_status_value(v)


class ReportExtraction(BaseModel):
    """Pydantic validation schema for LLM JSON response. v2."""
    exam_id: Optional[str] = None
    classification: str  # "normal" | "abnormal"
    findings: dict[str, FindingLabel]
    other_findings: list[OtherFinding] = []
    study_quality: str = "adequate"
    study_quality_flags: list[str] = []
    report_language: str = "pt"
    extraction_model: str = "claude-sonnet-4-6"


# === Ground Truth Row ===

@dataclass
class GroundTruthRow:
    """One row in the reference label dataset (one per exam_id)."""
    exam_id: str
    customer_id: str
    classification: str  # "normal" | "abnormal"
    findings: dict  # {finding_name: {status, confidence, evidence}}

    # Provenance
    dicom_filenames: list = field(default_factory=list)
    report_hash: Optional[str] = None
    original_label: Optional[int] = None  # 1=normal, 2=abnormal (CSV, unreliable)
    extraction_model: Optional[str] = None
    prompt_hash: Optional[str] = None

    # Patient ID — NOT in CSV. Populated from DICOM metadata in Stage 3.
    patient_id: Optional[str] = None

    # Multi-model agreement (populated in Stage 2 from agreement_report.json)
    inter_model_agreement: float = 1.0
    has_disagreement: bool = False
    disagreement_findings: list = field(default_factory=list)
    primary_model: str = ""

    # DICOM metadata — populated in Stage 3
    body_part: str = "CXR"
    view_position: Optional[str] = None
    portable_flag: bool = False
    quality_status: Optional[str] = None
    quality_flags: list = field(default_factory=list)


# === Vision Model Prediction ===

@dataclass
class ModelPrediction:
    """One prediction from a vision backend for one study."""
    exam_id: str
    model_name: str
    model_version: str

    # Binary classification
    binary_label: str  # "normal" | "abnormal"
    binary_score: Optional[float] = None  # 0-1

    # Per-finding predictions
    findings: dict = field(default_factory=dict)
    # {finding_name: {"label": str, "score": float}}

    # Provenance
    inference_timestamp: Optional[str] = None
    config_hash: Optional[str] = None


# === Run Manifest (provenance) ===

@dataclass
class RunManifest:
    """Reproducibility metadata for every pipeline stage."""
    stage: str
    timestamp: str
    code_commit: Optional[str] = None
    input_hash: Optional[str] = None
    config_hash: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    n_processed: int = 0
    n_errors: int = 0
    pipeline_version: str = "v7"
    prompt_hash: Optional[str] = None
    extraction_mode: Optional[str] = None  # "sync" | "batch"
    n_exams: int = 0
    n_unique_reports: int = 0
    n_extracted: int = 0
    n_balanced: int = 0


def get_finding_status(data) -> str:
    """Extract status from a finding data dict. Returns 'Absent' if missing."""
    if isinstance(data, dict):
        return data.get("status", "Absent")
    return "Absent"
```

---

## Config Module: `src/cxr_mvp/config.py`

Centralized YAML loading with `@lru_cache`. All consumers import from here — no raw `yaml.safe_load` elsewhere.

```python
"""Centralized config loader for findings_cxr.yaml v2.
Single point of YAML parsing. All consumers import from here."""
from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class FindingDef:
    """One finding definition from config."""
    en: str
    pt: list[str]
    category: str
    priority: str       # CRITICAL | HIGH | MODERATE | LOW
    tier: int = 1
    type: str = "descriptive"          # descriptive | etiologic | device_presence | device_position
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

    def findings_by_type(self, finding_type: str) -> list[str]:
        """Finding names filtered by type."""
        return [name for name, f in self.findings.items() if f.type == finding_type]

    def findings_by_acuity(self, acuity: str) -> list[str]:
        """Finding names filtered by acuity."""
        return [name for name, f in self.findings.items() if f.acuity == acuity]

    def pt_synonyms(self, finding_name: str) -> list[str]:
        """Portuguese synonyms for a finding."""
        return self.findings[finding_name].pt

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
            en=data["en"], pt=data["pt"],
            category=data["category"], priority=data["priority"],
            tier=data.get("tier", 1), type=data.get("type", "descriptive"),
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
```

---

## Step 0: Ingest & Deduplicate (`scripts/00_ingest.py`)

Parses the raw CSV, normalizes report text, deduplicates by SHA-256 hash,
extracts DICOM filenames from URLs, and produces the two working datasets
for the extraction pipeline. No API calls. No DICOM pixel processing.

```python
#!/usr/bin/env python3
"""Step 0: Ingest ListaLLM.csv → exam_registry.jsonl + unique_reports.jsonl.
Handles: no header, semicolons, UTF-8 BOM, report dedup, DICOM filename extraction.
DICOM validation is deferred to Stage 3 (vision model phase)."""

import csv, json, hashlib, re, unicodedata
from pathlib import Path
from urllib.parse import urlparse
from collections import defaultdict


def normalize_report(text: str) -> str:
    """Deterministic text normalization for dedup hashing."""
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)
    text = unicodedata.normalize('NFC', text)
    return text


def report_hash(text: str) -> str:
    """SHA-256 of normalized report text. The dedup + join key."""
    return hashlib.sha256(normalize_report(text).encode('utf-8')).hexdigest()


def extract_dicom_filename(url: str) -> str:
    """Extract DICOM filename from download URL path."""
    parsed = urlparse(url)
    return parsed.path.split('/')[-1]


def main(input_path: str = "ListaLLM.csv"):
    # Parse CSV: no header, semicolons, UTF-8 BOM
    with open(input_path, encoding='utf-8-sig') as f:
        reader = csv.reader(f, delimiter=';', quotechar='"')
        rows = list(reader)

    # Group by exam_id, build registry + unique reports, write JSONL
    # (full implementation in src/cxr_mvp/ingest.py)
    ...
```

---

## Step 0.5: Generate Extraction Prompt (`scripts/00b_generate_prompt.py`)

Config-driven prompt generation. Reads `findings_cxr.yaml` via `config.py`,
generates the Portuguese extraction prompt with all 40 Tier 1 findings,
PT synonym hints, device tracking, study quality assessment, and Tier 2
discovery instruction.

```python
#!/usr/bin/env python3
"""Step 0.5: Generate extraction prompt from config/findings_cxr.yaml.
Output: config/prompts/extract_cxr_pt.txt + SHA-256 hash for staleness detection."""

from cxr_mvp.prompt_generator import generate_prompt, prompt_hash

def main():
    prompt = generate_prompt()
    phash = prompt_hash()

    Path("config/prompts").mkdir(parents=True, exist_ok=True)
    Path("config/prompts/extract_cxr_pt.txt").write_text(prompt)

    print(f"Prompt generated: {len(prompt):,} chars")
    print(f"Prompt hash: {phash}")
    print(f"→ config/prompts/extract_cxr_pt.txt")
```

### Auto-Generated Portuguese Extraction Prompt

The prompt generator produces a comprehensive prompt that includes:

1. **System instruction** — role as extraction engine
2. **Section restriction** — extract from achados/impressão only, ignore indicação/técnica
3. **Classification** — normal vs abnormal rules
4. **40 findings** — all names + status rules (5-state)
5. **PT synonym hints** — grouped by category (PULMONARY, DEVICE, etc.)
6. **Device tracking** — device_presence vs device_malposition rules
7. **Study quality** — adequate/suboptimal + 7 quality flags
8. **Tier 2 discovery** — `other_findings` for findings not in vocabulary
9. **JSON schema** — exact response format with all 40 finding placeholders

---

## Step 1: Extract Labels (`scripts/01_extract_labels.py`)

Multi-model async concurrent extraction engine. Reads `unique_reports.jsonl`,
runs N models from `extraction_models.yaml`, writes per-model JSONL outputs.

```python
#!/usr/bin/env python3
"""Step 1: Extract structured labels from Portuguese radiology reports.
Multi-model, async concurrent, with retry and checkpoint/resume.

Usage:
  python 01_extract_labels.py run                        # all enabled models
  python 01_extract_labels.py run --models sonnet        # specific model
  python 01_extract_labels.py run --limit 10             # pilot run
  python 01_extract_labels.py run --concurrency 20       # parallel API calls

Cost: ~$3-6 for 1,163 unique reports (Sonnet + Opus, async concurrent).
"""

import asyncio
from pathlib import Path
from cxr_mvp.extractors.registry import load_extractors
from cxr_mvp.prompt_generator import generate_prompt
from cxr_mvp.run_manifest import generate_run_manifest

def main():
    # Load models from config/extraction_models.yaml
    extractors = load_extractors()
    prompt = generate_prompt()

    # Load unique reports from Step 0
    reports = load_unique_reports("output/unique_reports.jsonl")

    # Emit run manifest (frozen versions)
    manifest = generate_run_manifest(models=[e.name() for e in extractors])

    # Run each model (async concurrent, 20 parallel by default)
    for extractor in extractors:
        asyncio.run(extractor.extract_async(
            reports=reports, prompt=prompt,
            output_dir="output/reference_labels",
            concurrency=20,
        ))

    # Write manifest
    Path("output/reference_labels/run_manifest.json").write_text(
        json.dumps(manifest, indent=2)
    )
```

### Extraction Models Config: `config/extraction_models.yaml`

```yaml
prompt_template: config/prompts/extract_cxr_pt.txt
temperature: 0
max_tokens: 4096

models:
  - name: sonnet
    provider: anthropic
    model_id: claude-sonnet-4-6
    mode: batch
    enabled: true

  - name: opus
    provider: anthropic
    model_id: claude-opus-4-6
    mode: batch
    enabled: true

  # Future:
  # - name: gpt4o
  #   provider: openai
  #   model_id: gpt-4o
  #   mode: sync
  #   enabled: false
```

### Extraction Backend: `src/cxr_mvp/extractors/anthropic_extractor.py`

One class handles all `claude-*` models. Key features:
- Async concurrent extraction with `asyncio.Semaphore` (configurable concurrency)
- Exponential backoff retry (3 attempts: 1s, 2s delays)
- Checkpoint/resume via `report_hash` tracking
- Pydantic validation of LLM JSON output
- `other_findings` + `study_quality` parsing
- `dataclasses.asdict()` for serialization
- Provenance: `ontology_version` injected from config

```python
class AnthropicExtractor(ExtractionBackend):
    """Extraction backend for Anthropic models (Sonnet, Opus, etc.)."""

    async def extract_async(self, reports, prompt, output_dir, concurrency=20):
        """Async concurrent extraction with semaphore-based rate limiting.

        concurrency=20: Anthropic rate limit is 1000 RPM;
        20 concurrent at ~4s each = ~300 RPM (safe margin).
        """
        client = AsyncAnthropic()
        sem = asyncio.Semaphore(concurrency)

        async def extract_one(report):
            async with sem:
                for attempt in range(3):  # retry with backoff
                    try:
                        response = await client.messages.create(
                            model=self._model_id,
                            max_tokens=self._max_tokens,
                            temperature=self._temperature,
                            messages=[{"role": "user", "content": prompt}],
                        )
                        # Parse, validate, write checkpoint
                        ...
                        break  # success
                    except Exception:
                        if attempt < 2:
                            await asyncio.sleep(2 ** attempt)

        await asyncio.gather(*[extract_one(r) for r in remaining])
```

---

## Step 1.5: Post-Extraction Validation (`scripts/01a_validate_extractions.py`)

Applies 6 review rules to raw extractions. Never downgrades — only upgrades when evidence demands it.

```python
"""Post-extraction validation — 6 review rules + acute_classification + PT rules.
Stage 1.5: reads ExtractionResult, produces ValidatedExtraction.
Core principle: never downgrade. Only upgrade when evidence demands it."""

def validate_extraction(result: ExtractionResult, config_path: str) -> ValidatedExtraction:
    """Apply validation rules to raw extraction."""
    config = load_findings_config(config_path)
    priority = compute_priority(result.findings, result.other_findings)

    review_reasons = []

    # Rule 1: Ghost-abnormal — classification=abnormal, no supporting findings
    if classification == "abnormal" and not has_positive_or_uncertain:
        review_reasons.append("no_supporting_findings")

    # Rule 2: Critical override — normal + CRITICAL finding → upgrade
    if classification == "normal" and priority == "CRITICAL":
        classification = "abnormal"
        review_reasons.append("critical_finding_override")

    # Rule 3: High uncertainty — 3+ Uncertain findings
    if count_uncertain >= 3:
        review_reasons.append("high_uncertainty")

    # Rule 4: Critical on suboptimal study
    if study_quality == "suboptimal" and priority == "CRITICAL":
        review_reasons.append("critical_on_suboptimal")

    # Rule 5: Device without position assessment
    if has_device and malposition == "Absent":
        review_reasons.append("device_without_position")

    # Rule 6: Hierarchy inconsistency (child Positive, parent Absent)
    if child_positive and parent_absent:
        review_reasons.append("hierarchy_inconsistency")

    # PT rule checks (negation/hedging consistency)
    rule_warnings = pt_rules.check_extraction(result.findings)

    # Acute classification (acute/context_dependent Positive → "abnormal")
    acute_classification = "abnormal" if any_acute_positive else "normal"

    return ValidatedExtraction(
        ...,
        priority_level=priority,
        needs_review=len(review_reasons) > 0,
        review_reasons=review_reasons,
        acute_classification=acute_classification,
        rule_warnings=rule_warnings,
    )
```

---

## Portuguese NLP Rules: `src/cxr_mvp/pt_rules.py`

Deterministic phrase matching for negation, hedging, and chronicity. Catches high-impact LLM extraction errors without replacing the LLM.

```python
"""Portuguese medical text rule checks for post-extraction verification."""

NEGATION_PATTERNS = [
    r"sem sinais de", r"sem evidência de", r"ausência de",
    r"não se observa", r"não há", r"não se identifica",
    r"dentro dos limites", r"dentro da normalidade",
    r"sem alterações", r"aspecto normal", r"preservado[s]?",
    r"contornos preservados", r"de aspecto normal",
]

HEDGING_PATTERNS = [
    r"não se pode excluir", r"não se pode afastar",
    r"possível", r"provável", r"sugestivo de",
    r"a esclarecer", r"a critério clínico", r"a correlacionar",
    r"não se descarta",
]

CHRONICITY_PATTERNS = [
    r"sequela", r"residual", r"crônic[oa]", r"antig[oa]",
    r"prévi[oa]", r"degenerativ[oa]", r"consolidad[oa]",
]


def check_negation_consistency(finding_name, status, evidence):
    """Return warning if Positive status has negation evidence."""
    if status == "Positive" and evidence and negation_re.search(evidence):
        return f"Negation conflict: '{finding_name}' is Positive but evidence contains negation"


def check_hedging_consistency(finding_name, status, evidence):
    """Return warning if Positive status has hedging evidence (should be Uncertain)."""
    if status == "Positive" and evidence and hedging_re.search(evidence):
        return f"Hedging conflict: '{finding_name}' is Positive but evidence suggests Uncertain"


def check_extraction(findings: dict) -> list[dict]:
    """Run all rule checks on an extraction. Returns list of warnings."""
    warnings = []
    for name, data in findings.items():
        if not isinstance(data, dict):
            continue
        status = get_finding_status(data)
        evidence = data.get("evidence")
        # Check negation consistency, hedging consistency
        ...
    return warnings
```

---

## Tier 2 Discovery: `src/cxr_mvp/discovery.py`

Aggregates `other_findings` across extraction files, deduplicates via synonym map + stem fallback.

```python
"""Tier 2 discovery — aggregate other_findings across extractions."""

def _canonical_key(name: str) -> str:
    """Word-stem canonical key for dedup fallback.
    Takes first 6 chars of each word, sorts alphabetically.
    convex_diaphragm + diaphragm_convexity → same key."""
    parts = name.lower().replace("-", "_").split("_")
    stems = sorted(p[:6] for p in parts if p)
    return "_".join(stems)


def aggregate_discoveries(output_dir, synonym_path):
    """Aggregate all other_findings across extraction files.
    Pipeline:
    1. Raw count per name
    2. Synonym map remap (deterministic, from config/tier2_synonyms.yaml)
    3. Stem dedup fallback (for unknown synonym pairs)
    4. Most frequent name wins as canonical
    """
    ...


def generate_discovery_report(output_dir, total_reports, threshold=0.02, min_count=10):
    """Generate discovery report with promotion candidates.
    Promotion criteria: prevalence >= threshold AND count >= min_count."""
    ...
```

### Tier 2 Synonym Map: `config/tier2_synonyms.yaml`

```yaml
synonyms:
  diaphragm_convexity:
    - convex_diaphragm
    - dome_diaphragm
    - diaphragm_dome
  hilar_prominence:
    - hilar_enlargement
    - enlarged_hilum
    - prominent_hilum
    - hilar_congestion
  bronchial_wall_thickening:
    - peribronchial_thickening
    - bronchial_thickening
  pericardial_effusion:
    - pericardial_fluid
  hilar_adenopathy:
    - hilar_lymphadenopathy
    - mediastinal_adenopathy
    - lymphadenopathy
```

---

## Inter-Model Comparison: `src/cxr_mvp/comparison.py`

Compares N extraction outputs with hierarchical agreement roll-up and calibrated arbitration.

```python
"""Inter-model comparison and agreement scoring."""


def arbitrate_finding(status_a, status_b, finding_type=None):
    """Resolve disagreement between two model statuses.
    Returns (resolved_status, needs_review).

    Rules:
    - Agreement → accept, no review
    - Positive vs Uncertain on etiologic → Uncertain (conservative)
    - Positive vs Uncertain on descriptive → review needed
    - Absent vs Positive → major disagreement, keep Positive, flag review
    - Negative vs Absent → minor, accept Negative (more specific)
    - Not_Assessable vs anything → Not_Assessable (conservative)
    """
    ...


def _apply_hierarchy_rollup(findings, hierarchy):
    """Roll up child findings to parent level.
    consolidation=Positive + lung_opacity=Absent → lung_opacity=Positive
    (child Positive implies parent)."""
    ...


def compare_extractions(output_dir):
    """Compare N extraction outputs with hierarchy roll-up.
    Writes: agreement_report.json, disagreements.jsonl, per_report_agreement.json"""
    ...


def select_primary(output_dir, primary_model=None):
    """Copy primary model's extractions to selected_extractions.jsonl."""
    ...
```

---

## Step 2: Build Reference Labels (`scripts/02_build_ground_truth.py`)

Joins extractions (keyed by `report_hash`) back to exams, compares with original
flag, builds balanced evaluation set, and computes statistics.

```python
#!/usr/bin/env python3
"""Step 2: Join extractions → exams, compare with original flag, balance, compute stats.
Input: exam_registry.jsonl + selected_extractions.jsonl + agreement_report.json.
Output: labels.jsonl, flag_comparison.json, balanced.csv, statistics.json."""

from cxr_mvp.reference_labels import (
    join_extractions_to_exams, build_balanced_set,
    compute_statistics, compare_flags,
)

def main(seed=42, ratio=1.0):
    # Join extractions to exams
    labels = join_extractions_to_exams("output")

    # Compare Sonnet vs original CSV flag
    comparison = compare_flags(labels)

    # Build balanced set (all abnormals + equal random normals)
    balanced = build_balanced_set(labels, seed=seed, ratio=ratio)

    # Compute statistics (finding prevalence, quality distribution, etc.)
    stats = compute_statistics(labels)

    # Write outputs to output/reference_labels/
    ...
```

---

## Run Manifest: `src/cxr_mvp/run_manifest.py`

Captures frozen versions of all pipeline components at run time for reproducibility.

```python
def generate_run_manifest(models, config_path, extraction_config_path):
    """Generate a run manifest with frozen versions."""
    return {
        "run_id": str(uuid.uuid4())[:8],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "models": models,
        "ontology_version": config.version,     # "2.0.0"
        "prompt_hash": phash,                    # SHA-256[:16]
        "yaml_hash": yaml_hash,                  # SHA-256[:16] of findings_cxr.yaml
        "code_commit": code_commit,              # git rev-parse --short HEAD
        "extraction_schema": "v2",
        "pipeline_version": "v3",
    }
```

---

## Step 3: Run Vision Models (`scripts/03_run_models.py`)

```python
#!/usr/bin/env python3
"""Step 3: Run N vision models against the reference label images.
Model-agnostic: each backend implements the same interface.
Adding a new model = one file in src/backends/.

Usage:
  python 03_run_models.py                    # run all registered backends
  python 03_run_models.py medsiglip          # run specific backend
  python 03_run_models.py medsiglip txv      # run multiple specific backends
"""

from src.backends import get_backend, list_backends
from src.image_utils import load_dicom_pixels


def run_backend(backend_name, reference_labels_path, output_dir):
    """Run one vision backend against all reference label images."""
    gt = pd.read_csv(reference_labels_path)
    backend = get_backend(backend_name)

    for exam in gt.iterrows():
        pixel_array, meta = load_dicom_pixels(dicom_path)
        prediction = backend.predict(pixel_array, meta)
        # Write to output_dir/{backend_name}.jsonl (checkpointed)
```

---

## Vision Backend Interface: `src/cxr_mvp/backends/base.py`

```python
"""Abstract interface for all vision classification backends."""

from abc import ABC, abstractmethod
import numpy as np


class VisionBackend(ABC):
    """All vision models implement this interface."""

    @abstractmethod
    def name(self) -> str:
        """Unique backend identifier."""

    @abstractmethod
    def predict(self, pixel_array: np.ndarray, dicom_meta: dict) -> dict:
        """Classify one image.
        Returns:
            {
                "binary_label": "normal" | "abnormal",
                "binary_score": float (0-1, higher = more abnormal),
                "findings": {
                    finding_name: {"label": "Positive"|"Negative"|"Uncertain", "score": float},
                },
                "method": str,
            }
        """
```

---

## Backend: MedSigLIP (`src/backends/medsiglip.py`)

```python
"""MedSigLIP zero-shot classification backend.
Local MPS, $0, 84.4% mAUC on CheXpert.
SigLIP uses sigmoid (not softmax) — native multi-label."""

import torch
import numpy as np
from PIL import Image
from transformers import AutoModel, AutoProcessor
from src.vision_backend import VisionBackend

# Text prompts for zero-shot — NEVER use negated prompts
FINDING_PROMPTS = {
    "atelectasis": "atelectasis present",
    "cardiomegaly": "cardiomegaly present",
    "consolidation": "consolidation present",
    "edema": "pulmonary edema present",
    "effusion": "pleural effusion present",
    "emphysema": "emphysema present",
    "fibrosis": "pulmonary fibrosis present",
    "fracture": "fracture present",
    "hernia": "hiatal hernia present",
    "infiltration": "infiltrate present",
    "lung_lesion": "lung lesion present",
    "lung_opacity": "lung opacity present",
    "mass": "mass present",
    "nodule": "nodule present",
    "pleural_thickening": "pleural thickening present",
    "pneumonia": "pneumonia present",
    "pneumothorax": "pneumothorax present",
    "enlarged_cardiomediastinum": "enlarged cardiomediastinum present",
}

THRESHOLD = 0.5


class MedSigLIPBackend(VisionBackend):
    def __init__(self):
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.model = AutoModel.from_pretrained("google/medsiglip-448").to(self.device)
        self.processor = AutoProcessor.from_pretrained("google/medsiglip-448")
        self.model.eval()

    def name(self):
        return "medsiglip"

    def predict(self, pixel_array, dicom_meta):
        pil_image = self._preprocess(pixel_array)

        # SigLIP uses sigmoid natively → per-finding independent probabilities
        inputs = self.processor(
            text=list(FINDING_PROMPTS.values()),
            images=[pil_image],
            padding="max_length",
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)

        probs = torch.sigmoid(outputs.logits_per_image[0]).cpu().numpy()

        findings = {}
        for i, (finding, _) in enumerate(FINDING_PROMPTS.items()):
            score = float(probs[i])
            findings[finding] = {
                "label": "Positive" if score >= THRESHOLD else "Negative",
                "score": round(score, 4),
            }

        binary_score = max(f["score"] for f in findings.values())
        return {
            "binary_label": "abnormal" if any(f["label"] == "Positive" for f in findings.values()) else "normal",
            "binary_score": round(binary_score, 4),
            "findings": findings,
            "method": "medsiglip_zero_shot",
        }
```

---

## Backend: TorchXRayVision (`src/backends/torchxrayvision.py`)

```python
"""TorchXRayVision DenseNet-121 baseline backend.
Local CPU, $0, 81.1% mAUC. 18 fixed CXR classes."""

import torch
import numpy as np
import torchxrayvision as xrv
from src.vision_backend import VisionBackend


class TXVBackend(VisionBackend):
    def __init__(self):
        self.model = xrv.models.DenseNet(weights="densenet121-res224-all")
        self.model.eval()
        self.device = "cpu"

    def name(self):
        return "torchxrayvision"

    def predict(self, pixel_array, dicom_meta):
        # TXV preprocessing → 224x224 normalized
        # Run inference → 18 sigmoid scores
        # Map TXV names to our canonical names
        ...
```

---

## Backend Registry: `src/backends/__init__.py`

```python
"""Auto-discovery registry for vision backends.
Adding a new model = one file in this directory implementing VisionBackend."""

_REGISTRY = {}

def register(name, backend_class): _REGISTRY[name] = backend_class
def get_backend(name): return _REGISTRY[name]()
def list_backends(): return list(_REGISTRY.keys())

# Auto-register
try:
    from src.backends.medsiglip import MedSigLIPBackend
    register("medsiglip", MedSigLIPBackend)
except ImportError:
    pass

try:
    from src.backends.torchxrayvision import TXVBackend
    register("torchxrayvision", TXVBackend)
except ImportError:
    pass
```

---

## Step 4: Evaluate (`scripts/04_evaluate.py`)

```python
#!/usr/bin/env python3
"""Step 4: Evaluate all vision models against reference labels.
Produces confusion matrices, AUROC, per-finding metrics, comparison tables.
Output feeds directly into Playbook v4 threshold calibration."""

def evaluate_binary(gt, preds, model_name):
    """Track A: Binary normal/abnormal evaluation.
    Returns: sensitivity, specificity, PPV, NPV, F1, AUROC + confusion matrix plot."""
    ...

def evaluate_findings(gt, preds, model_name):
    """Track B: Per-finding evaluation (40 findings).
    Returns: per-finding AUROC, AUPRC, sensitivity, specificity."""
    ...

def build_comparison_table(binary_results, finding_results):
    """Side-by-side comparison of all models → comparison_table.csv."""
    ...

def compute_recommended_thresholds(gt, preds, model_name):
    """Per-finding optimal thresholds via Youden's J → recommended_thresholds.json."""
    ...
```

---

## Run All (Stages 0-2: Text Extraction Pipeline)

```bash
#!/bin/bash
# scripts/run_extraction.sh — Stages 0-2 only (text extraction + reference labels)
set -e
mkdir -p output/reference_labels

echo "══════════════════════════════════════════════════════════════"
echo "  X-Ray Reference Label Engine — MVP v7 (Text Extraction)"
echo "══════════════════════════════════════════════════════════════"

echo ""
echo "Step 0: Ingesting & deduplicating CSV..."
PYTHONPATH=src python3 scripts/00_ingest.py --input ListaLLM.csv

echo ""
echo "Step 0.5: Generating extraction prompt from config..."
PYTHONPATH=src python3 scripts/00b_generate_prompt.py

echo ""
echo "Step 1: Extracting labels from Portuguese reports (async concurrent)..."
PYTHONPATH=src python3 scripts/01_extract_labels.py run --concurrency 20

echo ""
echo "Step 1.5: Validating extractions (6 rules + PT checks)..."
PYTHONPATH=src python3 scripts/01a_validate_extractions.py

echo ""
echo "Step 1b: Comparing inter-model agreement..."
PYTHONPATH=src python3 scripts/01b_compare_extractions.py

echo ""
echo "Step 1.75: Tier 2 discovery aggregation..."
PYTHONPATH=src python3 scripts/01c_discovery_report.py --total-reports 1126

echo ""
echo "Step 2: Building reference labels + balanced set..."
PYTHONPATH=src python3 scripts/02_build_ground_truth.py

echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  Done. Check output/reference_labels/ for results."
echo "══════════════════════════════════════════════════════════════"
```

---

## E2E Validated Results (100 Reports, Sonnet + Opus)

Pilot validation run on 100 unique reports (covering ~500 exams), both models:

### Classification Agreement

| Metric | Value |
|---|---|
| Classification agreement (Sonnet vs Opus) | **100%** (both agree normal/abnormal) |
| Mean finding agreement | **91.0%** across 40 findings |
| Total disagreements found | **362** individual finding-level disagreements |
| Arbitration auto-resolved | **74%** (268/362) resolved without human review |
| Remaining for review | **26%** (94/362) flagged for human adjudication |

### Review Rate (Validation Rules)

| Model | Review Rate | CRITICAL Triage | Notes |
|---|---|---|---|
| Sonnet | 26% | 40 CRITICAL extractions | More sensitive — flags more findings |
| Opus | 15% | 23 CRITICAL extractions | More conservative — fewer flags |

Sonnet's higher sensitivity is desirable for a screening pipeline (miss fewer findings).

### Tier 2 Discovery Results

| Metric | Value |
|---|---|
| Unique Tier 2 findings discovered | 13 |
| Top promotion candidate | `bronchial_wall_thickening` at 6% prevalence |
| Synonym dedup merges | 5 pairs merged via synonym map |

### Portuguese NLP Rules

| Metric | Value |
|---|---|
| Total PT rule warnings | 1 in 100 reports |
| Warning type | Hedging conflict (Positive status with hedging evidence) |

### Pneumonia Observation

pneumonia was 0 Positive and 20 Uncertain across 100 reports. This is correct — radiologists hedge on pneumonia because it's an etiologic diagnosis (type=etiologic), not a descriptive finding. They say "consolidação sugestiva de pneumonia" (Uncertain) rather than definitively "pneumonia" (Positive). The `label_maps.py` `broad` map correctly captures these as True.

---

## Cost Model

Thanks to report deduplication (10K rows → 1,163 unique reports), extraction costs are dramatically reduced. With max_tokens=4096 for 40 findings.

| Step | What | Method | Time | Cost |
|------|------|--------|------|------|
| 0 | Ingest & dedup CSV (10K → 6,542 exams → 1,163 unique reports) | Local CPU | instant | $0 |
| 0.5 | Generate extraction prompt from config | Local CPU | instant | $0 |
| 1 pilot | Pilot extraction (~50 reports × 2 models) | Sonnet + Opus async | ~2 min | ~$0.05 |
| 1 full | Full extraction: Sonnet (1,163 reports) | Sonnet async (20 concurrent) | ~4 min | ~$1.50 |
| 1 full | Full extraction: Opus (1,163 reports) | Opus async (5 concurrent) | ~15 min | ~$3.00 |
| 1.5 | Validate extractions (6 rules + PT checks) | Local CPU | instant | $0 |
| 1.75 | Tier 2 discovery aggregation | Local CPU | instant | $0 |
| 1b | Compare extractions + agreement report | Local CPU | instant | $0 |
| 2 | Build reference labels + balance + stats | Local CPU | instant | $0 |
| 3a | MedSigLIP (balanced set) | Local MPS | ~8 min | $0 |
| 3b | TXV (balanced set) | Local CPU | ~2 min | $0 |
| 3c | MedGemma 4B (optional) | GCP | ~5 min | ~$1 |
| 3d | GPT vision (optional) | OpenAI API | ~15 min | ~$5 |
| 3e | Gemini vision (optional) | Google API | ~10 min | ~$3 |
| 4 | Evaluate + plots | Local CPU | 10 sec | $0 |
| **Total (Stages 0-2 only: multi-model text extraction)** | | | **~25 min** | **~$4.55** |
| **Total (all stages, minimum 2 local models)** | | | **~35 min** | **~$4.55** |
| **Total (all stages, all 5 vision models)** | | | **~1.5 hrs** | **~$13.55** |

---

## Known Limitations

1. **Reference labels are NLP-derived, not radiologist-adjudicated.** Claude Sonnet/Opus extract labels from reports, which themselves may contain errors. The Fisher (2026) NLP-to-Expert gap (0.07-0.19 AUC) applies. For production, adjudicate a 200-case subset with a radiologist. These are **silver standard** reference labels, not gold standard ground truth.

2. **Portuguese prompt engineering needs pilot validation.** The extraction prompt must be tested on real Brazilian reports before full run. Report style varies by institution (96 customers in dataset) and dictation system. Use `01_extract_labels.py run --models sonnet --limit 50` for rapid pilot iteration.

3. **No patient_id in CSV.** Patient-level splitting to prevent data leakage is not possible until DICOM metadata is processed. The balanced set in Stage 2 is split by exam_id with customer_id stratification. Re-balancing with PatientID from DICOMs is required before vision model evaluation.

4. **Heavy report text duplication.** Only 1,163 unique texts across 6,542 exams — radiologists use templates. Dedup saves cost but means many exams share identical labels. This is correct (same text → same findings) but reduces effective diversity.

5. **Original label (1/2) is unreliable.** 28 identical reports have conflicting labels. The label is a radiologist click-flag often ignored. LLM extraction is the reference label; original label is retained only for comparison metrics.

6. **432 DICOM filenames contain PHI.** Patient names embedded in filenames (e.g., `ADALBERTO DOS SANTOS - RX TORAX.dcm`). Not an issue for the text extraction phase but must be handled when processing DICOMs.

7. **MedSigLIP is slower than TXV on MPS.** ~500ms vs <100ms per image. Acceptable for evaluation, but matters at 500K scale.

8. **HAI-DEF license on MedSigLIP.** Research is fine. If going to production, need MI2 (MIT) with adapter or a commercial model.

9. **Balanced set may not represent true prevalence.** The 50/50 split is for evaluation fairness, but real-world prevalence changes PPV/NPV dramatically. Report both balanced AND prevalence-adjusted metrics.

10. **Rare findings may have unreliable metrics.** Sub-classification AUROC depends on finding prevalence. Findings with <20 positives in the balanced set will have wide confidence intervals.

11. **Multi-model extraction is a validation step, not a permanent workflow.** Running Sonnet + Opus on every report is to validate that Sonnet alone is sufficient. Once agreement >95% is confirmed, future runs can use Sonnet only. The `ExtractionBackend` pattern supports both modes via `extraction_models.yaml`.

12. **Opus rate limit is 30K input TPM.** Use `--concurrency 5` for Opus (vs 20 for Sonnet). Higher concurrency hits rate limits and triggers retries.

13. **Pneumonia is 100% Uncertain in our data.** Radiologists hedge on etiologic diagnoses. Use `label_maps.py` with the `broad` map to capture these as positive. The `strict` map will show 0% pneumonia prevalence, which is misleading.

14. **Triage priority gap between models.** Sonnet flags 40 CRITICAL vs Opus 23 CRITICAL on 100 reports. This is a sensitivity vs specificity tradeoff — Sonnet is more sensitive, which is desirable for screening.

15. **Hierarchy is currently limited.** Only `lung_opacity → consolidation, infiltration`. Future versions may add more parent-child relationships as the ontology expands.

---

## Upgrade Path: MVP v7 → Playbook v4

```
MVP v7 (batch, research)               → Playbook v4 (real-time, production)
──────────────────────────────────────────────────────────────────────────────
Batch CSV input                         → Orthanc event-driven DICOM
Sonnet/Opus API for text                → MedGemma 27B or local LLM for text
MedSigLIP/TXV for CXR vision           → Winner from bakeoff + calibrated thresholds
Model bakeoff results                   → config/thresholds.yaml (per-finding)
recommended_thresholds.json             → Playbook adjudication rules
Portuguese prompt templates             → Playbook config/prompts.yaml (PT)
JSONL/CSV output                        → DICOM SR + SC dashboard + OHIF
No quality gate routing                 → Quality → triage → escalation flow
No de-identification                    → De-ID before cloud calls
No audit trail                          → SQLite audit (every inference logged)
Research disclaimer                     → Shadow mode → pilot → production
6 validation rules                      → Production QA pipeline (same rules)
Reference labels (silver standard)      → Gold standard after adjudication
```

---

## Quick Start

### Stages 0-2: Text Extraction Pipeline (this is where we start)

```
 1. pip install pydantic pyyaml anthropic                     (1 min)
 2. Set ANTHROPIC_API_KEY in environment                      (1 min)
 3. Ensure ListaLLM.csv is in project root                    (already there)
 4. source .venv/bin/activate
 5. PYTHONPATH=src python3 scripts/00_ingest.py               (instant)
 6. PYTHONPATH=src python3 scripts/00b_generate_prompt.py     (instant, generates prompt)
 7. PYTHONPATH=src python3 scripts/01_extract_labels.py run --models sonnet --limit 10 --concurrency 10
                                                              (pilot, ~30 sec, ~$0.01)
 8. PYTHONPATH=src python3 scripts/01a_validate_extractions.py  (validate pilot)
 9. Review output/reference_labels/validated_sonnet.jsonl      (check quality)
10. PYTHONPATH=src python3 scripts/01_extract_labels.py run --concurrency 20
                                                              (full run, both models, resumes)
11. PYTHONPATH=src python3 scripts/01a_validate_extractions.py  (validate all)
12. PYTHONPATH=src python3 scripts/01b_compare_extractions.py   (inter-model agreement)
13. PYTHONPATH=src python3 scripts/01c_discovery_report.py --total-reports 1126
                                                              (Tier 2 discovery)
14. PYTHONPATH=src python3 scripts/02_build_ground_truth.py   (instant)
15. Open output/reference_labels/agreement_report.json        (Sonnet vs Opus agreement)
16. Open output/reference_labels/discovery_report.json        (Tier 2 findings)
17. Open output/reference_labels/flag_comparison.json         (Sonnet vs original label)
18. Open output/reference_labels/statistics.json              (finding prevalence)
19. Open output/reference_labels/balanced.csv                 (THE EVALUATION ASSET)
```

**Time to first result: ~25 minutes (including pilot iteration + multi-model comparison).**
**Cost: ~$4.55 total (Sonnet + Opus on 1,163 unique reports, max_tokens=4096).**

### Stages 3-4: Vision Model Bakeoff (Phase 2)

```
20. Place DICOMs in data/dicoms/                             (your data)
21. python scripts/03_run_models.py                          (10-30 min)
22. python scripts/04_evaluate.py                            (instant)
23. Open output/evaluation/comparison_table.csv              (THE ANSWER)
24. Open output/evaluation/recommended_thresholds.json       (for Playbook v4)
```

### Run Tests

```bash
source .venv/bin/activate
PYTHONPATH=src python3 -m pytest tests/ -v --tb=short    # 228 tests
```

---

## AI Council Reviews

### Round 1 (GPT 5.4, Gemini 3.1 Pro, Grok 4.20, Claude Opus 4.6)

Identified key gaps from v6 that led to v7 improvements:

| Gap Identified | v7 Resolution |
|---|---|
| "Ground truth" overstates LLM-extracted labels | Renamed to "reference labels" (silver standard) throughout |
| 18 findings too narrow for CXR vocabulary | Expanded to 40 with priority, type, acuity metadata |
| No post-extraction quality checks | 6 validation rules in Stage 1.5 |
| No Portuguese NLP verification | pt_rules.py catches negation/hedging conflicts |
| Etiologic findings treated same as descriptive | Calibrated arbitration rules in comparison.py |
| No ontology versioning or audit trail | Run manifests, provenance fields, deterministic synonym maps |

### Round 2 (Final Review)

Status: **Ready for controlled 1,126-report run with human adjudication subset.**

Remaining recommendations for post-MVP:
- Adjudicate 200-case subset with radiologist to validate silver standard
- Add more hierarchy relationships as ontology expands
- Consider per-institution prompt tuning (96 customers with varying report styles)
- Implement batch mode (submit/status/download) for cost savings at scale

---

## Provenance

This specification evolved through:
- **v1-v3**: Pipeline complexity exploration (rule-based → LLM → production features)
- **v4**: Simplified batch POC (TXV + MedGemma, 4-step pipeline)
- **v5**: MedSigLIP upgrade (zero-shot, no training, same 4-step pipeline)
- **10-agent MI2 research**: Deep dive on MedImageInsight (adapter approach evaluated, circularity identified)
- **AI Council Round 1**: GPT + Gemini + Grok unanimous on circularity fix
- **AI Council Round 2**: Claude Code rate limits identified, CheXbert proposed (English-only → rejected for PT), Anthropic Batch API selected
- **CXR Foundation investigation**: TensorFlow-only, no MPS → rejected
- **User reframe**: Reference label creation + model evaluation is the real goal, not discrepancy detection
- **Portuguese-first**: Brazilian telemedicine database, all prompts in PT
- **Playbook v3 alignment**: Label vocabulary, quality flags, backend interface designed for production transition
- **v6 data analysis (2026-03-23)**: Deep dive into ListaLLM.csv revealed: no header, semicolons, BOM, 6,542 unique exams, only 1,163 unique report texts (template reuse), 96 customers (not patients), unreliable label column, 432 PHI filenames. Led to: SHA-256 report dedup (85% cost savings), hybrid sync/batch extraction, pilot-first workflow, flag comparison as validation metric.
- **v7 implementation (2026-03-23)**: 40-finding ontology with metadata, config-driven prompt generation, 6 validation rules, PT NLP rules, Tier 2 discovery with synonym dedup, calibrated arbitration with hierarchy roll-up, named label maps, run manifests, async concurrent extraction. 228 tests. E2E validated on 100 reports (100% classification agreement, 91% finding agreement). Ready for controlled 1,126-report production run.

---

**RESEARCH USE ONLY — Not a diagnostic device. All labels and classifications are silver-standard reference labels requiring verification by a qualified radiologist before clinical use.**
