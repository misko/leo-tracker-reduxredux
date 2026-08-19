"""Typed, bounded Standard-GLRT64 operator presentation contracts.

These contracts deliberately contain no catalog ORM, artifact path, or raw-IQ
types.  They are the only values the v2 API and browser need in order to show
the receiver-path, radio, and paired hierarchy truthfully.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from leo.pipeline.scopes import ScopeIdentityV1, ScopeKind

Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=192, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
GitSha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]


def _candidate_only_language(value: str) -> str:
    normalized = " ".join(value.casefold().replace("-", " ").split())
    prohibited = (
        "confirmed starlink",
        "starlink detected",
        "detected starlink",
        "payload decoded",
        "payload recovered",
        "specificity confirmed",
        "specificity proven",
        "qualified detection",
        "independent trials",
        "independent trial",
        "statistically independent",
        "production accepted",
    )
    if any(claim in normalized for claim in prohibited):
        raise ValueError("Standard presentation language must remain candidate-only")
    tokens = {token.strip(".,:;!?()[]{}") for token in normalized.split()}
    if {"detected", "detection", "detections"} & tokens:
        raise ValueError(
            "Standard presentation must use candidate-evidence vocabulary, not detection claims"
        )
    if "independent" in tokens and any(token.startswith("trial") for token in tokens):
        raise ValueError("Standard presentation cannot claim independent trials")
    if "starlink" in normalized and not any(
        qualifier in normalized
        for qualifier in (
            "no starlink attribution",
            "starlink attribution unavailable",
            "not starlink specific",
            "no starlink specificity",
        )
    ):
        raise ValueError("Standard presentation cannot make a Starlink-specific claim")
    if "payload" in normalized and not any(
        qualifier in normalized
        for qualifier in (
            "no payload recovery",
            "payload recovery unavailable",
            "without payload",
        )
    ):
        raise ValueError("Standard presentation cannot claim payload evidence")
    if "specificity" in normalized and not any(
        qualifier in normalized
        for qualifier in ("no specificity", "specificity unavailable", "not specific")
    ):
        raise ValueError("Standard presentation cannot claim specificity")
    if "phase coherent" in normalized and not any(
        qualifier in normalized
        for qualifier in ("not phase coherent", "no phase coherence", "phase coherence unavailable")
    ):
        raise ValueError("Standard presentation cannot claim phase coherence")
    return value


CandidateOnlyText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=1024),
    AfterValidator(_candidate_only_language),
]
CandidateOnlyLabel = Annotated[
    str,
    StringConstraints(min_length=1, max_length=160),
    AfterValidator(_candidate_only_language),
]
StandardUnitV2 = Literal[
    "s",
    "Hz",
    "dB",
    "dBFS",
    "fraction",
    "response",
    "accuracy",
    "EVM",
    "mixed",
]


class StandardPresentationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class StandardSubjectKindV2(StrEnum):
    RECEIVER_PATH = "receiver_path"
    RADIO = "radio"
    PAIRED = "paired"


class StandardSubjectStateV2(StrEnum):
    NOT_ANALYZED = "not_analyzed"
    QUEUED = "queued"
    RUNNING = "running"
    BLOCKED = "blocked"
    PARTIAL = "partial"
    COMPLETE = "complete"
    CURRENT = "current"
    STALE = "stale"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class StandardSourceTypeV2(StrEnum):
    LIVE = "LIVE"
    IMPORT = "IMPORT"
    TEST = "TEST"


class StandardStaleReasonCodeV2(StrEnum):
    DESIRED_RELEASE_CHANGED = "desired_release_changed"
    INPUT_MANIFEST_CHANGED = "input_manifest_changed"
    CALIBRATION_APPLICABILITY_CHANGED = "calibration_applicability_changed"
    UPSTREAM_PRODUCT_CHANGED = "upstream_product_changed"
    STAGE_IMPLEMENTATION_CHANGED = "stage_implementation_changed"
    STAGE_CONFIGURATION_CHANGED = "stage_configuration_changed"
    CHILD_REPORT_NEWER = "child_report_newer"
    PRODUCT_UNAVAILABLE = "product_unavailable"


class StandardComputationDispositionV2(StrEnum):
    COMPUTED = "computed"
    REUSED = "reused"
    RECOMPUTE = "recompute"
    BLOCKED = "blocked"
    NOT_REQUIRED = "not_required"


class StandardViewKindV2(StrEnum):
    QUALITY = "quality"
    POWER = "power"
    WATERFALL = "waterfall"
    GLRT64 = "glrt64"
    CFO_TRAJECTORY = "cfo_trajectory"
    QAM = "qam"


class StandardViewStateV2(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class StandardPipelineReleaseV2(StandardPresentationModel):
    """Human metadata plus the exact source authority used by workers."""

    authoritative_pipeline_release_id: GitSha
    source_revision: GitSha
    family: Literal["standard-glrt64-v2"] = "standard-glrt64-v2"
    display_version: Annotated[
        str, StringConstraints(pattern=r"^2\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")
    ]
    graph_digest: Digest
    configuration_digest: Digest
    environment_digest: Digest

    @model_validator(mode="after")
    def _authority_is_exact_source(self) -> Self:
        if self.authoritative_pipeline_release_id != self.source_revision:
            raise ValueError("authoritative pipeline release must equal the exact source revision")
        return self

    @property
    def display_label(self) -> str:
        return f"{self.family} {self.display_version}"


class StandardEligibilityV2(StandardPresentationModel):
    source_type: StandardSourceTypeV2
    capture_committed: bool
    capture_healthy: bool
    automatic_eligible: bool
    explicit_eligible: bool
    promotion_allowed: bool
    evidence_only: bool
    exclusion_tags: tuple[str, ...] = Field(default=(), max_length=3)
    reason: CandidateOnlyText

    @model_validator(mode="after")
    def _source_truth_is_preserved(self) -> Self:
        if (not self.capture_committed or not self.capture_healthy) and (
            self.automatic_eligible or self.explicit_eligible or self.promotion_allowed
        ):
            raise ValueError("uncommitted or unhealthy captures must fail closed")
        if self.source_type is StandardSourceTypeV2.TEST and (
            self.automatic_eligible or self.promotion_allowed or not self.evidence_only
        ):
            raise ValueError("TEST analysis must remain explicit evidence-only and non-promotable")
        if self.exclusion_tags and (self.automatic_eligible or self.promotion_allowed):
            raise ValueError("excluded qualification lanes cannot be automatic or promotable")
        if self.evidence_only and self.promotion_allowed:
            raise ValueError(
                "evidence-only analysis cannot be promoted as ordinary current analysis"
            )
        return self


class StandardStateReasonV2(StandardPresentationModel):
    code: StandardStaleReasonCodeV2 | None = None
    message: CandidateOnlyText
    affected_stage_keys: tuple[Identifier, ...] = Field(default=(), max_length=32)
    affected_subject_ids: tuple[Identifier, ...] = Field(default=(), max_length=32)


class StandardReuseSummaryV2(StandardPresentationModel):
    computed_stage_count: Annotated[int, Field(ge=0)]
    reused_stage_count: Annotated[int, Field(ge=0)]
    recompute_stage_count: Annotated[int, Field(ge=0)]
    blocked_stage_count: Annotated[int, Field(ge=0)] = 0
    reused_from_run_ids: tuple[Identifier, ...] = Field(default=(), max_length=64)
    reason: CandidateOnlyText


class StandardReceiverPathRefV2(StandardPresentationModel):
    path_id: Identifier
    radio_id: Identifier
    radio_label: CandidateOnlyLabel
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    receiver_label: CandidateOnlyLabel
    scope: ScopeIdentityV1
    scope_digest: Digest

    @model_validator(mode="after")
    def _scope_matches_path(self) -> Self:
        if self.scope.kind is not ScopeKind.RECEIVER_PATH:
            raise ValueError("receiver path presentation requires a receiver-path scope")
        if self.scope.receiver_id != self.receiver_id:
            raise ValueError("receiver path scope receiver does not match presentation path")
        if self.scope.canonical_digest.removeprefix("sha256:") != self.scope_digest:
            raise ValueError("receiver path scope digest does not match its canonical scope")
        return self


class StandardSubjectSummaryV2(StandardPresentationModel):
    subject_id: Identifier
    session_id: Identifier
    subject_kind: StandardSubjectKindV2
    label: CandidateOnlyLabel
    derived: bool
    receiver_paths: tuple[StandardReceiverPathRefV2, ...] = Field(max_length=4)
    expected_path_count: Annotated[int, Field(ge=1, le=4)]
    completed_path_count: Annotated[int, Field(ge=0, le=4)]
    child_subject_ids: tuple[Identifier, ...] = Field(max_length=4)
    state: StandardSubjectStateV2
    ordinary_current: bool
    state_reasons: tuple[StandardStateReasonV2, ...] = Field(max_length=16)
    pipeline_release: StandardPipelineReleaseV2 | None
    desired_pipeline_release_id: GitSha
    reuse: StandardReuseSummaryV2
    eligibility: StandardEligibilityV2
    evidence_label: Literal["candidate evidence only"] = "candidate evidence only"

    @model_validator(mode="after")
    def _subject_shape_is_explicit(self) -> Self:
        path_count = len(self.receiver_paths)
        path_ids = tuple(path.path_id for path in self.receiver_paths)
        scope_digests = tuple(path.scope_digest for path in self.receiver_paths)
        if self.expected_path_count != path_count:
            raise ValueError("expected path count must equal the declared receiver-path inventory")
        if self.completed_path_count > self.expected_path_count:
            raise ValueError("completed path count cannot exceed expected paths")
        if len(path_ids) != len(set(path_ids)) or len(scope_digests) != len(set(scope_digests)):
            raise ValueError("subject receiver-path identities must be distinct")
        if len(self.child_subject_ids) != len(set(self.child_subject_ids)):
            raise ValueError("subject child identities must be distinct")
        if self.subject_kind is StandardSubjectKindV2.RECEIVER_PATH:
            if path_count != 1 or self.child_subject_ids or self.derived:
                raise ValueError("receiver-path subjects require one path and no derived children")
        elif self.subject_kind is StandardSubjectKindV2.RADIO:
            if not 1 <= path_count <= 2 or len(self.child_subject_ids) != path_count:
                raise ValueError("radio subjects require one or two receiver-path children")
            if len({path.radio_id for path in self.receiver_paths}) != 1:
                raise ValueError("radio subjects require paths from exactly one radio")
            if not self.derived:
                raise ValueError("radio reports are derived from receiver-path reports")
        else:
            radio_count = len({path.radio_id for path in self.receiver_paths})
            if radio_count != 2 or not 2 <= path_count <= 4 or len(self.child_subject_ids) != 2:
                raise ValueError("paired subjects require exactly two radio children")
            if not self.derived:
                raise ValueError("paired reports are derived evidence")
        if self.state is StandardSubjectStateV2.STALE and (
            not self.state_reasons or not any(reason.code for reason in self.state_reasons)
        ):
            raise ValueError("stale subjects require a machine-readable stale reason")
        if self.state is StandardSubjectStateV2.CURRENT and self.pipeline_release is None:
            raise ValueError("current subjects require exact pipeline release provenance")
        if self.eligibility.evidence_only and self.state is StandardSubjectStateV2.CURRENT:
            raise ValueError("evidence-only subjects cannot state current")
        if self.ordinary_current and (
            self.state is not StandardSubjectStateV2.CURRENT
            or not self.eligibility.promotion_allowed
            or self.eligibility.evidence_only
            or self.completed_path_count != self.expected_path_count
        ):
            raise ValueError(
                "ordinary current requires complete expected paths and current, promotable, "
                "non-TEST evidence"
            )
        if (
            self.state is StandardSubjectStateV2.CURRENT
            and self.eligibility.promotion_allowed
            and not self.ordinary_current
        ):
            raise ValueError("promotable current subject must declare ordinary current authority")
        return self


class StandardSubjectHierarchyV2(StandardPresentationModel):
    schema_version: Literal[2] = 2
    session_id: Identifier
    source_type: StandardSourceTypeV2
    eligibility: StandardEligibilityV2
    generated_at: datetime
    rows: tuple[StandardSubjectSummaryV2, ...] = Field(max_length=3)

    @model_validator(mode="after")
    def _top_level_rows_are_truthful(self) -> Self:
        if self.source_type is not self.eligibility.source_type:
            raise ValueError("hierarchy source type must match eligibility source type")
        if any(row.session_id != self.session_id for row in self.rows):
            raise ValueError("all subject rows must belong to the requested session")
        kinds = tuple(row.subject_kind for row in self.rows)
        subject_ids = tuple(row.subject_id for row in self.rows)
        if len(subject_ids) != len(set(subject_ids)):
            raise ValueError("top-level Standard subject identities must be distinct")
        if any(row.eligibility != self.eligibility for row in self.rows):
            raise ValueError("subject eligibility must equal the hierarchy eligibility")
        if StandardSubjectKindV2.RECEIVER_PATH in kinds:
            raise ValueError("receiver paths are expansions, not top-level rows")
        radio_rows = tuple(
            row for row in self.rows if row.subject_kind is StandardSubjectKindV2.RADIO
        )
        paired_rows = tuple(
            row for row in self.rows if row.subject_kind is StandardSubjectKindV2.PAIRED
        )
        if len(radio_rows) == 2:
            if len(paired_rows) != 1 or len(self.rows) != 3:
                raise ValueError("dual-radio captures require exactly pair, Radio0, Radio1 rows")
            if self.rows[0].subject_kind is not StandardSubjectKindV2.PAIRED:
                raise ValueError("paired row must be displayed before its two radio rows")
            paired = paired_rows[0]
            radio_ids = tuple(row.subject_id for row in radio_rows)
            if paired.child_subject_ids != radio_ids:
                raise ValueError("paired children must exactly equal the ordered radio rows")
            radio_path_ids = [path.path_id for radio in radio_rows for path in radio.receiver_paths]
            if len(radio_path_ids) != len(set(radio_path_ids)):
                raise ValueError("radio rows must have disjoint receiver-path membership")
            if tuple(path.path_id for path in paired.receiver_paths) != tuple(radio_path_ids):
                raise ValueError("paired path inventory must equal the ordered radio path union")
        elif len(radio_rows) == 1:
            if paired_rows or len(self.rows) != 1:
                raise ValueError("single-radio captures cannot manufacture a paired row")
        else:
            raise ValueError("a hierarchy requires one or two radio rows")
        return self


class StandardTimeDomainV2(StandardPresentationModel):
    absolute_start_utc: datetime
    absolute_end_utc: datetime
    elapsed_start_s: Annotated[float, Field(ge=0.0)] = 0.0
    elapsed_end_s: Annotated[float, Field(gt=0.0)]
    time_unit: Literal["s"] = "s"
    timing_uncertainty_s: Annotated[float, Field(ge=0.0)]

    @model_validator(mode="after")
    def _bounds_match(self) -> Self:
        if self.absolute_end_utc <= self.absolute_start_utc:
            raise ValueError("time domain requires increasing absolute bounds")
        if self.elapsed_end_s <= self.elapsed_start_s:
            raise ValueError("time domain requires increasing elapsed bounds")
        if self.absolute_start_utc.utcoffset() is None or self.absolute_end_utc.utcoffset() is None:
            raise ValueError("time-domain absolute bounds must be timezone aware")
        absolute_duration_s = (self.absolute_end_utc - self.absolute_start_utc).total_seconds()
        elapsed_duration_s = self.elapsed_end_s - self.elapsed_start_s
        if abs(absolute_duration_s - elapsed_duration_s) > self.timing_uncertainty_s:
            raise ValueError(
                "absolute and elapsed time-domain durations disagree beyond uncertainty"
            )
        return self


class StandardStageStatusV2(StandardPresentationModel):
    stage_key: Identifier
    subject_id: Identifier
    disposition: StandardComputationDispositionV2
    runtime_seconds: Annotated[float, Field(ge=0.0)] | None = None
    output_digest: Digest | None = None
    reused_from_run_id: Identifier | None = None
    reason: CandidateOnlyText

    @model_validator(mode="after")
    def _reuse_lineage_is_explicit(self) -> Self:
        if self.disposition is StandardComputationDispositionV2.REUSED:
            if self.reused_from_run_id is None or self.output_digest is None:
                raise ValueError("reused stages require their source run and exact output digest")
        elif self.reused_from_run_id is not None:
            raise ValueError("reuse provenance belongs only to reused stages")
        return self


class StandardViewDescriptorV2(StandardPresentationModel):
    view_kind: StandardViewKindV2
    state: StandardViewStateV2
    href: Annotated[
        str,
        StringConstraints(min_length=9, max_length=512, pattern=r"^/api/v2/"),
    ]
    source_point_count: Annotated[int, Field(ge=0)]
    reason: CandidateOnlyText


class StandardPathEvidenceV2(StandardPresentationModel):
    receiver_path: StandardReceiverPathRefV2
    coverage_fraction: Annotated[float, Field(ge=0.0, le=1.0)]
    analyzed_seconds: Annotated[float, Field(ge=0.0)]
    declared_seconds: Annotated[float, Field(gt=0.0)]
    quality_state: Literal["complete", "partial", "failed", "unavailable"]
    clipped_fraction: Annotated[float, Field(ge=0.0, le=1.0)] | None
    continuity_gap_count: Annotated[int, Field(ge=0)] | None
    calibration_state: Literal["applicable", "unavailable", "not_required"]
    calibration_id: Identifier | None
    calibration_digest: Digest | None
    frequency_uncertainty_hz: Annotated[float, Field(ge=0.0)] | None
    reason: CandidateOnlyText

    @model_validator(mode="after")
    def _coverage_and_calibration_are_honest(self) -> Self:
        expected = min(1.0, self.analyzed_seconds / self.declared_seconds)
        if abs(self.coverage_fraction - expected) > 1e-12:
            raise ValueError("path coverage disagrees with analyzed and declared seconds")
        calibration_fields = (
            self.calibration_id,
            self.calibration_digest,
            self.frequency_uncertainty_hz,
        )
        if self.calibration_state == "applicable" and not all(
            item is not None for item in calibration_fields
        ):
            raise ValueError("applicable calibration requires ID, digest, and uncertainty")
        if self.calibration_state != "applicable" and any(
            item is not None for item in calibration_fields
        ):
            raise ValueError("unavailable/not-required calibration cannot carry authority")
        return self


class StandardTrajectoryRowV2(StandardPresentationModel):
    trajectory_id: Identifier
    receiver_path_id: Identifier
    algorithm: Identifier
    degree: Literal[1, 2, 3]
    reference_time_s: Annotated[float, Field(ge=0.0)]
    coefficients_hz: tuple[float, ...]
    support_count: Annotated[int, Field(ge=0)]
    residual_rms_hz: Annotated[float, Field(ge=0.0)]
    bic: float
    selected_for_correction: bool
    corrected_glrt64_gain: float | None
    status: Literal["selected", "retained", "rejected"]
    rejection_reason: CandidateOnlyText | None = None

    @model_validator(mode="after")
    def _polynomial_is_reconstructable(self) -> Self:
        if len(self.coefficients_hz) != self.degree + 1:
            raise ValueError("polynomial coefficient count must equal degree plus one")
        if self.status == "rejected" and self.rejection_reason is None:
            raise ValueError("rejected trajectories require a reason")
        if self.status != "rejected" and self.rejection_reason is not None:
            raise ValueError("rejection reason belongs only to rejected trajectories")
        if self.selected_for_correction != (self.status == "selected"):
            raise ValueError("selected-for-correction must match selected status")
        return self


class StandardSubjectDetailV2(StandardPresentationModel):
    schema_version: Literal[2] = 2
    subject: StandardSubjectSummaryV2
    time_domain: StandardTimeDomainV2
    receiver_path_expansions: tuple[StandardSubjectSummaryV2, ...] = Field(max_length=4)
    receiver_path_evidence: tuple[StandardPathEvidenceV2, ...] = Field(max_length=4)
    stage_source_count: Annotated[int, Field(ge=0)]
    stages: tuple[StandardStageStatusV2, ...] = Field(max_length=256)
    stages_truncated: bool
    trajectory_source_count: Annotated[int, Field(ge=0)]
    trajectories: tuple[StandardTrajectoryRowV2, ...] = Field(max_length=256)
    trajectories_truncated: bool
    views: tuple[StandardViewDescriptorV2, ...] = Field(max_length=6)
    limitations: tuple[CandidateOnlyText, ...] = Field(max_length=16)

    @model_validator(mode="after")
    def _detail_is_bounded_and_complete(self) -> Self:
        if len(self.stages) > 256 or len(self.trajectories) > 256:
            raise ValueError("detail tables exceed their presentation bound")
        if self.stage_source_count < len(self.stages):
            raise ValueError("stage source count cannot be smaller than returned rows")
        if self.trajectory_source_count < len(self.trajectories):
            raise ValueError("trajectory source count cannot be smaller than returned rows")
        if self.stages_truncated != (self.stage_source_count > len(self.stages)):
            raise ValueError("stage truncation flag disagrees with counts")
        if self.trajectories_truncated != (self.trajectory_source_count > len(self.trajectories)):
            raise ValueError("trajectory truncation flag disagrees with counts")
        required = set(StandardViewKindV2)
        if {item.view_kind for item in self.views} != required or len(self.views) != len(required):
            raise ValueError("detail must describe every required Standard view exactly once")
        if any(
            item.subject_kind is not StandardSubjectKindV2.RECEIVER_PATH
            for item in self.receiver_path_expansions
        ):
            raise ValueError("subject expansions may contain receiver paths only")
        expansion_ids = tuple(item.subject_id for item in self.receiver_path_expansions)
        expansion_path_ids = tuple(
            item.receiver_paths[0].path_id for item in self.receiver_path_expansions
        )
        if len(expansion_ids) != len(set(expansion_ids)):
            raise ValueError("receiver-path expansion identities must be distinct")
        if (
            self.subject.subject_kind is StandardSubjectKindV2.RADIO
            and self.subject.child_subject_ids != expansion_ids
        ):
            raise ValueError(
                "radio child subjects must exactly equal ordered receiver-path expansions"
            )
        if expansion_path_ids != tuple(path.path_id for path in self.subject.receiver_paths):
            raise ValueError("receiver-path expansions must equal the ordered subject paths")
        subject_paths = {item.path_id for item in self.subject.receiver_paths}
        evidence_paths = {item.receiver_path.path_id for item in self.receiver_path_evidence}
        if evidence_paths != subject_paths or len(evidence_paths) != len(
            self.receiver_path_evidence
        ):
            raise ValueError("path evidence must cover each subject receiver path exactly once")
        return self


class StandardSeriesPointV2(StandardPresentationModel):
    time_s: Annotated[float, Field(ge=0.0)]
    value: float


class StandardMetricSeriesV2(StandardPresentationModel):
    series_id: Identifier
    receiver_path_id: Identifier
    label: CandidateOnlyLabel
    unit: StandardUnitV2
    source_point_count: Annotated[int, Field(ge=0)]
    points: tuple[StandardSeriesPointV2, ...] = Field(max_length=2048)
    truncated: bool
    source_min: float | None
    source_max: float | None

    @model_validator(mode="after")
    def _series_is_bounded(self) -> Self:
        if len(self.points) > 2048:
            raise ValueError("metric series exceeds 2,048 presentation points")
        if self.source_point_count < len(self.points):
            raise ValueError("series source count is smaller than returned points")
        if self.truncated != (self.source_point_count > len(self.points)):
            raise ValueError("series truncation flag disagrees with counts")
        if (self.source_min is None) != (self.source_max is None):
            raise ValueError("series source extrema must appear together")
        if self.points and self.source_min is None:
            raise ValueError("non-empty series require full-domain source extrema")
        if (
            self.source_min is not None
            and self.source_max is not None
            and self.source_min > self.source_max
        ):
            raise ValueError("series source extrema are reversed")
        if self.points and (
            min(point.value for point in self.points) != self.source_min
            or max(point.value for point in self.points) != self.source_max
        ):
            raise ValueError("metric series must retain exact full-source extrema")
        return self


class StandardWaterfallCellV2(StandardPresentationModel):
    receiver_path_id: Identifier
    time_s: Annotated[float, Field(ge=0.0)]
    frequency_hz: float
    power_db: float


class StandardCfoObservationV2(StandardPresentationModel):
    observation_id: Identifier
    receiver_path_id: Identifier
    algorithm: Identifier
    time_s: Annotated[float, Field(ge=0.0)]
    baseband_cfo_hz: float
    glrt64_response: float
    used_by_trajectory_ids: tuple[Identifier, ...] = Field(default=(), max_length=16)


class StandardTrajectoryCurveV2(StandardPresentationModel):
    trajectory_id: Identifier
    receiver_path_id: Identifier
    degree: Literal[1, 2, 3]
    selected_for_correction: bool
    points: tuple[StandardSeriesPointV2, ...] = Field(max_length=512)

    @model_validator(mode="after")
    def _curve_is_bounded(self) -> Self:
        if len(self.points) > 512:
            raise ValueError("trajectory curve exceeds 512 presentation points")
        return self


class StandardAxisBoundsV2(StandardPresentationModel):
    axis_id: Literal["time", "frequency_hz", "metric_value", "power_db"]
    label: CandidateOnlyLabel
    unit: StandardUnitV2
    full_source_min: float
    full_source_max: float

    @model_validator(mode="after")
    def _bounds_are_ordered(self) -> Self:
        if self.full_source_min > self.full_source_max:
            raise ValueError("full-source axis bounds are reversed")
        return self


class StandardPlotViewV2(StandardPresentationModel):
    schema_version: Literal[2] = 2
    session_id: Identifier
    subject_id: Identifier
    view_kind: StandardViewKindV2
    state: StandardViewStateV2
    time_domain: StandardTimeDomainV2
    receiver_path_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=4)
    horizontal_axis: StandardAxisBoundsV2
    vertical_axis: StandardAxisBoundsV2
    color_axis: StandardAxisBoundsV2 | None = None
    source_point_count: Annotated[int, Field(ge=0)]
    returned_point_count: Annotated[int, Field(ge=0, le=8192)]
    truncated: bool
    series: tuple[StandardMetricSeriesV2, ...] = Field(default=(), max_length=32)
    waterfall_cells: tuple[StandardWaterfallCellV2, ...] = Field(default=(), max_length=8192)
    cfo_observations: tuple[StandardCfoObservationV2, ...] = Field(default=(), max_length=8192)
    trajectory_curves: tuple[StandardTrajectoryCurveV2, ...] = Field(default=(), max_length=256)
    reason: CandidateOnlyText

    @model_validator(mode="after")
    def _payload_matches_view(self) -> Self:
        returned = (
            sum(len(item.points) for item in self.series)
            + len(self.waterfall_cells)
            + len(self.cfo_observations)
            + sum(len(item.points) for item in self.trajectory_curves)
        )
        if self.returned_point_count != returned:
            raise ValueError("plot returned point count disagrees with its payload")
        if self.source_point_count < returned:
            raise ValueError("plot source count is smaller than returned points")
        if self.truncated != (self.source_point_count > returned):
            raise ValueError("plot truncation flag disagrees with counts")
        if (
            self.state is not StandardViewStateV2.UNAVAILABLE
            and self.source_point_count > 0
            and returned == 0
        ):
            raise ValueError("available/partial plot sources require bounded returned evidence")
        if len(self.series) > 32 or len(self.waterfall_cells) > 8192:
            raise ValueError("plot exceeds presentation collection bounds")
        if len(self.receiver_path_ids) != len(set(self.receiver_path_ids)):
            raise ValueError("plot receiver-path lanes must be distinct")
        known_lanes = set(self.receiver_path_ids)
        returned_lanes = {
            *[item.receiver_path_id for item in self.series],
            *[item.receiver_path_id for item in self.waterfall_cells],
            *[item.receiver_path_id for item in self.cfo_observations],
            *[item.receiver_path_id for item in self.trajectory_curves],
        }
        if not returned_lanes <= known_lanes:
            raise ValueError("plot payload contains a foreign receiver-path lane")
        time_bounds = (self.time_domain.elapsed_start_s, self.time_domain.elapsed_end_s)
        axes = (self.horizontal_axis, self.vertical_axis)
        if self.view_kind is StandardViewKindV2.WATERFALL:
            expected = ("frequency_hz", "time")
            if self.color_axis is None or self.color_axis.axis_id != "power_db":
                raise ValueError("waterfall requires full-source power color bounds")
        elif self.view_kind is StandardViewKindV2.CFO_TRAJECTORY:
            expected = ("time", "frequency_hz")
            if self.color_axis is not None:
                raise ValueError("CFO trajectory view does not define a color axis")
        else:
            expected = ("time", "metric_value")
            if self.color_axis is not None:
                raise ValueError("metric view does not define a color axis")
        if tuple(axis.axis_id for axis in axes) != expected:
            raise ValueError("plot axes do not match the view geometry")
        time_axis = next(axis for axis in axes if axis.axis_id == "time")
        if (time_axis.full_source_min, time_axis.full_source_max) != time_bounds:
            raise ValueError("plot time-axis bounds disagree with the shared time domain")
        populated = {
            "series": bool(self.series),
            "waterfall": bool(self.waterfall_cells),
            "cfo": bool(self.cfo_observations or self.trajectory_curves),
        }
        if self.state is StandardViewStateV2.UNAVAILABLE and any(populated.values()):
            raise ValueError("unavailable views cannot contain plotted evidence")
        if self.view_kind is StandardViewKindV2.WATERFALL:
            if populated["series"] or populated["cfo"]:
                raise ValueError("waterfall view accepts waterfall cells only")
        elif self.view_kind is StandardViewKindV2.CFO_TRAJECTORY:
            if populated["series"] or populated["waterfall"]:
                raise ValueError("CFO trajectory view accepts observations and curves only")
        elif populated["waterfall"] or populated["cfo"]:
            raise ValueError("metric views accept time series only")
        if self.series:
            minima = [item.source_min for item in self.series if item.source_min is not None]
            maxima = [item.source_max for item in self.series if item.source_max is not None]
            if minima and (
                self.vertical_axis.full_source_min != min(minima)
                or self.vertical_axis.full_source_max != max(maxima)
            ):
                raise ValueError("metric axis must equal aggregate full-source series extrema")
        frequencies = (
            [item.frequency_hz for item in self.waterfall_cells]
            + [item.baseband_cfo_hz for item in self.cfo_observations]
            + [item.value for curve in self.trajectory_curves for item in curve.points]
        )
        frequency_axis = next((axis for axis in axes if axis.axis_id == "frequency_hz"), None)
        if (
            frequencies
            and frequency_axis is not None
            and (
                min(frequencies) != frequency_axis.full_source_min
                or max(frequencies) != frequency_axis.full_source_max
            )
        ):
            raise ValueError(
                "waterfall/CFO payload must retain exact full-source frequency extrema"
            )
        if self.waterfall_cells and self.color_axis is not None:
            powers = [item.power_db for item in self.waterfall_cells]
            if (
                min(powers) != self.color_axis.full_source_min
                or max(powers) != self.color_axis.full_source_max
            ):
                raise ValueError("waterfall payload must retain exact full-source power extrema")
        start = self.time_domain.elapsed_start_s
        end = self.time_domain.elapsed_end_s
        times = (
            [point.time_s for item in self.series for point in item.points]
            + [point.time_s for point in self.waterfall_cells]
            + [point.time_s for point in self.cfo_observations]
            + [point.time_s for curve in self.trajectory_curves for point in curve.points]
        )
        if any(time < start or time > end for time in times):
            raise ValueError("plot point lies outside the shared subject time domain")
        return self


def standard_eligibility_v2(
    source_type: StandardSourceTypeV2,
    tags: tuple[str, ...],
    *,
    capture_committed: bool,
    capture_healthy: bool,
) -> StandardEligibilityV2:
    """Project frozen LIVE/IMPORT/TEST scheduling and promotion truth."""

    excluded = tuple(tag for tag in ("QUALIFICATION", "CALIBRATION", "ACCEPTANCE") if tag in tags)
    if not capture_committed or not capture_healthy:
        return StandardEligibilityV2(
            source_type=source_type,
            capture_committed=capture_committed,
            capture_healthy=capture_healthy,
            automatic_eligible=False,
            explicit_eligible=False,
            promotion_allowed=False,
            evidence_only=source_type is StandardSourceTypeV2.TEST,
            exclusion_tags=excluded,
            reason=(
                "Capture is not committed; Standard analysis eligibility fails closed"
                if not capture_committed
                else "Capture health is unavailable or failed; Standard analysis eligibility "
                "fails closed"
            ),
        )
    if excluded:
        return StandardEligibilityV2(
            source_type=source_type,
            capture_committed=capture_committed,
            capture_healthy=capture_healthy,
            automatic_eligible=False,
            explicit_eligible=False,
            promotion_allowed=False,
            evidence_only=source_type is StandardSourceTypeV2.TEST,
            exclusion_tags=excluded,
            reason=f"Excluded from Standard by evidence-lane tag(s): {', '.join(excluded)}",
        )
    if source_type is StandardSourceTypeV2.TEST:
        return StandardEligibilityV2(
            source_type=source_type,
            capture_committed=capture_committed,
            capture_healthy=capture_healthy,
            automatic_eligible=False,
            explicit_eligible=True,
            promotion_allowed=False,
            evidence_only=True,
            reason="Reviewed TEST corpus is explicit, non-current evidence only",
        )
    return StandardEligibilityV2(
        source_type=source_type,
        capture_committed=capture_committed,
        capture_healthy=capture_healthy,
        automatic_eligible=True,
        explicit_eligible=True,
        promotion_allowed=True,
        evidence_only=False,
        reason=f"Committed ordinary {source_type.value} capture is Standard eligible",
    )
