"""Abstract base class for text extraction backends.

Mirrors the VisionBackend pattern. Each provider gets one file.
Batch vs sync is an internal implementation detail."""
from __future__ import annotations

from abc import ABC, abstractmethod

from cxr_mvp.models import ExtractionResult, UniqueReport


class ExtractionBackend(ABC):
    """Interface that all text extraction backends must implement."""

    @abstractmethod
    def name(self) -> str:
        """Config name (e.g., 'sonnet', 'opus')."""

    @abstractmethod
    def version(self) -> str:
        """Full model_id from config (e.g., 'claude-sonnet-4-6-20250514').
        Used in provenance/run manifests."""

    @abstractmethod
    def extract(
        self,
        reports: list[UniqueReport],
        prompt: str,
        output_dir: str,
    ) -> list[ExtractionResult]:
        """Extract structured labels from reports.

        Args:
            reports: UniqueReport list from Stage 0 dedup.
            prompt: The extraction prompt template (with {REPORT_TEXT} placeholder).
            output_dir: Base directory. Backend writes to output_dir/extractions_{name}.jsonl.

        Returns:
            List of validated ExtractionResult objects.
        """

    @abstractmethod
    def supports_batch(self) -> bool:
        """Whether this backend supports async batch processing."""

    async def extract_async(
        self,
        reports: list[UniqueReport],
        prompt: str,
        output_dir: str,
        concurrency: int = 20,
    ) -> list[ExtractionResult]:
        """Async extraction with concurrency. Default: falls back to sync extract()."""
        return self.extract(reports, prompt, output_dir)
