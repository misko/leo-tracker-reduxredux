"""Stable presentation-v1 contracts and read-model projection."""

from leo.presentation.fixtures import build_fixture_repository, write_fixture_artifacts
from leo.presentation.models import (
    AnalysisProductV1,
    ProductContentV1,
    RecordingDetailV1,
    RecordingSearchResponseV1,
    RecordingSummaryV1,
    StreamAnalysisV1,
    SystemStatusV1,
)
from leo.presentation.projectors import decimate_product_points_v1, recording_summary_v1
from leo.presentation.repository import FixturePresentationRepository, PresentationRepository

__all__ = [
    "AnalysisProductV1",
    "FixturePresentationRepository",
    "PresentationRepository",
    "ProductContentV1",
    "RecordingDetailV1",
    "RecordingSearchResponseV1",
    "RecordingSummaryV1",
    "StreamAnalysisV1",
    "SystemStatusV1",
    "build_fixture_repository",
    "decimate_product_points_v1",
    "recording_summary_v1",
    "write_fixture_artifacts",
]
