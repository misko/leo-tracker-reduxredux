"""Versioned numerical products for segmented scanner analysis."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.digests import Sha256Digest
from leo.contracts.standard_pipeline import StandardNumericalWaterfallV2, StandardScientificStatus
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


class ScannerPilotDopplerConfigV1(ScannerModel):
    """Policy for one independently tuned scanner frame.

    Historical scanner IQ contains 80 ms per target, while the current capture
    policy uses 120 ms.  The guard prevents acquisition from consuming the
    preferred window and makes the 50 ms fallback explicit rather than silently
    shortening an analysis window.
    """

    schema_version: Literal[1] = 1
    model_version: Literal["scanner-piecewise-modulo-pi-pilot-doppler-v1"] = (
        "scanner-piecewise-modulo-pi-pilot-doppler-v1"
    )
    preferred_window_duration_s: Annotated[float, Field(gt=0, le=0.100)] = 0.075
    fallback_window_duration_s: Annotated[float, Field(gt=0, le=0.100)] = 0.050
    preferred_window_capture_guard_s: Annotated[float, Field(ge=0, le=0.100)] = 0.025
    confirmation_minimum_separation_s: Annotated[float, Field(gt=0, le=0.100)] = 0.020
    confirmation_cfo_gate_hz: Annotated[float, Field(gt=0, le=20_000)] = 8_000.0
    phase_innovation_gate_rad: Annotated[float, Field(gt=0, le=math.pi / 2)] = 1.2
    timing_innovation_gate_sigma: Annotated[float, Field(gt=0, le=1_000)] = 8.0
    maximum_segments_per_frame: Annotated[int, Field(ge=1, le=8)] = 2
    maximum_residual_cfo_hz: Annotated[float, Field(gt=0, le=10_000)] = 2_000.0
    minimum_supported_frame_fraction: Annotated[float, Field(gt=0, le=1)] = 0.75
    maximum_supported_frame_gap_s: Annotated[float, Field(gt=0, le=0.050)] = 0.0041
    minimum_median_coherence_margin: Annotated[float, Field(ge=0, le=1)] = 0.0
    maximum_frequency_line_rms_hz: Annotated[float, Field(gt=0)] = 75.0
    maximum_held_out_frequency_rms_hz: Annotated[float, Field(gt=0)] = 100.0
    maximum_local_kalman_rate_disagreement_hz_s: Annotated[float, Field(gt=0)] = 1_000.0

    @model_validator(mode="after")
    def _durations_are_coherent(self) -> Self:
        values = (
            self.preferred_window_duration_s,
            self.fallback_window_duration_s,
            self.preferred_window_capture_guard_s,
            self.confirmation_minimum_separation_s,
            self.confirmation_cfo_gate_hz,
            self.phase_innovation_gate_rad,
            self.timing_innovation_gate_sigma,
            self.maximum_residual_cfo_hz,
            self.minimum_supported_frame_fraction,
            self.maximum_supported_frame_gap_s,
            self.minimum_median_coherence_margin,
            self.maximum_frequency_line_rms_hz,
            self.maximum_held_out_frequency_rms_hz,
            self.maximum_local_kalman_rate_disagreement_hz_s,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("scanner pilot Doppler configuration must be finite")
        if self.fallback_window_duration_s > self.preferred_window_duration_s:
            raise ValueError("scanner pilot Doppler fallback exceeds preferred duration")
        return self


class ScannerPilotFrameStateV1(ScannerModel):
    """One measured 750 Hz pilot-frame state inside a retune-bounded window."""

    schema_version: Literal[1] = 1
    frame_index: Annotated[int, Field(ge=0, le=100)]
    time_since_retune_s: Annotated[float, Field(ge=0, le=5.0)]
    exact_coherence: Annotated[float, Field(ge=0, le=1)]
    control_coherence: Annotated[float, Field(ge=0, le=1)]
    coherence_margin: float
    measurement_supported: bool
    phase_innovation_modulo_pi_rad: float
    phase_ambiguity_bit: Literal[0, 1]
    absolute_cfo_measurement_hz: float
    tracked_absolute_cfo_hz: float
    tracked_doppler_rate_hz_s: float
    fractional_timing_measurement_samples: float
    tracked_fractional_timing_samples: float
    tracked_timing_rate_s_s: float
    phase_update_applied: bool
    frequency_update_applied: bool
    timing_update_applied: bool

    @model_validator(mode="after")
    def _measurements_are_finite(self) -> Self:
        values = (
            self.time_since_retune_s,
            self.exact_coherence,
            self.control_coherence,
            self.coherence_margin,
            self.phase_innovation_modulo_pi_rad,
            self.absolute_cfo_measurement_hz,
            self.tracked_absolute_cfo_hz,
            self.tracked_doppler_rate_hz_s,
            self.fractional_timing_measurement_samples,
            self.tracked_fractional_timing_samples,
            self.tracked_timing_rate_s_s,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("scanner pilot frame measurements must be finite")
        return self


class ScannerPilotDopplerSegmentV1(ScannerModel):
    """One acquisition-confirmed, retune-bounded local carrier segment."""

    schema_version: Literal[1] = 1
    segment_index: Annotated[int, Field(ge=0, le=64)]
    segment_id: Sha256Digest
    target_index: Annotated[int, Field(ge=0)]
    target: ScanTarget
    receiver_id: int
    source_probe_index: Annotated[int, Field(ge=0)]
    source_probe_start_ms: Annotated[int, Field(ge=0)]
    source_candidate_rank: Annotated[int, Field(ge=0)]
    confirmation_probe_index: Annotated[int, Field(ge=0)]
    confirmation_probe_start_ms: Annotated[int, Field(ge=0)]
    confirmation_candidate_rank: Annotated[int, Field(ge=0)]
    source_epoch_sample: Annotated[int, Field(ge=0)]
    initial_tracking_cfo_hz: float
    window_start_s: Annotated[float, Field(ge=0, le=5.0)]
    window_end_s: Annotated[float, Field(ge=0, le=5.0)]
    reference_time_since_retune_s: Annotated[float, Field(ge=0, le=5.0)]
    lattice_frame_count: Annotated[int, Field(ge=0, le=100)]
    returned_frame_count: Annotated[int, Field(ge=0, le=100)]
    supported_frame_count: Annotated[int, Field(ge=0, le=100)]
    phase_update_count: Annotated[int, Field(ge=0, le=100)]
    frequency_update_count: Annotated[int, Field(ge=0, le=100)]
    timing_update_count: Annotated[int, Field(ge=0, le=100)]
    supported_frame_fraction: Annotated[float, Field(ge=0, le=1)]
    maximum_supported_frame_gap_s: Annotated[float, Field(ge=0)] | None
    median_exact_coherence: Annotated[float, Field(ge=0, le=1)] | None
    median_control_coherence: Annotated[float, Field(ge=0, le=1)] | None
    median_coherence_margin: float | None
    phase_innovation_rms_rad: Annotated[float, Field(ge=0)] | None
    phase_ambiguity_transition_count: Annotated[int, Field(ge=0, le=100)]
    local_doppler_rate_hz_s: float | None
    local_doppler_rate_sigma_hz_s: Annotated[float, Field(ge=0)] | None
    kalman_doppler_rate_hz_s: float | None
    local_minus_kalman_rate_hz_s: float | None
    local_cfo_at_reference_hz: float | None
    frequency_line_rms_hz: Annotated[float, Field(ge=0)] | None
    held_out_frequency_rms_hz: Annotated[float, Field(ge=0)] | None
    final_fractional_timing_samples: float | None
    final_timing_rate_s_s: float | None
    phase_lock_qualified: bool
    qualified: bool
    qualification_failures: Annotated[tuple[str, ...], Field(max_length=16)]
    long_baseline_reference_rate_hz_s: None = None
    frames: Annotated[tuple[ScannerPilotFrameStateV1, ...], Field(max_length=100)]

    @model_validator(mode="after")
    def _segment_is_closed(self) -> Self:
        if not self.window_start_s < self.window_end_s:
            raise ValueError("scanner pilot window must have positive duration")
        if not 0.050 - 1e-12 <= self.window_end_s - self.window_start_s <= 0.100 + 1e-12:
            raise ValueError("scanner pilot window must remain within 50--100 ms")
        if not self.window_start_s <= self.reference_time_since_retune_s <= self.window_end_s:
            raise ValueError("scanner pilot reference lies outside its window")
        if self.confirmation_probe_start_ms - self.source_probe_start_ms < 0:
            raise ValueError("scanner pilot confirmation precedes its source")
        if not (
            self.supported_frame_count <= self.returned_frame_count <= self.lattice_frame_count
        ):
            raise ValueError("scanner pilot frame accounting is inconsistent")
        if any(
            value > self.returned_frame_count
            for value in (
                self.phase_update_count,
                self.frequency_update_count,
                self.timing_update_count,
            )
        ):
            raise ValueError("scanner pilot update count exceeds returned frames")
        if self.returned_frame_count != len(self.frames):
            raise ValueError("scanner pilot returned frame inventory is incomplete")
        if self.supported_frame_count != sum(item.measurement_supported for item in self.frames):
            raise ValueError("scanner pilot supported-frame inventory is inconsistent")
        if self.lattice_frame_count and not math.isclose(
            self.supported_frame_fraction,
            self.supported_frame_count / self.lattice_frame_count,
            rel_tol=0,
            abs_tol=1e-12,
        ):
            raise ValueError("scanner pilot supported-frame fraction is inconsistent")
        frame_indexes = tuple(item.frame_index for item in self.frames)
        if frame_indexes != tuple(sorted(set(frame_indexes))):
            raise ValueError("scanner pilot returned frame indexes must be unique and ordered")
        if any(
            not self.window_start_s <= item.time_since_retune_s <= self.window_end_s
            for item in self.frames
        ):
            raise ValueError("scanner pilot frame lies outside its local window")
        if (
            self.phase_update_count != sum(item.phase_update_applied for item in self.frames)
            or self.frequency_update_count
            != sum(item.frequency_update_applied for item in self.frames)
            or self.timing_update_count != sum(item.timing_update_applied for item in self.frames)
        ):
            raise ValueError("scanner pilot update inventory is inconsistent")
        if self.qualified != (not self.qualification_failures):
            raise ValueError("scanner pilot qualification flag and failures disagree")
        finite_optional = (
            self.initial_tracking_cfo_hz,
            self.window_start_s,
            self.window_end_s,
            self.reference_time_since_retune_s,
            self.maximum_supported_frame_gap_s,
            self.median_exact_coherence,
            self.median_control_coherence,
            self.median_coherence_margin,
            self.phase_innovation_rms_rad,
            self.local_doppler_rate_hz_s,
            self.local_doppler_rate_sigma_hz_s,
            self.kalman_doppler_rate_hz_s,
            self.local_minus_kalman_rate_hz_s,
            self.local_cfo_at_reference_hz,
            self.frequency_line_rms_hz,
            self.held_out_frequency_rms_hz,
            self.final_fractional_timing_samples,
            self.final_timing_rate_s_s,
        )
        if any(value is not None and not math.isfinite(value) for value in finite_optional):
            raise ValueError("scanner pilot segment measurements must be finite")
        return self


class ScannerPilotReceiverPairV1(ScannerModel):
    """Same-edge receiver comparison; absent unless both receivers confirmed."""

    schema_version: Literal[1] = 1
    target_index: Annotated[int, Field(ge=0)]
    target: ScanTarget
    receiver_ids: tuple[int, int]
    segment_ids: tuple[Sha256Digest, Sha256Digest]
    both_qualified: bool
    local_rate_difference_hz_s: float | None
    local_cfo_difference_hz: float | None
    reason: str

    @model_validator(mode="after")
    def _pair_is_finite(self) -> Self:
        if self.receiver_ids[0] == self.receiver_ids[1]:
            raise ValueError("scanner pilot receiver pair must contain distinct receivers")
        values = (self.local_rate_difference_hz_s, self.local_cfo_difference_hz)
        if any(value is not None and not math.isfinite(value) for value in values):
            raise ValueError("scanner pilot receiver-pair metrics must be finite")
        return self


class ScannerPilotDopplerSegmentsV1(ScannerModel):
    """Immutable scanner-native 50--75 ms pilot phase/rate product."""

    schema_version: Literal[1] = 1
    kind: Literal["scanner.pilot-doppler-segments"] = "scanner.pilot-doppler-segments"
    algorithm_version: Literal["scanner-pilot-doppler-segments-v1"] = (
        "scanner-pilot-doppler-segments-v1"
    )
    scan_id: str
    input_uri: str
    input_manifest_sha256: Sha256Digest
    scanner_metrics_sha256: Sha256Digest
    config: ScannerPilotDopplerConfigV1
    config_digest: Sha256Digest
    source_frame_count: Annotated[int, Field(ge=0)]
    confirmed_receiver_track_count: Annotated[int, Field(ge=0, le=64)]
    analyzed_segment_count: Annotated[int, Field(ge=0, le=64)]
    unavailable_segment_count: Annotated[int, Field(ge=0, le=64)]
    qualified_segment_count: Annotated[int, Field(ge=0, le=64)]
    preferred_window_segment_count: Annotated[int, Field(ge=0, le=64)]
    fallback_window_segment_count: Annotated[int, Field(ge=0, le=64)]
    segments: Annotated[tuple[ScannerPilotDopplerSegmentV1, ...], Field(max_length=64)]
    receiver_pairs: Annotated[tuple[ScannerPilotReceiverPairV1, ...], Field(max_length=32)]
    status: StandardScientificStatus
    reason: str
    carrier_phase_period_rad: float = math.pi
    retune_boundaries_are_discontinuous: Literal[True] = True
    frame_timing_is_receiver_relative: Literal[True] = True
    absolute_carrier_phase_resolved: Literal[False] = False
    long_baseline_trajectory_available: Literal[False] = False
    range_dynamics_claimed: Literal[False] = False
    candidate_only: Literal[True] = True
    known_pilots_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _product_is_closed(self) -> Self:
        from leo.contracts.digests import canonical_digest

        if self.carrier_phase_period_rad != math.pi:
            raise ValueError("scanner pilot phase must remain modulo pi")
        if self.config_digest != canonical_digest(self.config.model_dump(mode="json")):
            raise ValueError("scanner pilot configuration digest disagrees")
        if (
            self.confirmed_receiver_track_count
            != self.analyzed_segment_count + self.unavailable_segment_count
            or self.analyzed_segment_count != len(self.segments)
            or self.qualified_segment_count != sum(item.qualified for item in self.segments)
            or self.preferred_window_segment_count + self.fallback_window_segment_count
            != self.analyzed_segment_count
        ):
            raise ValueError("scanner pilot product accounting is inconsistent")
        if tuple(item.segment_index for item in self.segments) != tuple(range(len(self.segments))):
            raise ValueError("scanner pilot segment indexes must be contiguous")
        keys = tuple((item.target_index, item.receiver_id) for item in self.segments)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("scanner pilot target/receiver segments must be unique and ordered")
        if any(item.target_index >= self.source_frame_count for item in self.segments):
            raise ValueError("scanner pilot segment target lies outside its source inventory")
        segments_by_id = {item.segment_id: item for item in self.segments}
        pair_targets: set[int] = set()
        for pair in self.receiver_pairs:
            if pair.target_index in pair_targets:
                raise ValueError("scanner pilot receiver-pair targets must be unique")
            pair_targets.add(pair.target_index)
            if not set(pair.segment_ids).issubset(segments_by_id):
                raise ValueError("scanner pilot receiver pair references an unknown segment")
            paired_segments = tuple(segments_by_id[item] for item in pair.segment_ids)
            if any(
                segment.target_index != pair.target_index or segment.target != pair.target
                for segment in paired_segments
            ):
                raise ValueError("scanner pilot receiver pair references a different target")
            if tuple(segment.receiver_id for segment in paired_segments) != pair.receiver_ids:
                raise ValueError("scanner pilot receiver pair and segment receivers disagree")
        document = self.model_dump(mode="json")
        document.pop("content_digest")
        if self.content_digest != canonical_digest(document):
            raise ValueError("scanner pilot product content digest disagrees")
        return self


class ScannerAnalysisBundleManifestV2(ScannerModel):
    """Additive scanner bundle with the retune-bounded pilot product."""

    schema_version: Literal[2] = 2
    kind: Literal["starlink_scanner_analysis_bundle"] = "starlink_scanner_analysis_bundle"
    analysis_id: str
    scan_id: str
    input_uri: str
    input_manifest_sha256: Sha256Digest
    analyzer_id: Literal["standard-scan-analysis-pilot-v1"] = "standard-scan-analysis-pilot-v1"
    report_relative_path: Literal["scanner-report.v1.json"] = "scanner-report.v1.json"
    report_sha256: Sha256Digest
    metrics_relative_path: Literal["scanner-metrics.v1.json"] = "scanner-metrics.v1.json"
    metrics_sha256: Sha256Digest
    pilot_doppler_relative_path: Literal["scanner-pilot-doppler-segments.v1.json"] = (
        "scanner-pilot-doppler-segments.v1.json"
    )
    pilot_doppler_sha256: Sha256Digest
    waterfall_png_relative_path: Literal["presentation/scanner-waterfall.v1.png"] = (
        "presentation/scanner-waterfall.v1.png"
    )
    waterfall_png_sha256: Sha256Digest
    glrt64_png_relative_path: Literal["presentation/scanner-glrt64-response.v1.png"] = (
        "presentation/scanner-glrt64-response.v1.png"
    )
    glrt64_png_sha256: Sha256Digest
    pilot_doppler_png_relative_path: Literal[
        "presentation/scanner-pilot-doppler-segments.v1.png"
    ] = "presentation/scanner-pilot-doppler-segments.v1.png"
    pilot_doppler_png_sha256: Sha256Digest


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
