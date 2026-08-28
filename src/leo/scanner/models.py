"""Versioned scanner configuration and report contracts."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from leo.contracts.digests import Sha256Digest
from leo.contracts.recording import CompressionSettingsV1
from leo.contracts.states import GainMode, SampleFormat, SampleLayout, StarlinkEdge
from leo.scanner.metadata import metadata_reports_rx_overflow

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
    dwell_ms: Annotated[int, Field(ge=20, le=5_000, multiple_of=20)] = 120
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


class ScannerConfigurationV2(ScannerConfiguration):
    """Continuity-observable live scanner policy.

    Every target is captured through a fresh metadata buffer after the LO has
    settled.  A deeper kernel queue is therefore safe: it cannot contain IQ
    from the preceding target.
    """

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    kernel_buffers: Annotated[int, Field(ge=2, le=64)] = 8  # type: ignore[assignment]
    tuning_settle_us: Annotated[int, Field(ge=0, le=1_000_000)] = 250
    reset_receive_buffer_before_each_target: Literal[True] = True
    require_device_metadata: Literal[True] = True


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


class ScannerFrameContinuityEvidenceV1(ScannerModel):
    """Integrity evidence for one independently retuned scanner target."""

    schema_version: Literal[1] = 1
    status: Literal["attested", "capture_failed"]
    target_index: Annotated[int, Field(ge=0)]
    metadata_abi_version: Annotated[int | None, Field(ge=1, le=2)] = None
    stream_id: Annotated[int | None, Field(gt=0)] = None
    stream_generation: Annotated[str | None, Field(min_length=1, max_length=128)] = None
    buffer_sequence: Annotated[int | None, Field(ge=0)] = None
    source_sequence: Annotated[int | None, Field(ge=0)] = None
    first_sample_sequence: Annotated[int | None, Field(ge=0)] = None
    last_sample_sequence_exclusive: Annotated[int | None, Field(gt=0)] = None
    device_sample_counter: Annotated[int | None, Field(ge=0)] = None
    device_sample_counter_end_exclusive: Annotated[int | None, Field(gt=0)] = None
    metadata_flags: Annotated[int | None, Field(ge=0)] = None
    sample_time_realtime_start_ns: Annotated[int | None, Field(ge=0)] = None
    sample_time_realtime_end_ns: Annotated[int | None, Field(gt=0)] = None
    sample_time_monotonic_start_ns: Annotated[int | None, Field(ge=0)] = None
    sample_time_monotonic_end_ns: Annotated[int | None, Field(gt=0)] = None
    sample_time_uncertainty_ns: Annotated[int | None, Field(ge=0)] = None
    kernel_buffers_requested: Annotated[int | None, Field(ge=2, le=64)] = None
    kernel_buffers_readback: Annotated[int | None, Field(ge=2, le=64)] = None
    reset_episode: Annotated[int | None, Field(gt=0)] = None
    missing_samples_before: Annotated[int, Field(ge=0)] = 0
    overflow_observed: bool = False
    continuity_observable: bool
    within_frame_continuity: Literal["proven_within_returned_buffer", "unavailable_capture_failed"]
    cross_frame_continuity: Literal["not_applicable_retune_boundary"] = (
        "not_applicable_retune_boundary"
    )
    reason: str

    @model_validator(mode="after")
    def _evidence_is_closed(self) -> Self:
        optional = (
            self.metadata_abi_version,
            self.stream_id,
            self.stream_generation,
            self.buffer_sequence,
            self.source_sequence,
            self.first_sample_sequence,
            self.last_sample_sequence_exclusive,
            self.device_sample_counter,
            self.device_sample_counter_end_exclusive,
            self.metadata_flags,
            self.sample_time_realtime_start_ns,
            self.sample_time_realtime_end_ns,
            self.sample_time_monotonic_start_ns,
            self.sample_time_monotonic_end_ns,
            self.sample_time_uncertainty_ns,
            self.kernel_buffers_requested,
            self.kernel_buffers_readback,
            self.reset_episode,
        )
        if self.status == "capture_failed":
            if (
                any(item is not None for item in optional)
                or self.continuity_observable
                or self.within_frame_continuity != "unavailable_capture_failed"
            ):
                raise ValueError("failed scanner frame claims continuity evidence")
            return self
        if (
            any(item is None for item in optional)
            or not self.continuity_observable
            or self.within_frame_continuity != "proven_within_returned_buffer"
            or self.missing_samples_before
            or self.overflow_observed
        ):
            raise ValueError("attested scanner frame has incomplete continuity evidence")
        assert self.first_sample_sequence is not None
        assert self.last_sample_sequence_exclusive is not None
        if self.stream_generation != str(self.stream_id):
            raise ValueError("scanner continuity generation disagrees with raw stream ID")
        if self.source_sequence != self.buffer_sequence:
            raise ValueError(
                "scanner continuity source sequence disagrees with raw buffer sequence"
            )
        if self.buffer_sequence != 0:
            raise ValueError("scanner continuity first buffer/source sequence must be zero")
        if self.device_sample_counter != self.first_sample_sequence:
            raise ValueError("scanner continuity device counter disagrees with raw first sample")
        if self.device_sample_counter_end_exclusive != self.last_sample_sequence_exclusive:
            raise ValueError("scanner continuity canonical and raw counter ends disagree")
        if self.last_sample_sequence_exclusive <= self.first_sample_sequence:
            raise ValueError("scanner continuity sample range does not increase")
        if self.kernel_buffers_readback != self.kernel_buffers_requested:
            raise ValueError("scanner continuity kernel-buffer readback disagrees")
        assert self.metadata_flags is not None
        if self.overflow_observed != metadata_reports_rx_overflow(self.metadata_flags):
            raise ValueError("scanner continuity overflow disagrees with metadata flags bit 11")
        return self


class ScannerFrameContinuityEvidenceV2(ScannerFrameContinuityEvidenceV1):
    """Additive continuity evidence for counter-authoritative metadata ABI 3."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    metadata_abi_version: Literal[3] | None = None  # type: ignore[assignment]


ScannerFrameContinuityEvidenceLike = (
    ScannerFrameContinuityEvidenceV1 | ScannerFrameContinuityEvidenceV2
)


def _validate_continuity_report(
    configuration: ScannerConfigurationV2,
    results: tuple[ScanEdgeResult, ...],
    continuity_evidence: tuple[ScannerFrameContinuityEvidenceLike, ...],
    *,
    continuity_observable: bool,
) -> None:
    if tuple(item.target for item in results) != configuration.targets:
        raise ValueError("scanner report must cover the ordered target plan exactly")
    if tuple(item.target_index for item in continuity_evidence) != tuple(
        range(len(configuration.targets))
    ):
        raise ValueError("scanner report continuity must cover the target plan exactly")
    if any(
        evidence.status == "capture_failed" and result.decision is not ScanDecision.INCONCLUSIVE
        for result, evidence in zip(results, continuity_evidence, strict=True)
    ):
        raise ValueError("scanner report claims a decision from a failed capture")
    attested = tuple(evidence for evidence in continuity_evidence if evidence.status == "attested")
    if continuity_observable != bool(attested):
        raise ValueError("scanner report observability disagrees with attested target evidence")
    generations = tuple(evidence.stream_generation for evidence in attested)
    if len(generations) != len(set(generations)):
        raise ValueError("scanner report reuses a stream generation across reset episodes")
    episodes = tuple(int(evidence.reset_episode or 0) for evidence in attested)
    if episodes != tuple(sorted(set(episodes))):
        raise ValueError("scanner report reset episodes must be unique and ordered")


class ScannerReportV2(ScannerModel):
    """Scanner report bound to at least one continuity-observable V2 frame."""

    schema_version: Literal[2] = 2
    kind: Literal["starlink_scanner_report_v2"] = "starlink_scanner_report_v2"
    scan_id: str
    radio_id: str
    radio_serial: str
    configuration: ScannerConfigurationV2
    capture_elapsed_ms: float
    analysis_elapsed_ms: float
    results: tuple[ScanEdgeResult, ...]
    continuity_evidence: tuple[ScannerFrameContinuityEvidenceV1, ...]
    continuity_observable: Literal[True] = True
    retune_boundaries_are_discontinuous: Literal[True] = True
    candidate_only: Literal[True] = True
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _covers_plan(self) -> Self:
        _validate_continuity_report(
            self.configuration,
            self.results,
            self.continuity_evidence,
            continuity_observable=self.continuity_observable,
        )
        return self

    @property
    def active_edges(self) -> tuple[ScanTarget, ...]:
        return tuple(item.target for item in self.results if item.decision is ScanDecision.ACTIVE)


class ScannerCloseFailureEvidenceV1(ScannerModel):
    """Terminal cleanup failure retained without discarding captured targets."""

    schema_version: Literal[1] = 1
    stage: Literal["radio_close"] = "radio_close"
    exception_type: Annotated[str, Field(min_length=1, max_length=256)]
    message: Annotated[str, Field(min_length=1, max_length=2048)]


class ScannerReportV3(ScannerModel):
    """Additive failed-attempt report for zero evidence or terminal close failure."""

    schema_version: Literal[3] = 3
    kind: Literal["starlink_scanner_report_v3"] = "starlink_scanner_report_v3"
    scan_id: str
    radio_id: str
    radio_serial: str
    configuration: ScannerConfigurationV2
    capture_elapsed_ms: float
    analysis_elapsed_ms: float
    results: tuple[ScanEdgeResult, ...]
    continuity_evidence: tuple[ScannerFrameContinuityEvidenceV1, ...]
    continuity_observable: bool
    close_failure: ScannerCloseFailureEvidenceV1 | None = None
    retune_boundaries_are_discontinuous: Literal[True] = True
    candidate_only: Literal[True] = True
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _is_additive_failure(self) -> Self:
        _validate_continuity_report(
            self.configuration,
            self.results,
            self.continuity_evidence,
            continuity_observable=self.continuity_observable,
        )
        if self.continuity_observable and self.close_failure is None:
            raise ValueError("scanner report V3 requires a failed capture or radio close")
        return self

    @property
    def active_edges(self) -> tuple[ScanTarget, ...]:
        return tuple(item.target for item in self.results if item.decision is ScanDecision.ACTIVE)


class ScannerReportV4(ScannerModel):
    """Additive scanner report retaining metadata ABI 3 without relabeling it."""

    schema_version: Literal[4] = 4
    kind: Literal["starlink_scanner_report_v4"] = "starlink_scanner_report_v4"
    scan_id: str
    radio_id: str
    radio_serial: str
    configuration: ScannerConfigurationV2
    capture_elapsed_ms: float
    analysis_elapsed_ms: float
    results: tuple[ScanEdgeResult, ...]
    continuity_evidence: tuple[ScannerFrameContinuityEvidenceLike, ...]
    continuity_observable: bool
    close_failure: ScannerCloseFailureEvidenceV1 | None = None
    retune_boundaries_are_discontinuous: Literal[True] = True
    candidate_only: Literal[True] = True
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _covers_plan(self) -> Self:
        _validate_continuity_report(
            self.configuration,
            self.results,
            self.continuity_evidence,
            continuity_observable=self.continuity_observable,
        )
        if not any(
            isinstance(item, ScannerFrameContinuityEvidenceV2) for item in self.continuity_evidence
        ):
            raise ValueError("scanner report V4 requires metadata ABI 3 evidence")
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


class ScannerBurstReportV2(ScannerModel):
    """Ordered continuity-observable reports from one scanner burst."""

    schema_version: Literal[2] = 2
    kind: Literal["starlink_scanner_burst_report_v2"] = "starlink_scanner_burst_report_v2"
    burst_id: Annotated[str, Field(min_length=1, max_length=128)]
    reports: Annotated[tuple[ScannerReportV2, ...], Field(min_length=4, max_length=4)]

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


class ScannerBurstReportV3(ScannerModel):
    """Burst containing at least one additive failed-attempt report."""

    schema_version: Literal[3] = 3
    kind: Literal["starlink_scanner_burst_report_v3"] = "starlink_scanner_burst_report_v3"
    burst_id: Annotated[str, Field(min_length=1, max_length=128)]
    reports: Annotated[
        tuple[ScannerReportV2 | ScannerReportV3, ...],
        Field(min_length=4, max_length=4),
    ]

    @model_validator(mode="after")
    def _is_one_ordered_radio_burst(self) -> Self:
        if not any(isinstance(report, ScannerReportV3) for report in self.reports):
            raise ValueError("scanner burst V3 requires failed-attempt evidence")
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


class ScannerBurstReportV4(ScannerModel):
    """Additive burst containing at least one metadata ABI 3 report."""

    schema_version: Literal[4] = 4
    kind: Literal["starlink_scanner_burst_report_v4"] = "starlink_scanner_burst_report_v4"
    burst_id: Annotated[str, Field(min_length=1, max_length=128)]
    reports: Annotated[
        tuple[ScannerReportV2 | ScannerReportV3 | ScannerReportV4, ...],
        Field(min_length=4, max_length=4),
    ]

    @model_validator(mode="after")
    def _is_one_ordered_radio_burst(self) -> Self:
        if not any(isinstance(report, ScannerReportV4) for report in self.reports):
            raise ValueError("scanner burst V4 requires metadata ABI 3 evidence")
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


class ScannerIqFrameV2(ScannerIqFrameV1):
    """One reset-bounded, metadata-attested retuned scanner frame."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    metadata_abi_version: Annotated[int, Field(ge=1, le=2)]
    stream_id: Annotated[int, Field(gt=0)]
    stream_generation: Annotated[str, Field(min_length=1, max_length=128)]
    buffer_sequence: Annotated[int, Field(ge=0)]
    source_sequence: Annotated[int, Field(ge=0)]
    first_sample_sequence: Annotated[int, Field(ge=0)]
    last_sample_sequence_exclusive: Annotated[int, Field(gt=0)]
    device_sample_counter: Annotated[int, Field(ge=0)]
    device_sample_counter_end_exclusive: Annotated[int, Field(gt=0)]
    metadata_flags: Annotated[int, Field(ge=0)]
    sample_time_realtime_start_ns: Annotated[int, Field(ge=0)]
    sample_time_realtime_end_ns: Annotated[int, Field(gt=0)]
    sample_time_monotonic_start_ns: Annotated[int, Field(ge=0)]
    sample_time_monotonic_end_ns: Annotated[int, Field(gt=0)]
    sample_time_uncertainty_ns: Annotated[int, Field(ge=0)]
    kernel_buffers_requested: Annotated[int, Field(ge=2, le=64)]
    kernel_buffers_readback: Annotated[int, Field(ge=2, le=64)]
    reset_episode: Annotated[int, Field(gt=0)]
    missing_samples_before: Literal[0] = 0
    overflow_observed: Literal[False] = False
    continuity_observable: Literal[True] = True
    within_frame_continuity: Literal["proven_within_returned_buffer"] = (
        "proven_within_returned_buffer"
    )
    cross_frame_continuity: Literal["not_applicable_retune_boundary"] = (
        "not_applicable_retune_boundary"
    )

    @model_validator(mode="after")
    def _metadata_is_closed(self) -> Self:
        if self.stream_generation != str(self.stream_id):
            raise ValueError("scanner frame stream generation disagrees with raw stream ID")
        if self.source_sequence != self.buffer_sequence:
            raise ValueError("scanner frame source sequence disagrees with raw buffer sequence")
        if self.buffer_sequence != 0:
            raise ValueError("scanner frame first buffer/source sequence must be zero")
        if self.device_sample_counter != self.first_sample_sequence:
            raise ValueError("scanner frame device counter disagrees with raw first sample")
        if self.last_sample_sequence_exclusive != self.first_sample_sequence + self.sample_count:
            raise ValueError("scanner frame sample-counter range disagrees with its IQ length")
        if self.device_sample_counter_end_exclusive != self.last_sample_sequence_exclusive:
            raise ValueError("scanner frame canonical counter end disagrees with raw counter end")
        if self.sample_time_realtime_end_ns <= self.sample_time_realtime_start_ns:
            raise ValueError("scanner frame realtime sample interval does not increase")
        if self.sample_time_monotonic_end_ns <= self.sample_time_monotonic_start_ns:
            raise ValueError("scanner frame monotonic sample interval does not increase")
        if self.kernel_buffers_readback != self.kernel_buffers_requested:
            raise ValueError("scanner frame kernel-buffer readback disagrees with its request")
        if self.overflow_observed != metadata_reports_rx_overflow(self.metadata_flags):
            raise ValueError("scanner frame overflow disagrees with metadata flags bit 11")
        return self


class ScannerIqFrameV3(ScannerIqFrameV2):
    """Additive reset-bounded scanner frame carrying metadata ABI 3."""

    schema_version: Literal[3] = 3  # type: ignore[assignment]
    metadata_abi_version: Literal[3] = 3  # type: ignore[assignment]


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


class ScannerIqBundleManifestV2(ScannerIqBundleManifestV1):
    """Additive scanner bundle with sample-exact, retune-bounded evidence."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    configuration: ScannerConfigurationV2
    frames: tuple[ScannerIqFrameV2, ...]
    continuity_observable: Literal[True] = True
    cross_frame_continuity: Literal["not_applicable_retune_boundary"] = (
        "not_applicable_retune_boundary"
    )
    retune_boundary_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _continuity_evidence_is_closed(self) -> Self:
        if self.retune_boundary_count != max(0, len(self.frames) - 1):
            raise ValueError("scanner retune-boundary count disagrees with captured frames")
        episodes = tuple(frame.reset_episode for frame in self.frames)
        if episodes != tuple(sorted(set(episodes))):
            raise ValueError("scanner reset episodes must be unique and ordered")
        generations = tuple(frame.stream_generation for frame in self.frames)
        if len(generations) != len(set(generations)):
            raise ValueError("scanner stream generations must be unique across reset episodes")
        if any(
            frame.kernel_buffers_requested != self.configuration.kernel_buffers
            or frame.kernel_buffers_readback != self.configuration.kernel_buffers
            for frame in self.frames
        ):
            raise ValueError("scanner frame kernel buffers disagree with configuration")
        return self


class ScannerIqBundleManifestV3(ScannerIqBundleManifestV2):
    """Additive scanner IQ bundle retaining metadata ABI 3 frames."""

    schema_version: Literal[3] = 3  # type: ignore[assignment]
    frames: tuple[ScannerIqFrameV2 | ScannerIqFrameV3, ...]  # type: ignore[assignment]

    @model_validator(mode="after")
    def _contains_abi3_evidence(self) -> Self:
        if not any(isinstance(frame, ScannerIqFrameV3) for frame in self.frames):
            raise ValueError("scanner IQ bundle V3 requires metadata ABI 3 evidence")
        return self


ScannerConfigurationLike = ScannerConfiguration | ScannerConfigurationV2
ScannerReportLike = ScannerReport | ScannerReportV2 | ScannerReportV4
ScannerBurstReportLike = ScannerBurstReportV1 | ScannerBurstReportV2
ScannerCaptureReportLike = ScannerReportLike | ScannerReportV3
ScannerCaptureBurstReportLike = ScannerBurstReportLike | ScannerBurstReportV3 | ScannerBurstReportV4
ScannerIqBundleManifestLike = (
    ScannerIqBundleManifestV1 | ScannerIqBundleManifestV2 | ScannerIqBundleManifestV3
)
