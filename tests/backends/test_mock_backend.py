"""Tests for mock backend — verifies the VisionBackend contract."""
from __future__ import annotations

from cxr_mvp.backends.mock_backend import MockBackend
from cxr_mvp.models import ModelPrediction


class TestMockBackend:
    def test_implements_vision_backend(self):
        backend = MockBackend()
        assert backend.name() == "mock"
        assert backend.version() == "mock-1.0.0"

    def test_predict_returns_model_prediction(self, dummy_pixel_array, dummy_dicom_meta):
        backend = MockBackend()
        result = backend.predict(dummy_pixel_array, dummy_dicom_meta)
        assert isinstance(result, ModelPrediction)
        assert result.model_name == "mock"
        assert result.binary_label in ("normal", "abnormal")
        assert 0.0 <= result.binary_score <= 1.0

    def test_deterministic_for_same_exam_id(self, dummy_pixel_array, dummy_dicom_meta):
        backend = MockBackend()
        r1 = backend.predict(dummy_pixel_array, dummy_dicom_meta)
        r2 = backend.predict(dummy_pixel_array, dummy_dicom_meta)
        assert r1.binary_score == r2.binary_score

    def test_different_exam_ids_produce_different_scores(self, dummy_pixel_array, dummy_dicom_meta):
        backend = MockBackend()
        meta2 = {**dummy_dicom_meta, "exam_id": "TEST002"}
        r1 = backend.predict(dummy_pixel_array, dummy_dicom_meta)
        r2 = backend.predict(dummy_pixel_array, meta2)
        assert r1.binary_score != r2.binary_score

    def test_healthcheck(self):
        backend = MockBackend()
        health = backend.healthcheck()
        assert health["status"] == "ok"
