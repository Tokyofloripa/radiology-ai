"""Config-driven prompt generation for CXR text extraction.

Reads findings_cxr.yaml via config.py, generates the Portuguese extraction
prompt with all Tier 1 findings, PT synonym hints, study quality assessment,
Tier 2 discovery instruction, and JSON response schema.

Single source of truth: change YAML, regenerate prompt."""
from __future__ import annotations

import hashlib
from collections import defaultdict

from cxr_mvp.config import load_findings_config


def generate_prompt(config_path: str = "config/findings_cxr.yaml") -> str:
    """Generate the full extraction prompt from config."""
    config = load_findings_config(config_path)

    # Group findings by category for readability
    by_category: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for name in config.finding_names():
        f = config.findings[name]
        by_category[f.category].append((name, f.pt))

    # Build finding list and PT hints
    finding_names = ", ".join(config.finding_names())
    pt_hints = ""
    for category in sorted(by_category.keys()):
        pt_hints += f"\n{category.upper()}:\n"
        for name, pt_terms in by_category[category]:
            pt_hints += f"- {name}: {', '.join(pt_terms)}\n"

    # Build JSON schema example (all Absent as template)
    findings_json = ""
    for name in config.finding_names():
        findings_json += f'    "{name}": {{"status": "Absent", "confidence": "high", "evidence": null}},\n'
    findings_json = findings_json.rstrip(",\n") + "\n"

    prompt = f"""Você é um mecanismo de extração de dados de laudos radiológicos. Analise o laudo de radiografia de tórax abaixo e extraia informações estruturadas.

IMPORTANTE: Ignore seções de TÉCNICA e INDICAÇÃO. Extraia achados apenas das seções de ACHADOS e IMPRESSÃO.

LAUDO:
{{REPORT_TEXT}}

TAREFA: Extraia as seguintes informações do laudo acima.

1. CLASSIFICAÇÃO GERAL: Classifique o exame como "normal" ou "abnormal".
   - "normal" = laudo indica exame sem alterações significativas
   - "abnormal" = laudo indica qualquer achado patológico (incluindo dispositivos, achados incidentais, alterações degenerativas)

2. ACHADOS ESPECÍFICOS: Para CADA um dos {len(config.findings)} achados abaixo, forneça:
   - "status": exatamente um de "Positive", "Negative", "Uncertain", "Absent", "Not_Assessable"
   - "confidence": "high", "medium" ou "low"
   - "evidence": a frase exata do laudo que sustenta sua classificação (null se Absent)

ACHADOS PARA CLASSIFICAR:
{finding_names}

DICAS DE TERMOS EM PORTUGUÊS:
{pt_hints}
DISPOSITIVOS MÉDICOS:
- Para dispositivos (endotracheal_tube, central_line, feeding_tube, chest_drain, cardiac_device, surgical_hardware): "Positive" = dispositivo presente, "Negative" = explicitamente ausente/removido, "Absent" = não mencionado.
- Se um dispositivo está MAL POSICIONADO, marque device_malposition como "Positive" além do dispositivo específico.

REGRAS:
- "Positive" = achado explicitamente descrito como presente
- "Negative" = achado explicitamente negado ("sem", "ausência de", "dentro dos limites")
- "Uncertain" = linguagem duvidosa ("não se pode excluir", "possível", "a esclarecer", "discreto")
- "Absent" = achado não mencionado no laudo
- "Not_Assessable" = avaliação prejudicada (estudo no leito, hipoinsuflação, laudo incompleto)

IMPORTANTE:
- Use EXATAMENTE os nomes dos achados listados acima como chaves.
- O campo "evidence" deve ser a citação EXATA do laudo em português.
- "Pulmões limpos" ou "sem alterações" implica Negative para achados pulmonares.
- Se o laudo diz "normal" sem detalhar, classifique todos como Negative.

3. QUALIDADE DO ESTUDO: Avalie a qualidade técnica do exame.
   - "study_quality": "adequate" ou "suboptimal"
   - "study_quality_flags": lista de problemas (vazio se adequado)
   Problemas possíveis: "bedside", "rotation", "hyperinflation", "underexposure", "overexposure", "motion", "incomplete"
   Se o laudo não mencionar limitações técnicas, assuma "adequate" com lista vazia.
   Se marcar "suboptimal", inclua pelo menos um flag na lista.

4. ACHADOS ADICIONAIS: Se o laudo descrever algum achado ANORMAL ou PATOLÓGICO que NÃO se encaixe nos {len(config.findings)} achados acima, liste-os em "other_findings". Para cada:
   - "name": termo médico CURTO e canônico em inglês (snake_case, máximo 2-3 palavras). Exemplos corretos: "bronchiectasis", "pericardial_effusion", "hilar_adenopathy". Exemplos INCORRETOS: "bilateral_cylindrical_bronchiectasis_in_lower_lobes", "peribronchiovascular_markings_accentuation"
   - "original_term": o termo exato em português do laudo
   - "status": Positive, Negative, Uncertain
   - "confidence": high, medium, low
   - "evidence": citação exata do laudo
   - "suggested_category": uma de: pulmonary, infectious, musculoskeletal, vascular, device, structural, soft_tissue, other
   IMPORTANTE para other_findings:
   - NÃO reporte achados já cobertos pelos {len(config.findings)} achados listados acima (ex: se "velamento de seio costofrênico" classifique em effusion, não como other_finding)
   - NÃO reporte descrições de anatomia NORMAL (ex: "hilos de aspecto normal", "mediastino de contornos preservados" NÃO são achados)
   - Apenas achados ANORMAIS/PATOLÓGICOS não cobertos pela lista principal
   Se não houver achados adicionais, retorne "other_findings": []

Responda APENAS com JSON válido no formato abaixo. Sem explicações, sem markdown.

{{
  "classification": "normal",
  "findings": {{
{findings_json}  }},
  "other_findings": [],
  "study_quality": "adequate",
  "study_quality_flags": []
}}"""

    return prompt


def prompt_hash(config_path: str = "config/findings_cxr.yaml") -> str:
    """SHA-256 hash of generated prompt (truncated to 16 chars)."""
    text = generate_prompt(config_path)
    return hashlib.sha256(text.encode()).hexdigest()[:16]
