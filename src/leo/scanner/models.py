"""Versioned scanner configuration and report contracts."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from leo.contracts.digests import Sha256Digest
from leo.contracts.recording import CompressionSettingsV1
from leo.contracts.states import GainMode, SampleFormat, SampleLayout, StarlinkEdge

_CURRENT_RF_CENTERS_HZ = (
    (1, StarlinkEdge.LOWER, 10_709_687_500),
    (1, StarlinkEdge.UPPER, 10_940_312_500),
    (2, StarlinkEdge.LOWER, 10_959_687_500),
    (2, StarlinkEdge.UPPER, 11_190_312_500),
    (3, StarlinkEdge.LOWER, 11_209_687_500),
    (3, StarlinkEdge.UPPER, 11_440_312_500),
    (4, StarlinkEdge.LOWER, 11_459_687_500),
    (4, StarlinkEdge.UPPER, 11_690_312_500),
)


class ScannerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScanTarget(ScannerModel):
    channel: Annotated[int, Field(ge=1)]
    edge: StarlinkEdge
    rf_center_hz: Annotated[int, Field(gt=0)]
    if_center_hz: Annotated[int, Field(gt=0)]


class ScannerConfiguration(ScannerModel):
    schema_version: Literal[1] = 1
    band_plan_id: str = "starlink-low-ch1-ch4-v1"
    lnb_lo_hz: Annotated[int, Field(gt=0)] = 9_750_000_000
    sample_rate_hz: Annotated[int, Field(gt=0)] = 2_500_000
    bandwidth_hz: Annotated[int, Field(gt=0)] = 2_500_000
    dwell_ms: Annotated[int, Field(ge=20, le=5_000, multiple_of=20)] = 80
    probe_ms: Literal[20] = 20
    kernel_buffers: Literal[1] = 1
    receiver_ids: tuple[int, ...] = (0, 1)
    gain_mode: GainMode = GainMode.MANUAL
    gain_db: float = 40.0
    glrt64_margin_gate: Annotated[float, Field(gt=0)] = 0.025
    maximum_acquisition_candidates: Annotated[int, Field(ge=1, le=16)] = 8
    targets: tuple[ScanTarget, ...]

    @model_validator(mode="after")
    def _geometry_is_exact(self) -> Self:
        if self.bandwidth_hz > self.sample_rate_hz:
            raise ValueError("scanner bandwidth cannot exceed sample rate")
        if len(set(self.receiver_ids)) != len(self.receiver_ids) or not self.receiver_ids:
            raise ValueError("scanner receiver IDs must be nonempty and unique")
        if len(set((item.channel, item.edge) for item in self.targets)) != len(self.targets):
            raise ValueError("scanner targets must be unique by channel and edge")
        if tuple(sorted(self.targets, key=lambda item: item.if_center_hz)) != self.targets:
            raise ValueError("scanner targets must be ordered by increasing IF center")
        if not math.isfinite(self.gain_db):
            raise ValueError("scanner gain must be finite")
        return self

    @property
    def dwell_samples(self) -> int:
        return self.sample_rate_hz * self.dwell_ms // 1_000

    @property
    def probe_samples(self) -> int:
        return self.sample_rate_hz * self.probe_ms // 1_000

    @property
    def probe_stride_ms(self) -> int:
        """Half-window stride used by the fixed scanner analysis geometry."""

        return self.probe_ms // 2

    @property
    def probe_stride_samples(self) -> int:
        return self.sample_rate_hz * self.probe_stride_ms // 1_000

    @property
    def scheduled_probe_count(self) -> int:
        return (self.dwell_samples - self.probe_samples) // self.probe_stride_samples + 1


def current_low_band_targets(lnb_lo_hz: int = 9_750_000_000) -> tuple[ScanTarget, ...]:
    """Return every presently published channel edge reachable by the low LNB."""

    targets = tuple(
        ScanTarget(
            channel=channel,
            edge=edge,
            rf_center_hz=rf_center,
            if_center_hz=rf_center - lnb_lo_hz,
        )
        for channel, edge, rf_center in _CURRENT_RF_CENTERS_HZ
    )
    return tuple(sorted(targets, key=lambda item: item.if_center_hz))


class ScanDecision(StrEnum):
    ACTIVE = "active"
    NO_DETECTION = "no_detection"
    INCONCLUSIVE = "inconclusive"


class Glrt64FirstDetection(ScannerModel):
    receiver_id: int
    probe_index: Annotated[int, Field(ge=0)]
    probe_start_ms: Annotated[int, Field(ge=0)]
    candidate_rank: Annotated[int, Field(ge=0)]
    epoch_sample: Annotated[int, Field(ge=0)]
    acquired_cfo_hz: float
    residual_cfo_hz: float
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float


class ScanEdgeResult(ScannerModel):
    target: ScanTarget
    decision: ScanDecision
    requested_if_center_hz: int
    actual_if_center_hz: int | None
    tune_ms: float | None
    listen_ms: float | None
    iq_sha256: str | None
    first_detection: Glrt64FirstDetection | None = None
    best_margin: float | None = None
    reason: str


class ScannerReport(ScannerModel):
    schema_version: Literal[1] = 1
    kind: Literal["starlink_scanner_report"] = "starlink_scanner_report"
    scan_id: str
    radio_id: str
    radio_serial: str
    configuration: ScannerConfiguration
    capture_elapsed_ms: float
    analysis_elapsed_ms: float
    results: tuple[ScanEdgeResult, ...]
    candidate_only: Literal[True] = True
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _covers_plan(self) -> Self:
        if tuple(item.target for item in self.results) != self.configuration.targets:
            raise ValueError("scanner report must cover the ordered target plan exactly")
        return self

    @property
    def active_edges(self) -> tuple[ScanTarget, ...]:
        return tuple(item.target for item in self.results if item.decision is ScanDecision.ACTIVE)


class ScannerBurstReportV1(ScannerModel):
    """Ordered reports from one capture-first scanner burst."""

    schema_version: Literal[1] = 1
    kind: Literal["starlink_scanner_burst_report"] = "starlink_scanner_burst_report"
    burst_id: Annotated[str, Field(min_length=1, max_length=128)]
    reports: Annotated[tuple[ScannerReport, ...], Field(min_length=4, max_length=4)]

    @model_validator(mode="after")
    def _is_one_ordered_radio_burst(self) -> Self:
        if len({report.scan_id for report in self.reports}) != len(self.reports):
            raise ValueError("scanner burst scan IDs must be unique")
        first = self.reports[0]
        if any(
            report.radio_id != first.radio_id
            or report.radio_serial != first.radio_serial
            or report.configuration != first.configuration
            for report in self.reports[1:]
        ):
            raise ValueError("scanner burst reports must share one radio and configuration")
        return self

    @property
    def active_edge_count(self) -> int:
        return sum(len(report.active_edges) for report in self.reports)

    @property
    def inconclusive_edge_count(self) -> int:
        return sum(
            result.decision is ScanDecision.INCONCLUSIVE
            for report in self.reports
            for result in report.results
        )


class ScannerIqFrameV1(ScannerModel):
    """One fixed-tuning frame inside a concatenated scanner IQ payload."""

    schema_version: Literal[1] = 1
    frame_index: Annotated[int, Field(ge=0)]
    target_index: Annotated[int, Field(ge=0)]
    target: ScanTarget
    sample_start: Annotated[int, Field(ge=0)]
    sample_count: Annotated[int, Field(gt=0)]
    requested_if_center_hz: Annotated[int, Field(gt=0)]
    actual_if_center_hz: Annotated[int, Field(gt=0)]
    actual_rf_center_hz: Annotated[int, Field(gt=0)]
    tune_ms: Annotated[float, Field(ge=0.0)]
    listen_ms: Annotated[float, Field(ge=0.0)]
    host_request_utc_ns_lower: Annotated[int, Field(ge=0)]
    host_request_utc_ns_upper: Annotated[int, Field(ge=0)]
    host_request_monotonic_ns_lower: Annotated[int, Field(ge=0)]
    host_request_monotonic_ns_upper: Annotated[int, Field(ge=0)]
    uncompressed_bytes: Annotated[int, Field(gt=0)]
    uncompressed_sha256: Sha256Digest

    @model_validator(mode="after")
    def _frame_is_consistent(self) -> Self:
        if self.requested_if_center_hz != self.target.if_center_hz:
            raise ValueError("scanner IQ frame requested IF disagrees with its target")
        if self.actual_rf_center_hz <= self.actual_if_center_hz:
            raise ValueError("scanner IQ frame actual RF must include a positive LNB offset")
        if self.host_request_utc_ns_lower > self.host_request_utc_ns_upper:
            raise ValueError("scanner IQ frame UTC bracket is reversed")
        if self.host_request_monotonic_ns_lower > self.host_request_monotonic_ns_upper:
            raise ValueError("scanner IQ frame monotonic bracket is reversed")
        return self


class ScannerIqCaptureFailureV1(ScannerModel):
    schema_version: Literal[1] = 1
    target_index: Annotated[int, Field(ge=0)]
    target: ScanTarget
    reason: Annotated[str, Field(min_length=1, max_length=2048)]


class ScannerIqBundleManifestV1(ScannerModel):
    """Commit record for one retuned scanner sweep stored as one IQ payload.

    The payload sample coordinate is contiguous only as a storage coordinate.
    Frame metadata is authoritative for tuning and signal-time boundaries.
    """

    schema_version: Literal[1] = 1
    kind: Literal["starlink_scanner_iq_bundle"] = "starlink_scanner_iq_bundle"
    scan_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    created_utc_ns: Annotated[int, Field(ge=0)]
    finalized_utc_ns: Annotated[int, Field(ge=0)]
    radio_id: str
    radio_serial: str
    radio_uri: str
    configuration: ScannerConfiguration
    frames: tuple[ScannerIqFrameV1, ...]
    failures: tuple[ScannerIqCaptureFailureV1, ...] = ()
    total_sample_count: Annotated[int, Field(gt=0)]
    payload_relative_path: Literal["iq.ci16.zst"] = "iq.ci16.zst"
    sample_format: Literal[SampleFormat.CI16_LE] = SampleFormat.CI16_LE
    sample_layout: Literal[SampleLayout.SAMPLE_RECEIVER_IQ] = SampleLayout.SAMPLE_RECEIVER_IQ
    uncompressed_bytes: Annotated[int, Field(gt=0)]
    compressed_bytes: Annotated[int, Field(gt=0)]
    uncompressed_sha256: Sha256Digest
    compressed_sha256: Sha256Digest
    compression: CompressionSettingsV1

    @model_validator(mode="after")
    def _bundle_is_consistent(self) -> Self:
        if self.finalized_utc_ns < self.created_utc_ns:
            raise ValueError("scanner IQ bundle finalization precedes capture")
        if not self.frames:
            raise ValueError("scanner IQ bundle requires at least one captured frame")
        expected_sample_start = 0
        covered_targets: list[int] = []
        frame_target_indexes: list[int] = []
        for expected_frame_index, frame in enumerate(self.frames):
            if frame.frame_index != expected_frame_index:
                raise ValueError("scanner IQ frame indexes must be contiguous from zero")
            if frame.sample_start != expected_sample_start:
                raise ValueError("scanner IQ frame sample ranges must be contiguous")
            if frame.target_index >= len(self.configuration.targets):
                raise ValueError("scanner IQ frame target index is outside the scan plan")
            if frame.target != self.configuration.targets[frame.target_index]:
                raise ValueError("scanner IQ frame target disagrees with the scan plan")
            if frame.sample_count != self.configuration.dwell_samples:
                raise ValueError("scanner IQ frame sample count disagrees with the dwell plan")
            if (
                frame.actual_rf_center_hz
                != frame.actual_if_center_hz + self.configuration.lnb_lo_hz
            ):
                raise ValueError("scanner IQ frame actual RF disagrees with the LNB plan")
            expected_frame_bytes = frame.sample_count * len(self.configuration.receiver_ids) * 4
            if frame.uncompressed_bytes != expected_frame_bytes:
                raise ValueError("scanner IQ frame bytes disagree with CI16 geometry")
            expected_sample_start += frame.sample_count
            covered_targets.append(frame.target_index)
            frame_target_indexes.append(frame.target_index)
        if frame_target_indexes != sorted(frame_target_indexes):
            raise ValueError("scanner IQ frames must retain scan-plan order")
        for failure in self.failures:
            if failure.target_index >= len(self.configuration.targets):
                raise ValueError("scanner IQ failure target index is outside the scan plan")
            if failure.target != self.configuration.targets[failure.target_index]:
                raise ValueError("scanner IQ failure target disagrees with the scan plan")
            covered_targets.append(failure.target_index)
        if tuple(sorted(covered_targets)) != tuple(range(len(self.configuration.targets))):
            raise ValueError("scanner IQ bundle must account for every planned target exactly once")
        if len(set(covered_targets)) != len(covered_targets):
            raise ValueError("scanner IQ bundle accounts for a target more than once")
        if expected_sample_start != self.total_sample_count:
            raise ValueError("scanner IQ total sample count disagrees with its frames")
        expected_bytes = self.total_sample_count * len(self.configuration.receiver_ids) * 4
        if self.uncompressed_bytes != expected_bytes:
            raise ValueError("scanner IQ payload bytes disagree with CI16 geometry")
        return self
