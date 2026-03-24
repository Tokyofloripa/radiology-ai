"""Abstract base class for vision model backends.

Every backend implements this interface. Adding a new model = one new file.
Return typed ModelPrediction, never raw dicts."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np

from cxr_mvp.models import ModelPrediction


class VisionBackend(ABC):
    """Interface that all vision model backends must implement."""

    @abstractmethod
    def name(self) -> str:
        """Unique backend identifier (e.g., 'torchxrayvision')."""

    @abstractmethod
    def version(self) -> str:
        """Model weights version or API version string for provenance."""

    @abstractmethod
    def predict(
        self,
        pixel_array: np.ndarray,
        dicom_meta: dict[str, Any],
    ) -> ModelPrediction:
        """Classify a single study image.

        Args:
            pixel_array: Normalized 2D array (MONOCHROME2, windowed, float32).
            dicom_meta: DICOM metadata dict (view_position, body_part, etc.).

        Returns:
            ModelPrediction with binary label, score, and per-finding predictions.
        """

    def supports(self, body_part: str) -> bool:
        """Whether this backend supports the given body part. Override if needed."""
        return True

    def healthcheck(self) -> dict:
        """Verify the backend is ready (model loaded, API reachable, etc.)."""
        return {"status": "ok", "backend": self.name()}
