"""Versioned numerical products for segmented scanner analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.digests import Sha256Digest
from leo.contracts.standard_pipeline import StandardNumericalWaterfallV2
from leo.scanner.models import (
    Glrt64FirstDetection,
    ScanDecision,
    ScannerConfiguration,
    ScannerModel,
    ScannerReport,
    ScanTarget,
)


class ScannerGlrt64CandidateMetricsV1(ScannerModel):
    schema_version: Literal[1] = 1
    candidate_rank: Annotated[int, Field(ge=0)]
    epoch_sample: Annotated[int, Field(ge=0)]
    acquired_cfo_hz: float
    residual_cfo_hz: float
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float
    passed_margin_gate: bool


class ScannerGlrt64ProbeMetricsV1(ScannerModel):
    schema_version: Literal[1] = 1
    receiver_id: int
    probe_index: Annotated[int, Field(ge=0)]
    probe_start_ms: Annotated[int, Field(ge=0)]
    candidates: tuple[ScannerGlrt64CandidateMetricsV1, ...]


class ScannerFrameAnalysisV1(ScannerModel):
    schema_version: Literal[1] = 1
    status: Literal["complete", "failed"]
    target_index: Annotated[int, Field(ge=0)]
    target: ScanTarget
    source_sample_start: Annotated[int, Field(ge=0)]
    sample_count: Annotated[int, Field(ge=0)]
    requested_if_center_hz: Annotated[int, Field(gt=0)]
    actual_if_center_hz: Annotated[int | None, Field(gt=0)]
    iq_sha256: Sha256Digest | None
    decision: ScanDecision
    decision_best_margin: float | None
    full_best_margin: float | None
    first_detection: Glrt64FirstDetection | None
    reason: str
    probes: tuple[ScannerGlrt64ProbeMetricsV1, ...]
    waterfalls: tuple[StandardNumericalWaterfallV2, ...]

    @model_validator(mode="after")
    def _frame_is_consistent(self) -> Self:
        if self.requested_if_center_hz != self.target.if_center_hz:
            raise ValueError("scanner analysis requested IF disagrees with target")
        receiver_ids = tuple(item.receiver_ids[0] for item in self.waterfalls)
        if len(set(receiver_ids)) != len(receiver_ids):
            raise ValueError("scanner analysis waterfall receivers must be unique")
        if self.status == "failed":
            if (
                self.sample_count
                or self.actual_if_center_hz is not None
                or self.iq_sha256 is not None
                or self.decision is not ScanDecision.INCONCLUSIVE
                or self.probes
                or self.waterfalls
            ):
                raise ValueError("failed scanner analysis frame contains numerical evidence")
        elif (
            self.sample_count == 0
            or self.actual_if_center_hz is None
            or self.iq_sha256 is None
            or self.decision is ScanDecision.INCONCLUSIVE
        ):
            raise ValueError("complete scanner analysis frame is incomplete")
        return self


class ScannerAnalysisMetricsV1(ScannerModel):
    schema_version: Literal[1] = 1
    kind: Literal["starlink_scanner_analysis_metrics"] = "starlink_scanner_analysis_metrics"
    scan_id: str
    input_uri: str
    input_manifest_sha256: Sha256Digest
    analyzer_id: Literal["standard-scan-analysis-v1"] = "standard-scan-analysis-v1"
    configuration: ScannerConfiguration
    frames: tuple[ScannerFrameAnalysisV1, ...]

    @model_validator(mode="after")
    def _covers_plan(self) -> Self:
        if tuple(item.target_index for item in self.frames) != tuple(
            range(len(self.configuration.targets))
        ):
            raise ValueError("scanner analysis frames must cover the ordered target plan")
        if tuple(item.target for item in self.frames) != self.configuration.targets:
            raise ValueError("scanner analysis targets disagree with configuration")
        expected_probes = self.configuration.scheduled_probe_count * len(
            self.configuration.receiver_ids
        )
        for frame in self.frames:
            if frame.status == "failed":
                continue
            if frame.sample_count != self.configuration.dwell_samples:
                raise ValueError("scanner analysis frame duration disagrees with configuration")
            if len(frame.probes) != expected_probes:
                raise ValueError("scanner analysis probe coverage is incomplete")
            if tuple(item.receiver_ids[0] for item in frame.waterfalls) != (
                self.configuration.receiver_ids
            ):
                raise ValueError("scanner analysis waterfall coverage is incomplete")
        return self


class ScannerAnalysisBundleManifestV1(ScannerModel):
    schema_version: Literal[1] = 1
    kind: Literal["starlink_scanner_analysis_bundle"] = "starlink_scanner_analysis_bundle"
    analysis_id: str
    scan_id: str
    input_uri: str
    input_manifest_sha256: Sha256Digest
    analyzer_id: Literal["standard-scan-analysis-v1"] = "standard-scan-analysis-v1"
    report_relative_path: Literal["scanner-report.v1.json"] = "scanner-report.v1.json"
    report_sha256: Sha256Digest
    metrics_relative_path: Literal["scanner-metrics.v1.json"] = "scanner-metrics.v1.json"
    metrics_sha256: Sha256Digest
    waterfall_png_relative_path: Literal["presentation/scanner-waterfall.v1.png"] = (
        "presentation/scanner-waterfall.v1.png"
    )
    waterfall_png_sha256: Sha256Digest
    glrt64_png_relative_path: Literal["presentation/scanner-glrt64-response.v1.png"] = (
        "presentation/scanner-glrt64-response.v1.png"
    )
    glrt64_png_sha256: Sha256Digest


class ScannerAnalysisHistoryItemV1(ScannerModel):
    """Newest published Standard analysis selected for one scan."""

    schema_version: Literal[1] = 1
    published_at: datetime
    scan_id: str
    analysis_id: str
    report: ScannerReport


class ScannerAnalysisHistoryPageV1(ScannerModel):
    """Bounded newest-first scanner analysis gallery page."""

    schema_version: Literal[1] = 1
    cursor: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1, le=100)]
    total: Annotated[int, Field(ge=0)]
    next_cursor: int | None
    items: tuple[ScannerAnalysisHistoryItemV1, ...]


class ScannerAnalysisHistoryItemV2(ScannerModel):
    """One scanner analysis with capture and publication clocks kept distinct."""

    schema_version: Literal[2] = 2
    captured_at: datetime
    published_at: datetime
    scan_id: str
    analysis_id: str
    report: ScannerReport


class ScannerAnalysisHistoryPageV2(ScannerModel):
    """Capture-time-ordered scanner gallery page."""

    schema_version: Literal[2] = 2
    cursor: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1, le=100)]
    total: Annotated[int, Field(ge=0)]
    next_cursor: int | None
    items: tuple[ScannerAnalysisHistoryItemV2, ...]
