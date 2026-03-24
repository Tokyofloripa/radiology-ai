"""Tests for ExtractionBackend ABC contract."""
from __future__ import annotations

import pytest

from cxr_mvp.extractors.base import ExtractionBackend
from cxr_mvp.models import ExtractionResult, UniqueReport


class TestExtractionBackendABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError, match="abstract"):
            ExtractionBackend()

    def test_concrete_subclass_works(self):
        class DummyExtractor(ExtractionBackend):
            def name(self) -> str:
                return "dummy"

            def version(self) -> str:
                return "dummy-1.0"

            def extract(self, reports, prompt, output_dir):
                return []

            def supports_batch(self) -> bool:
                return False

        ext = DummyExtractor()
        assert ext.name() == "dummy"
        assert ext.version() == "dummy-1.0"
        assert ext.supports_batch() is False
        assert ext.extract([], "", "/tmp") == []

    def test_missing_method_raises_error(self):
        class IncompleteExtractor(ExtractionBackend):
            def name(self) -> str:
                return "incomplete"
            # missing version, extract, supports_batch

        with pytest.raises(TypeError):
            IncompleteExtractor()


import asyncio


class TestExtractionBackendAsync:
    def test_default_extract_async_falls_back_to_sync(self):
        class SyncOnlyExtractor(ExtractionBackend):
            def name(self) -> str:
                return "sync_only"
            def version(self) -> str:
                return "1.0"
            def extract(self, reports, prompt, output_dir):
                return [{"mock": True}]
            def supports_batch(self) -> bool:
                return False

        ext = SyncOnlyExtractor()
        result = asyncio.run(ext.extract_async([], "", "/tmp"))
        assert result == [{"mock": True}]
