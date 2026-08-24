"""Stable, bounded presentation contracts consumed by HTTP and the browser."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
AbsolutePath = Annotated[str, StringConstraints(min_length=1, max_length=2048, pattern=r"^/")]
MappingStringAny = dict[str, Any]


class PresentationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class SourceTypeV1(StrEnum):
    LIVE = "LIVE"
    TEST = "TEST"
    IMPORT = "IMPORT"


class CaptureHealthV1(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class StorageStateV1(StrEnum):
    AVAILABLE = "available"
    PURGED = "purged"


class AnalysisStateV1(StrEnum):
    NO_RESULT = "no_result"
    QUEUED = "queued"
    RUNNING = "running"
    PARTIAL = "partial"
    FAILED = "failed"
    COMPLETE = "complete"


class ProductStatusV1(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    NO_RESULT = "no_result"


class DetectionStateV1(StrEnum):
    CANDIDATE = "candidate"
    NONE = "none"
    NOT_RUN = "not_run"
    FAILED = "failed"


class ComputeTierV1(StrEnum):
    NOT_RUN = "not_run"
    QUICK = "quick"
    STANDARD = "standard"
    RESEARCH = "research"


class ScientificConfidenceV1(StrEnum):
    UNASSESSED = "unassessed"
    CANDIDATE = "candidate"
    QUALIFIED = "qualified"
    REJECTED = "rejected"
    INSUFFICIENT = "insufficient"


class HoldV1(PresentationModel):
    held: bool
    reason: str | None = None

    @model_validator(mode="after")
    def _reason_matches_state(self) -> Self:
        if self.held != (self.reason is not None):
            raise ValueError("held state and hold reason must appear together")
        return self


class CurrentRunV1(PresentationModel):
    run_id: Identifier
    pipeline_release: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    state: AnalysisStateV1
    started_at: datetime
    finished_at: datetime | None = None
    is_current: Literal[True] = True


class CoverageV1(PresentationModel):
    analyzed_fraction: Annotated[float, Field(ge=0.0, le=1.0)]
    analyzed_seconds: Annotated[float, Field(ge=0.0)]
    dwell_seconds: Annotated[float, Field(ge=0.0)]
    description: Annotated[str, StringConstraints(min_length=1, max_length=512)]


class AnalysisSummaryV1(PresentationModel):
    state: AnalysisStateV1
    current_run: CurrentRunV1 | None
    coverage: CoverageV1 | None = None
    failure_reason: str | None = None
    no_result_reason: str | None = None
    product_count: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def _state_is_explicit(self) -> Self:
        if self.state is AnalysisStateV1.NO_RESULT:
            if self.no_result_reason is None:
                raise ValueError("no-result analysis requires a reason")
            if (
                self.current_run is not None
                and self.current_run.state is not AnalysisStateV1.NO_RESULT
            ):
                raise ValueError("no-result current run must carry the no-result state")
        elif self.no_result_reason is not None:
            raise ValueError("no-result reason belongs only to no-result state")
        if self.state is AnalysisStateV1.FAILED:
            if self.failure_reason is None:
                raise ValueError("failed analysis requires a failure reason")
        elif self.failure_reason is not None:
            raise ValueError("failure reason belongs only to failed state")
        if (
            self.state in {AnalysisStateV1.COMPLETE, AnalysisStateV1.PARTIAL}
            and self.current_run is None
        ):
            raise ValueError("complete or partial analysis requires a current run")
        return self


class CaptureProfileV1(PresentationModel):
    profile_id: Identifier
    name: str
    revision: Annotated[int, Field(ge=1)]
    sample_rate_hz: Annotated[float, Field(gt=0)]
    bandwidth_hz: Annotated[float, Field(gt=0)]
    dwell_seconds: Annotated[float, Field(gt=0)]
    center_frequency_hz: Annotated[float, Field(gt=0)]
    receiver_count_per_radio: Annotated[int, Field(ge=1, le=2)]


class RadioStreamV1(PresentationModel):
    radio_id: Identifier
    serial: str
    receiver_labels: tuple[str, ...]
    state: CaptureHealthV1
    captured_samples: Annotated[int, Field(ge=0)]
    sample_rate_hz: Annotated[float, Field(gt=0)]
    gain_db: tuple[float, ...]
    raw_path: AbsolutePath | None
    continuity_gaps: Annotated[int, Field(ge=0)]
    clipped_samples: Annotated[int, Field(ge=0)]
    enqueue_failures: Annotated[int, Field(ge=0)] = 0
    terminal_rejected_gaps: Annotated[int, Field(ge=0)] = 0
    terminal_rejected_missing_samples: Annotated[int, Field(ge=0)] = 0
    terminal_rejected_overflows: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def _receiver_shapes_match(self) -> Self:
        if not 1 <= len(self.receiver_labels) <= 2:
            raise ValueError("a radio stream requires one or two receiver labels")
        if len(self.gain_db) != len(self.receiver_labels):
            raise ValueError("gain values must match receiver labels")
        return self


class RadioSetupV2(PresentationModel):
    """Captured, per-radio acquisition setup shown without profile inference."""

    schema_version: Literal[2] = 2
    radio_id: Identifier
    radio_index: Annotated[int, Field(ge=0, le=1)]
    applied_if_center_frequency_hz: Annotated[int, Field(gt=0)] | None
    target_rf_center_frequency_hz: Annotated[int, Field(gt=0)] | None
    applied_bandwidth_hz: Annotated[int, Field(gt=0)] | None
    applied_sample_rate_hz: Annotated[int, Field(gt=0)] | None
    gain_mode: Literal["manual", "slow_attack", "fast_attack", "hybrid"] | None
    starlink_channel: Annotated[str | None, StringConstraints(min_length=1, max_length=64)] = None
    starlink_edge: Literal["lower", "upper"] | None = None
    firmware_version: Annotated[str | None, StringConstraints(min_length=1, max_length=128)] = None

    @model_validator(mode="after")
    def _starlink_intent_is_complete(self) -> Self:
        if (self.starlink_channel is None) != (self.starlink_edge is None):
            raise ValueError("Starlink channel and edge must appear together")
        return self


class RecordingRadioSetupV2(PresentationModel):
    schema_version: Literal[2] = 2
    session_id: Identifier
    radios: tuple[RadioSetupV2, ...]

    @model_validator(mode="after")
    def _radios_are_ordered(self) -> Self:
        if not 1 <= len(self.radios) <= 2:
            raise ValueError("recording setup requires one or two radios")
        if [radio.radio_index for radio in self.radios] != list(range(len(self.radios))):
            raise ValueError("recording setup radios must follow manifest order")
        if len({radio.radio_id for radio in self.radios}) != len(self.radios):
            raise ValueError("recording setup radio IDs must be unique")
        return self


class SynchronizationV1(PresentationModel):
    mode: Literal["none", "best_effort"]
    grade: Literal["not_requested", "observed", "degraded", "unavailable"]
    start_skew_ms: Annotated[float, Field(ge=0.0)] | None = None
    skew_uncertainty_ms: Annotated[float, Field(ge=0.0)] | None = None
    overlap_seconds: Annotated[float, Field(ge=0.0)] | None = None
    overlap_fraction: Annotated[float, Field(ge=0.0, le=1.0)] | None = None
    timing_basis: str
    phase_coherent: Literal[False] = False

    @model_validator(mode="after")
    def _claims_match_mode(self) -> Self:
        observations = (
            self.start_skew_ms,
            self.skew_uncertainty_ms,
            self.overlap_seconds,
            self.overlap_fraction,
        )
        if self.mode == "none" and any(value is not None for value in observations):
            raise ValueError("single-radio synchronization cannot claim overlap")
        if self.mode == "best_effort" and self.grade == "not_requested":
            raise ValueError("best-effort synchronization must be graded")
        return self


class RecordingPathsV1(PresentationModel):
    recording_root: AbsolutePath
    manifest_path: AbsolutePath
    analysis_root: AbsolutePath | None


class SeriesPointV1(PresentationModel):
    time_s: Annotated[float, Field(ge=0.0)]
    value: float


class SeriesV1(PresentationModel):
    series_id: Identifier
    label: str
    unit: str
    points: tuple[SeriesPointV1, ...]
    source_point_count: Annotated[int, Field(ge=0)]
    decimated: bool

    @model_validator(mode="after")
    def _count_is_honest(self) -> Self:
        if self.source_point_count < len(self.points):
            raise ValueError("source point count cannot be smaller than returned points")
        if self.decimated != (self.source_point_count > len(self.points)):
            raise ValueError("decimation flag disagrees with point counts")
        return self


class TimelineAvailabilityV1(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class CarrierTimingPointV1(PresentationModel):
    candidate_id: Identifier
    track_id: Identifier | None
    receiver_key: Identifier
    time_s: Annotated[float, Field(ge=0.0)]
    absolute_epoch_sample: Annotated[int, Field(ge=0)]
    observed_baseband_cfo_hz: float
    fitted_baseband_cfo_hz: float | None
    verify_minus_control_margin: float
    used_by_doppler_fit: bool


class CarrierTimingTimelineV1(PresentationModel):
    """Bounded observed carrier points and fit values at those same timestamps."""

    schema_version: Literal[1] = 1
    run_id: Identifier
    state: TimelineAvailabilityV1
    time_unit: Literal["s"] = "s"
    frequency_unit: Literal["Hz"] = "Hz"
    source_point_count: Annotated[int, Field(ge=0)]
    returned_point_count: Annotated[int, Field(ge=0, le=256)]
    truncated: bool
    points: tuple[CarrierTimingPointV1, ...]
    doppler_fit_available: bool
    reason: Annotated[str, StringConstraints(min_length=1, max_length=1024)]

    @model_validator(mode="after")
    def _counts_are_honest(self) -> Self:
        if self.returned_point_count != len(self.points):
            raise ValueError("returned carrier point count disagrees with payload")
        if self.source_point_count < self.returned_point_count:
            raise ValueError("source carrier point count is smaller than returned count")
        if self.truncated != (self.source_point_count > self.returned_point_count):
            raise ValueError("carrier truncation flag disagrees with point counts")
        if self.state is TimelineAvailabilityV1.UNAVAILABLE and self.points:
            raise ValueError("unavailable carrier timeline cannot contain points")
        return self


class QamTimelinePointV1(PresentationModel):
    receiver_key: Identifier
    time_s: Annotated[float, Field(ge=0.0)]
    candidate_epoch_sample: Annotated[int, Field(ge=0)]
    accuracy: Annotated[float, Field(ge=0.0, le=1.0)]
    rms_evm: Annotated[float, Field(ge=0.0)]
    frame_count: Annotated[int, Field(ge=0)]


class QamTimelineV1(PresentationModel):
    """Sparse candidate-window QAM aggregates; never an interpolated QAM curve."""

    schema_version: Literal[1] = 1
    run_id: Identifier
    state: TimelineAvailabilityV1
    time_unit: Literal["s"] = "s"
    temporal_resolution: Literal["aggregate_candidate_window"] = "aggregate_candidate_window"
    source_point_count: Annotated[int, Field(ge=0)]
    returned_point_count: Annotated[int, Field(ge=0, le=16)]
    truncated: bool
    points: tuple[QamTimelinePointV1, ...]
    continuous_time_series_available: Literal[False] = False
    reason: Annotated[str, StringConstraints(min_length=1, max_length=1024)]

    @model_validator(mode="after")
    def _counts_are_honest(self) -> Self:
        if self.returned_point_count != len(self.points):
            raise ValueError("returned QAM point count disagrees with payload")
        if self.source_point_count < self.returned_point_count:
            raise ValueError("source QAM point count is smaller than returned count")
        if self.truncated != (self.source_point_count > self.returned_point_count):
            raise ValueError("QAM truncation flag disagrees with point counts")
        if self.state is TimelineAvailabilityV1.UNAVAILABLE and self.points:
            raise ValueError("unavailable QAM timeline cannot contain points")
        return self


class AnalysisStageTimelineV1(PresentationModel):
    """Honest placeholder until persisted per-stage signal-time evidence exists."""

    schema_version: Literal[1] = 1
    run_id: Identifier
    state: Literal[TimelineAvailabilityV1.UNAVAILABLE] = TimelineAvailabilityV1.UNAVAILABLE
    stages: tuple[()] = ()
    reason: Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class CurrentRunStageStatusV1(PresentationModel):
    """Catalog-backed status for one stage/scope in the current run."""

    job_id: Annotated[int, Field(ge=1)]
    stage_key: Identifier
    scope_key: Identifier
    state: Literal["pending", "leased", "succeeded", "failed", "cancelled"]
    outcome: Literal["complete", "partial_coverage", "insufficient_data", "no_result"] | None


class CurrentRunStageMatrixV1(PresentationModel):
    """Bounded catalog job inventory; this does not claim signal-time coverage."""

    analysis_run_id: Identifier
    source_stage_count: Annotated[int, Field(ge=0)]
    returned_stage_count: Annotated[int, Field(ge=0, le=256)]
    truncated: bool
    stages: tuple[CurrentRunStageStatusV1, ...]

    @model_validator(mode="after")
    def _inventory_is_honest(self) -> Self:
        if self.returned_stage_count != len(self.stages):
            raise ValueError("returned stage count disagrees with stage inventory")
        if self.source_stage_count < self.returned_stage_count:
            raise ValueError("source stage count is smaller than returned stage count")
        if self.truncated != (self.source_stage_count > self.returned_stage_count):
            raise ValueError("stage truncation flag disagrees with stage counts")
        identities = [(item.stage_key, item.scope_key) for item in self.stages]
        if len(identities) != len(set(identities)):
            raise ValueError("stage inventory requires unique stage and scope pairs")
        return self


class QualitySummaryV1(PresentationModel):
    state: ProductStatusV1
    clipped_fraction: Annotated[float, Field(ge=0.0, le=1.0)] | None
    constant_iq_refills: Annotated[int, Field(ge=0)] | None
    continuity_gaps: Annotated[int, Field(ge=0)] | None
    note: str | None = None


class DetectionSummaryV1(PresentationModel):
    state: DetectionStateV1
    known_pilot_candidate: bool
    calibrated_detection: bool
    qin_score: float | None
    control_score: float | None
    reason: str


class CandidateCoverageV1(PresentationModel):
    scheduled_windows: Annotated[int, Field(ge=0)]
    complete_windows: Annotated[int, Field(ge=0)]
    searched_receiver_windows: Annotated[int, Field(ge=0)]
    searched_samples: Annotated[int, Field(ge=0)]
    searched_time_fraction: Annotated[float, Field(ge=0.0, le=1.0)]
    residual_cfo_min_hz: float
    residual_cfo_max_hz: float
    survey_config_digest: Digest

    @model_validator(mode="after")
    def _coverage_is_honest(self) -> Self:
        if self.complete_windows > self.scheduled_windows:
            raise ValueError("complete survey windows cannot exceed scheduled windows")
        if self.residual_cfo_min_hz >= self.residual_cfo_max_hz:
            raise ValueError("candidate coverage requires a non-empty CFO range")
        return self


class CandidateLineageV1(PresentationModel):
    candidate_id: Identifier
    receiver_key: Identifier
    time_s: Annotated[float, Field(ge=0.0)]
    absolute_epoch_sample: Annotated[int, Field(ge=0)]
    search_residual_cfo_hz: float
    baseband_cfo_hz: float
    receiver_tuned_center_hz: float
    tuned_signal_frequency_hz: float
    verify_score: Annotated[float, Field(ge=0.0, le=1.0)]
    control_score: Annotated[float, Field(ge=0.0, le=1.0)]
    margin: float
    rank_within_search: Annotated[int, Field(ge=0)]
    track_id: Identifier | None
    calibration_digest: Digest
    parent_survey_config_digest: Digest


class ControlSummaryV1(PresentationModel):
    state: ProductStatusV1
    thresholds_calibrated: bool
    specificity_claimed: bool
    passed_candidate_count: Annotated[int, Field(ge=0)]
    best_held_out_margin: float | None
    best_surrogate_margin: float | None
    rejection_reasons: tuple[str, ...]
    reason: str

    @model_validator(mode="after")
    def _specificity_is_explicit(self) -> Self:
        if self.specificity_claimed and not self.thresholds_calibrated:
            raise ValueError("specificity cannot be claimed by uncalibrated controls")
        return self


class WholeDwellSummaryV1(PresentationModel):
    analysis_run_id: Identifier | None
    compute_tier: ComputeTierV1
    confidence: ScientificConfidenceV1
    confidence_reason: str
    candidate_count: Annotated[int, Field(ge=0)]
    returned_candidate_count: Annotated[int, Field(ge=0, le=256)]
    candidate_lineage_truncated: bool
    candidate_coverage: CandidateCoverageV1 | None
    candidates: tuple[CandidateLineageV1, ...]
    controls: ControlSummaryV1

    @model_validator(mode="after")
    def _counts_are_honest(self) -> Self:
        if self.returned_candidate_count != len(self.candidates):
            raise ValueError("returned candidate count disagrees with candidate lineage")
        if self.candidate_count < self.returned_candidate_count:
            raise ValueError("candidate count is smaller than returned lineage")
        if self.candidate_lineage_truncated != (
            self.candidate_count > self.returned_candidate_count
        ):
            raise ValueError("candidate truncation flag disagrees with counts")
        if self.compute_tier is ComputeTierV1.NOT_RUN and self.analysis_run_id is not None:
            raise ValueError("not-run science cannot identify an analysis run")
        return self


class ReceiverQamSummaryV1(PresentationModel):
    receiver_key: Identifier
    candidate_epoch_sample: Annotated[int, Field(ge=0)]
    baseband_cfo_hz: float
    residual_cfo_refinement_hz: float
    receiver_tuned_center_hz: float
    tuned_signal_frequency_hz: float
    accuracy: Annotated[float, Field(ge=0.0, le=1.0)]
    rms_evm: Annotated[float, Field(ge=0.0)]
    frame_count: Annotated[int, Field(ge=0)]
    noise_variance: Annotated[float, Field(ge=0.0)]


class QamSummaryV1(PresentationModel):
    state: ProductStatusV1
    combined_accuracy: Annotated[float, Field(ge=0.0, le=1.0)] | None
    receiver_accuracy: tuple[Annotated[float, Field(ge=0.0, le=1.0)], ...]
    rms_evm: float | None
    frame_count: Annotated[int, Field(ge=0)]
    receiver_metrics: tuple[ReceiverQamSummaryV1, ...] = ()
    known_symbols_only: Literal[True] = True


class DopplerSummaryV1(PresentationModel):
    state: ProductStatusV1
    slope_hz_per_s: float | None
    baseband_cfo_at_reference_hz: float | None = None
    receiver_tuned_center_hz: float | None = None
    tuned_signal_frequency_at_reference_hz: float | None = None
    frequency_span_hz: float | None
    correlation: Annotated[float, Field(ge=-1.0, le=1.0)] | None
    residual_rms_hz: Annotated[float, Field(ge=0.0)] | None = None
    point_count: Annotated[int, Field(ge=0)] = 0
    motion_class: Literal["dynamic", "stationary_confounder", "indeterminate"] | None = None
    confidence: ScientificConfidenceV1 = ScientificConfidenceV1.UNASSESSED
    tle_candidate: str | None
    association_status: Literal["not_run", "candidate", "no_match", "unavailable", "failed"]


class StreamAnalysisV1(PresentationModel):
    """Bounded current-run evidence for one recording stream/radio.

    The legacy top-level scientific summaries remain the primary-stream view so
    presentation-v1 clients continue to work.  This additive collection is the
    authoritative view for multi-radio recordings.
    """

    scope_key: Identifier
    radio_id: Identifier
    receiver_labels: tuple[str, ...]
    is_primary: bool
    detection: DetectionSummaryV1
    whole_dwell: WholeDwellSummaryV1
    qam: QamSummaryV1
    doppler: DopplerSummaryV1


class ProvenanceV1(PresentationModel):
    analysis_run_id: Identifier | None = None
    pipeline_release: str | None
    generated_at: datetime | None
    config_digest: Digest | None
    recording_digest: Digest
    limitation_codes: tuple[str, ...]


class AnalysisProductV1(PresentationModel):
    schema_version: Literal[1] = 1
    product_id: Identifier
    session_id: Identifier
    analysis_run_id: Identifier
    kind: Literal[
        "quality",
        "power",
        "waterfall",
        "detection",
        "qam",
        "doppler",
        "controls",
        "overlays",
        "provenance",
    ]
    status: ProductStatusV1
    content_type: Literal["application/json"]
    artifact_path: AbsolutePath
    byte_count: Annotated[int, Field(gt=0, le=16 * 1024 * 1024)]
    sha256: Digest
    coverage: CoverageV1 | None
    summary: MappingStringAny


class RecordingSummaryV1(PresentationModel):
    schema_version: Literal[1] = 1
    session_id: Identifier
    title: str
    started_at: datetime
    duration_seconds: Annotated[float, Field(gt=0)]
    source_type: SourceTypeV1
    tags: tuple[str, ...]
    hold: HoldV1
    capture_health: CaptureHealthV1
    storage_state: StorageStateV1
    profile_name: str
    radio_count: Annotated[int, Field(ge=1, le=2)]
    analysis: AnalysisSummaryV1


class RecordingDetailV1(PresentationModel):
    schema_version: Literal[1] = 1
    session_id: Identifier
    title: str
    started_at: datetime
    duration_seconds: Annotated[float, Field(gt=0)]
    source_type: SourceTypeV1
    tags: tuple[str, ...]
    hold: HoldV1
    capture_health: CaptureHealthV1
    storage_state: StorageStateV1
    profile: CaptureProfileV1
    radios: tuple[RadioStreamV1, ...]
    synchronization: SynchronizationV1
    paths: RecordingPathsV1
    analysis: AnalysisSummaryV1
    quality: QualitySummaryV1
    power: tuple[SeriesV1, ...]
    detection: DetectionSummaryV1
    whole_dwell: WholeDwellSummaryV1
    qam: QamSummaryV1
    doppler: DopplerSummaryV1
    stream_analyses: tuple[StreamAnalysisV1, ...] = ()
    stage_matrix: CurrentRunStageMatrixV1 | None = None
    provenance: ProvenanceV1
    products: tuple[AnalysisProductV1, ...]

    @model_validator(mode="after")
    def _detail_is_consistent(self) -> Self:
        if len(self.radios) not in {1, 2}:
            raise ValueError("recording detail requires one or two radios")
        if self.storage_state is StorageStateV1.PURGED and any(
            radio.raw_path is not None for radio in self.radios
        ):
            raise ValueError("purged recordings cannot expose present raw paths")
        if self.source_type is SourceTypeV1.TEST and "TEST" not in self.tags:
            raise ValueError("TEST recordings require an explicit TEST tag")
        if self.stream_analyses:
            scope_keys = [item.scope_key for item in self.stream_analyses]
            if len(scope_keys) != len(set(scope_keys)):
                raise ValueError("stream analyses require unique scope keys")
            if sum(item.is_primary for item in self.stream_analyses) != 1:
                raise ValueError("stream analyses require exactly one primary scope")
            radio_ids = {radio.radio_id for radio in self.radios}
            if (
                len(self.stream_analyses) != len(self.radios)
                or {item.radio_id for item in self.stream_analyses} != radio_ids
            ):
                raise ValueError("stream analyses must cover every recording radio exactly once")
            primary = next(item for item in self.stream_analyses if item.is_primary)
            if (
                self.detection != primary.detection
                or self.whole_dwell != primary.whole_dwell
                or self.qam != primary.qam
                or self.doppler != primary.doppler
            ):
                raise ValueError("top-level scientific evidence must equal the primary stream view")
        current = self.analysis.current_run
        if current is not None:
            if (
                self.stage_matrix is not None
                and self.stage_matrix.analysis_run_id != current.run_id
            ):
                raise ValueError("stage inventory must identify the current run")
            run_ids = {
                *[product.analysis_run_id for product in self.products],
                *(
                    [self.whole_dwell.analysis_run_id]
                    if self.whole_dwell.analysis_run_id is not None
                    else []
                ),
                *(
                    [self.provenance.analysis_run_id]
                    if self.provenance.analysis_run_id is not None
                    else []
                ),
            }
            if run_ids and run_ids != {current.run_id}:
                raise ValueError("presented products and evidence must share the current run ID")
        elif (
            self.products
            or self.whole_dwell.analysis_run_id is not None
            or self.stage_matrix is not None
        ):
            raise ValueError("analysis evidence cannot exist without a current run")
        return self


class RecordingSearchResponseV1(PresentationModel):
    schema_version: Literal[1] = 1
    items: tuple[RecordingSummaryV1, ...]
    total: Annotated[int, Field(ge=0)]
    next_cursor: Annotated[int, Field(ge=0)] | None


class PlotPointV1(PresentationModel):
    x: float
    y: float
    value: float


class ProductContentV1(PresentationModel):
    schema_version: Literal[1] = 1
    product_id: Identifier
    analysis_run_id: Identifier
    kind: str
    source_point_count: Annotated[int, Field(ge=0)]
    returned_point_count: Annotated[int, Field(ge=0)]
    truncated: bool
    points: tuple[PlotPointV1, ...]
    metadata: MappingStringAny

    @model_validator(mode="after")
    def _content_counts_match(self) -> Self:
        if self.returned_point_count != len(self.points):
            raise ValueError("returned point count disagrees with payload")
        if self.source_point_count < self.returned_point_count:
            raise ValueError("source point count is smaller than returned count")
        if self.truncated != (self.source_point_count > self.returned_point_count):
            raise ValueError("truncated flag disagrees with point counts")
        return self


class StorageStatusV1(PresentationModel):
    total_bytes: Annotated[int, Field(gt=0)]
    used_bytes: Annotated[int, Field(ge=0)]
    used_fraction: Annotated[float, Field(ge=0.0, le=1.0)]
    retention_high_watermark: Annotated[float, Field(ge=0.0, le=1.0)]
    retention_low_watermark: Annotated[float, Field(ge=0.0, le=1.0)]
    admission_state: Literal["open", "warning", "stopped"]


class BacklogStatusV1(PresentationModel):
    queued: Annotated[int, Field(ge=0)]
    running: Annotated[int, Field(ge=0)]
    failed: Annotated[int, Field(ge=0)]
    oldest_queued_seconds: Annotated[float, Field(ge=0.0)] | None


class ActiveQueueJobV1(PresentationModel):
    schema_version: Literal[1] = 1
    job_id: Annotated[int, Field(gt=0)]
    run_id: Identifier
    session_id: Identifier
    pipeline_release_id: Identifier
    stage_key: Identifier
    description: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    state: Literal["pending", "leased"]
    resource_class: Literal["streaming", "cpu", "memory", "heavy"]
    scope_kind: Literal["receiver_path", "radio", "paired"] | None
    stream_id: Identifier | None
    radio_id: Identifier | None
    receiver_id: Annotated[int | None, Field(ge=0)]
    worker_id: Identifier | None
    created_at: datetime
    updated_at: datetime


class ActiveQueueV1(PresentationModel):
    schema_version: Literal[1] = 1
    generated_at: datetime
    items: tuple[ActiveQueueJobV1, ...] = Field(max_length=200)
    returned_count: Annotated[int, Field(ge=0, le=200)]
    truncated: bool


class AcquisitionQueueOperationV1(PresentationModel):
    schema_version: Literal[1] = 1
    operation_id: Annotated[int, Field(gt=0)]
    operation_key: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    kind: Literal[
        "scheduled_recording",
        "scanner_sweep",
        "operator_once",
        "qualification",
        "soak",
        "radio_probe",
    ]
    state: Literal["pending", "leased"]
    profile_name: Identifier | None
    radio_ids: tuple[Identifier, ...] = Field(max_length=2)
    worker_id: Identifier | None
    scheduled_for: datetime
    attempt_count: Annotated[int, Field(ge=0)]
    error: str | None


class AcquisitionQueueV1(PresentationModel):
    schema_version: Literal[1] = 1
    generated_at: datetime
    items: tuple[AcquisitionQueueOperationV1, ...] = Field(max_length=200)
    returned_count: Annotated[int, Field(ge=0, le=200)]
    truncated: bool


class SystemStatusV1(PresentationModel):
    schema_version: Literal[1] = 1
    generated_at: datetime
    storage: StorageStatusV1
    backlog: BacklogStatusV1
    api_mode: Literal["read_only"] = "read_only"


class QualificationDocumentRefV1(PresentationModel):
    schema_version: Literal[1] = 1
    logical_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    digest: Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]


class QualificationRecoveryV1(PresentationModel):
    schema_version: Literal[1] = 1
    successes: Annotated[int, Field(ge=0)]
    trials: Annotated[int, Field(ge=0)]
    point_estimate: Annotated[float | None, Field(ge=0, le=1)]
    confidence_level: Annotated[float, Field(gt=0.5, lt=1)]
    wilson_lower_bound: Annotated[float | None, Field(ge=0, le=1)]
    clopper_pearson_lower_bound: Annotated[float | None, Field(ge=0, le=1)]
    method: Literal["wilson-and-clopper-pearson-one-sided"] = "wilson-and-clopper-pearson-one-sided"


class QualificationQamV1(PresentationModel):
    schema_version: Literal[1] = 1
    reference_positive_count: Annotated[int, Field(ge=0)]
    native_recovery_count: Annotated[int, Field(ge=0)]
    mean_accuracy_difference: float | None
    accuracy_difference_lower_bound: float | None
    interval_method: str
    noninferiority_passed: bool | None


class QualificationStratumV1(PresentationModel):
    schema_version: Literal[1] = 1
    stratum_id: Identifier
    status: Literal["pass", "fail", "inconclusive", "insufficient"]
    reason: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    expected_session_count: Annotated[int, Field(ge=0)]
    observed_session_count: Annotated[int, Field(ge=0)]
    reference_positive_count: Annotated[int, Field(ge=0)]
    associated_reference_positive_count: Annotated[int, Field(ge=0)]
    recovery: QualificationRecoveryV1
    qam: QualificationQamV1


class QualificationCalibrationV1(PresentationModel):
    schema_version: Literal[1] = 1
    frequency_calibration_id: Annotated[int, Field(gt=0)]
    calibration_id: Identifier
    radio_id: Identifier
    radio_serial: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    physical_receiver_id: Identifier
    hardware_epoch_id: Identifier
    center_hz: float
    uncertainty_lower_hz: float
    uncertainty_upper_hz: float
    valid_from_utc_ns: Annotated[int, Field(ge=0)]
    valid_until_utc_ns: Annotated[int | None, Field(ge=0)]
    method: str
    evidence_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    evidence_digest: Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
    session_count: Annotated[int, Field(ge=1)]
    stream_count: Annotated[int, Field(ge=1)]


class QualificationCampaignListItemV1(PresentationModel):
    schema_version: Literal[1] = 1
    campaign_id: Identifier
    authority_status: Literal["authoritative_sealed"] = "authoritative_sealed"
    result_status: Literal["pass", "fail", "inconclusive"]
    reason: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    mathematical_eligible: bool
    production_accepted: bool
    expected_session_count: Literal[30] = 30
    observed_session_count: Annotated[int, Field(ge=0, le=30)]
    expected_stream_count: Literal[40] = 40
    observed_stream_count: Annotated[int, Field(ge=0, le=40)]
    sealed_at: datetime
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    attribution_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False


class QualificationCampaignListV1(PresentationModel):
    schema_version: Literal[1] = 1
    items: tuple[QualificationCampaignListItemV1, ...]
    total: Annotated[int, Field(ge=0)]
    next_cursor: Annotated[int, Field(ge=0)] | None


class QualificationCampaignDetailV1(QualificationCampaignListItemV1):
    pipeline_release_ids: tuple[Identifier, ...]
    capture: QualificationDocumentRefV1
    outer_seal: QualificationDocumentRefV1
    outer_sealed_utc_ns: Annotated[int, Field(ge=0)]
    current_release_evidence_digest: Annotated[
        str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")
    ]
    strata: tuple[QualificationStratumV1, ...]
    calibrations: tuple[QualificationCalibrationV1, ...]

    @model_validator(mode="after")
    def _bounded_authoritative_projection(self) -> Self:
        if len(self.strata) != 4:
            raise ValueError("qualification campaign requires four strata")
        if self.production_accepted != (self.result_status == "pass"):
            raise ValueError("production acceptance must equal authoritative PASS")
        return self
