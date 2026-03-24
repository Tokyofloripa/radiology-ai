"""Mock backend for deterministic testing. Scores derived from exam_id hash."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import numpy as np

from cxr_mvp.backends.base import VisionBackend
from cxr_mvp.models import ModelPrediction


class MockBackend(VisionBackend):
    """Deterministic backend for unit/integration tests."""

    def name(self) -> str:
        return "mock"

    def version(self) -> str:
        return "mock-1.0.0"

    def predict(
        self,
        pixel_array: np.ndarray,
        dicom_meta: dict,
    ) -> ModelPrediction:
        exam_id = dicom_meta.get("exam_id", "unknown")
        seed = int(hashlib.sha256(exam_id.encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)

        score = float(rng.random())
        return ModelPrediction(
            exam_id=exam_id,
            model_name=self.name(),
            model_version=self.version(),
            binary_label="abnormal" if score > 0.5 else "normal",
            binary_score=score,
            findings={
                "cardiomegaly": {"label": "Positive" if score > 0.6 else "Negative", "score": score},
                "effusion": {"label": "Positive" if score > 0.7 else "Negative", "score": max(0, score - 0.1)},
            },
            inference_timestamp=datetime.now(timezone.utc).isoformat(),
        )
