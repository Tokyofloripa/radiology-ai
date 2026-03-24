"""Anthropic extraction backend — handles any claude-* model.

Supports sync (immediate) and batch (50% discount) modes.
Prompt formatting, response parsing, Pydantic validation, checkpoint/resume."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path

from anthropic import AsyncAnthropic

from cxr_mvp.extractors.base import ExtractionBackend
from cxr_mvp.models import (
    ExtractionResult,
    FindingLabel,
    ReportExtraction,
    UniqueReport,
)


def parse_llm_response(raw_text: str) -> dict:
    """Parse JSON from LLM response, handling markdown fences."""
    text = raw_text.strip()
    if text.startswith("```"):
        # Strip opening fence (```json or ```)
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        # Strip closing fence
        text = text.rsplit("```", 1)[0]
    return json.loads(text)


def validate_extraction(
    data: dict,
    report_hash: str,
    prompt_hash: str,
    model_name: str,
    expected_findings: list[str] | None = None,
) -> tuple[ExtractionResult | None, str | None]:
    """Validate LLM output against schema. Returns (result, error_or_None).

    Args:
        expected_findings: List of finding names that must be present.
            Loaded from config/findings_cxr.yaml by the caller.
            If None or empty, finding completeness check is skipped.
    """
    if expected_findings is None:
        expected_findings = []

    try:
        # Validate via Pydantic
        extraction = ReportExtraction(
            classification=data.get("classification", "unknown"),
            findings={
                k: FindingLabel(**v) if isinstance(v, dict) else FindingLabel(status=str(v))
                for k, v in data.get("findings", {}).items()
            },
        )

        # Check all expected findings present
        if expected_findings:
            missing = set(expected_findings) - set(extraction.findings.keys())
            if missing:
                return None, f"missing_findings:{','.join(sorted(missing))}"

        # Check classification valid
        if extraction.classification not in ("normal", "abnormal"):
            return None, f"invalid_classification:{extraction.classification}"

        # Parse other_findings (Tier 2) — gracefully handle malformed entries
        other_findings = []
        for f in data.get("other_findings", []):
            if isinstance(f, dict):
                other_findings.append({
                    "name": f.get("name", "unknown"),
                    "original_term": f.get("original_term", ""),
                    "status": f.get("status", "Positive"),
                    "confidence": f.get("confidence", "medium"),
                    "evidence": f.get("evidence"),
                    "suggested_category": f.get("suggested_category", "other"),
                })

        # Parse study quality
        study_quality = data.get("study_quality", "adequate")
        if study_quality not in ("adequate", "suboptimal"):
            study_quality = "adequate"
        study_quality_flags = data.get("study_quality_flags", [])
        if not isinstance(study_quality_flags, list):
            study_quality_flags = []

        result = ExtractionResult(
            report_hash=report_hash,
            classification=extraction.classification,
            findings={k: v.model_dump() for k, v in extraction.findings.items()},
            other_findings=other_findings,
            extraction_model=model_name,
            prompt_hash=prompt_hash,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            study_quality=study_quality,
            study_quality_flags=study_quality_flags,
        )
        return result, None

    except (ValueError, KeyError, TypeError) as e:
        return None, f"validation_error:{str(e)[:200]}"


class AnthropicExtractor(ExtractionBackend):
    """Extraction backend for Anthropic models (Sonnet, Opus, etc.).

    One class handles all claude-* models. model_id and mode from config."""

    def __init__(
        self,
        config_name: str,
        model_id: str,
        mode: str = "batch",
        temperature: int = 0,
        max_tokens: int = 1024,
    ) -> None:
        self._name = config_name
        self._model_id = model_id
        self._mode = mode
        self._temperature = temperature
        self._max_tokens = max_tokens

    def name(self) -> str:
        return self._name

    def version(self) -> str:
        return self._model_id

    def supports_batch(self) -> bool:
        return True  # Anthropic always supports batch

    def _load_completed_hashes(self, output_dir: str) -> set[str]:
        """Checkpoint: which report_hashes are already extracted."""
        output_path = Path(output_dir) / f"extractions_{self._name}.jsonl"
        done: set[str] = set()
        if output_path.exists():
            with open(output_path) as f:
                for line in f:
                    try:
                        done.add(json.loads(line)["report_hash"])
                    except (json.JSONDecodeError, KeyError):
                        pass
        return done

    def _prompt_hash(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]

    @staticmethod
    def _result_to_dict(result: ExtractionResult) -> dict:
        """Serialize ExtractionResult for JSONL output."""
        from dataclasses import asdict
        return asdict(result)

    def extract(
        self,
        reports: list[UniqueReport],
        prompt: str,
        output_dir: str,
    ) -> list[ExtractionResult]:
        """Run extraction — sync mode.

        NOTE: Batch mode (submit/status/download) is deferred to a follow-up task.
        This implementation covers sync mode for pilot + moderate-scale runs."""
        from anthropic import Anthropic

        client = Anthropic()
        phash = self._prompt_hash(prompt)
        done = self._load_completed_hashes(output_dir)

        # Load expected findings from config for validation
        try:
            from cxr_mvp.config import load_findings_config
            config = load_findings_config()
            expected_findings = config.finding_names()
            ontology_version = config.version
        except FileNotFoundError:
            expected_findings = []
            ontology_version = ""

        remaining = [r for r in reports if r.report_hash not in done]
        if not remaining:
            # Load and return existing results
            return self._load_results(output_dir)

        output_path = Path(output_dir) / f"extractions_{self._name}.jsonl"
        errors_path = Path(output_dir) / f"extraction_errors_{self._name}.jsonl"
        results: list[ExtractionResult] = []

        for i, report in enumerate(remaining):
            rhash = report.report_hash
            filled_prompt = prompt.replace("{REPORT_TEXT}", report.report_text)

            try:
                response = client.messages.create(
                    model=self._model_id,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                    messages=[{"role": "user", "content": filled_prompt}],
                )

                raw_text = response.content[0].text
                data = parse_llm_response(raw_text)
                result, error = validate_extraction(data, rhash, phash, self._name, expected_findings)

                if result:
                    result.ontology_version = ontology_version
                    with open(output_path, "a") as f:
                        f.write(json.dumps(self._result_to_dict(result)) + "\n")
                    results.append(result)
                else:
                    with open(errors_path, "a") as f:
                        f.write(json.dumps({
                            "report_hash": rhash,
                            "error": error,
                            "raw_response": raw_text[:500],
                        }) + "\n")

            except Exception as e:
                with open(errors_path, "a") as f:
                    f.write(json.dumps({
                        "report_hash": rhash,
                        "error": str(e)[:200],
                    }) + "\n")

        return results

    def _load_results(self, output_dir: str) -> list[ExtractionResult]:
        """Load previously extracted results from checkpoint file."""
        output_path = Path(output_dir) / f"extractions_{self._name}.jsonl"
        results: list[ExtractionResult] = []
        if output_path.exists():
            with open(output_path) as f:
                for line in f:
                    data = json.loads(line)
                    results.append(ExtractionResult(**data))
        return results

    async def extract_async(
        self,
        reports: list[UniqueReport],
        prompt: str,
        output_dir: str,
        concurrency: int = 20,
    ) -> list[ExtractionResult]:
        """Async concurrent extraction with semaphore-based rate limiting.

        Args:
            concurrency: Max concurrent API calls (default 20).
                Anthropic rate limit is 1000 RPM; 20 concurrent at ~4s each = ~300 RPM.
        """
        client = AsyncAnthropic()
        phash = self._prompt_hash(prompt)
        done = self._load_completed_hashes(output_dir)

        # Load expected findings from config
        try:
            from cxr_mvp.config import load_findings_config
            config = load_findings_config()
            expected_findings = config.finding_names()
            ontology_version = config.version
        except FileNotFoundError:
            expected_findings = []
            ontology_version = ""

        remaining = [r for r in reports if r.report_hash not in done]
        if not remaining:
            return self._load_results(output_dir)

        output_path = Path(output_dir) / f"extractions_{self._name}.jsonl"
        errors_path = Path(output_dir) / f"extraction_errors_{self._name}.jsonl"
        results: list[ExtractionResult] = []
        sem = asyncio.Semaphore(concurrency)
        lock = asyncio.Lock()  # protects file writes
        completed = 0

        async def extract_one(report: UniqueReport) -> None:
            nonlocal completed
            rhash = report.report_hash
            filled_prompt = prompt.replace("{REPORT_TEXT}", report.report_text)

            async with sem:
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        response = await client.messages.create(
                            model=self._model_id,
                            max_tokens=self._max_tokens,
                            temperature=self._temperature,
                            messages=[{"role": "user", "content": filled_prompt}],
                        )

                        raw_text = response.content[0].text
                        data = parse_llm_response(raw_text)
                        result, error = validate_extraction(
                            data, rhash, phash, self._name, expected_findings
                        )

                        async with lock:
                            if result:
                                result.ontology_version = ontology_version
                                with open(output_path, "a") as f:
                                    f.write(json.dumps(self._result_to_dict(result)) + "\n")
                                results.append(result)
                            else:
                                with open(errors_path, "a") as f:
                                    f.write(json.dumps({
                                        "report_hash": rhash,
                                        "error": error,
                                        "raw_response": raw_text[:500],
                                    }) + "\n")

                            completed += 1
                            if completed % 10 == 0 or completed == len(remaining):
                                print(f"  Progress: {completed}/{len(remaining)}")
                        break  # success — exit retry loop

                    except Exception as e:
                        if attempt < max_retries - 1:
                            wait = 2 ** attempt  # 1s, 2s
                            await asyncio.sleep(wait)
                            continue
                        # Final attempt failed — log error
                        async with lock:
                            with open(errors_path, "a") as f:
                                f.write(json.dumps({
                                    "report_hash": rhash,
                                    "error": f"after {max_retries} retries: {str(e)[:200]}",
                                }) + "\n")
                            completed += 1

        await asyncio.gather(*[extract_one(r) for r in remaining])
        return results
