"""Closed operator-presentation contracts for promoted Standard-native runs.

The published Standard-v2 presentation contracts remain untouched.  These
additive V3 contracts expose the validity-aware native-rate result without
reinterpreting the evidence-only scientific product contracts as promotion
authority: Current comes only from the sealed run's promotion envelope, while
coverage and science disposition remain independent terminal facts.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_native import NativeSufficientStatisticsV1, NativeValidUtcIntervalV1
from leo.contracts.standard_native_path_report import (
    NativePathScientificDispositionV1,
    NativeProbeExecutionAccountingV1,
    NativeQamSufficientStatisticsV1,
)
from leo.contracts.standard_native_terminal import NativeTerminalTrackAccountingV1
from leo.presentation.standard_pipeline import (
    StandardComputationDispositionV2,
    StandardReceiverPathRefV2,
    StandardReuseSummaryV2,
    StandardStageStatusV2,
    StandardSubjectKindV2,
    StandardSubjectStateV2,
    StandardTimeDomainV2,
    StandardViewKindV2,
    StandardViewStateV2,
)

Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=192, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
GitSha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
BoundedText = Annotated[str, StringConstraints(min_length=1, max_length=1024)]
NativeCoverageStatusV3 = Literal["complete", "partial_coverage", "insufficient_data"]
NativeArtifactNameV3 = Literal["waterfall", "cfo-alternate"]


class StandardNativePipelineReleaseV3(ContractModel):
    """Exact promotable native definition and executable release."""

    schema_version: Literal[3] = 3
    family: Literal["standard-native-v1"] = "standard-native-v1"
    authoritative_pipeline_release_id: GitSha
    source_revision: GitSha
    pipeline_definition_id: Sha256Digest
    graph_digest: Sha256Digest
    configuration_digest: Sha256Digest
    environment_digest: Sha256Digest

    @model_validator(mode="after")
    def _release_is_exact(self) -> Self:
        if self.authoritative_pipeline_release_id != self.source_revision:
            raise ValueError("native presentation release is not exact source authority")
        return self


class StandardNativeEligibilityV3(ContractModel):
    """Promotion truth for a reviewed full-device-span V3 LIVE capture."""

    schema_version: Literal[3] = 3
    source_type: Literal["LIVE"] = "LIVE"
    source_manifest_schema_version: Literal[3] = 3
    capture_state: Literal["committed", "degraded"]
    capture_committed: bool
    capture_healthy: Literal[True] = True
    full_device_span: Literal[True] = True
    validity_aware: Literal[True] = True
    automatic_eligible: Literal[True] = True
    explicit_eligible: Literal[True] = True
    promotion_allowed: Literal[True] = True
    evidence_only: Literal[False] = False
    profile_revision_digest: Sha256Digest
    sample_rate_hz: Literal[2_500_000, 3_000_000, 5_000_000, 10_000_000]
    pipeline_definition_id: Sha256Digest
    promotion_authority_digest: Sha256Digest
    reason: Literal[
        "Promoted reviewed V3 Standard-native capture is Current",
        "Promoted reviewed V3 Standard-native capture is Current with partial validity coverage",
    ]

    @model_validator(mode="after")
    def _eligibility_is_exact(self) -> Self:
        committed = self.capture_state == "committed"
        if self.capture_committed != committed:
            raise ValueError("native eligibility committed flag disagrees with capture state")
        expected_reason = (
            "Promoted reviewed V3 Standard-native capture is Current"
            if committed
            else (
                "Promoted reviewed V3 Standard-native capture is Current with partial "
                "validity coverage"
            )
        )
        if self.reason != expected_reason:
            raise ValueError("native eligibility reason disagrees with capture state")
        return self


class StandardNativeMixedLegV4(ContractModel):
    """One exact RF/passband and native-rate leg shown for a mixed dwell."""

    schema_version: Literal[4] = 4
    stream_id: Identifier
    radio_id: Identifier
    profile_name: Identifier
    profile_revision_digest: Sha256Digest
    starlink_channel: Annotated[int, Field(ge=1, le=4)]
    starlink_edge: Literal["lower", "upper"]
    sample_rate_hz: Literal[2_500_000, 5_000_000, 10_000_000]
    rf_bandwidth_hz: Literal[2_500_000, 5_000_000, 10_000_000]
    tuned_center_frequency_hz: Annotated[int, Field(gt=0)]
    pilot_if_center_frequency_hz: Annotated[int, Field(gt=0)]
    channel_if_start_hz: Annotated[int, Field(gt=0)]
    channel_if_stop_hz: Annotated[int, Field(gt=0)]
    captured_if_start_hz: Annotated[int, Field(gt=0)]
    captured_if_stop_hz: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def _rf_passband_closes(self) -> Self:
        if (
            self.rf_bandwidth_hz != self.sample_rate_hz
            or self.captured_if_stop_hz - self.captured_if_start_hz != self.rf_bandwidth_hz
            or 2 * self.tuned_center_frequency_hz
            != self.captured_if_start_hz + self.captured_if_stop_hz
            or self.channel_if_stop_hz <= self.channel_if_start_hz
            or self.captured_if_start_hz < self.channel_if_start_hz
            or self.captured_if_stop_hz > self.channel_if_stop_hz
            or not (
                self.captured_if_start_hz
                <= self.pilot_if_center_frequency_hz
                <= self.captured_if_stop_hz
            )
        ):
            raise ValueError("mixed native presentation RF/passband authority is invalid")
        return self


class StandardNativeEligibilityV4(ContractModel):
    """Promotion truth for one reviewed unequal-rate RecordingManifestV4."""

    schema_version: Literal[4] = 4
    source_type: Literal["LIVE"] = "LIVE"
    source_manifest_schema_version: Literal[4] = 4
    capture_state: Literal["committed", "degraded"]
    capture_committed: bool
    capture_healthy: Literal[True] = True
    full_device_span: Literal[True] = True
    validity_aware: Literal[True] = True
    automatic_eligible: Literal[True] = True
    explicit_eligible: Literal[True] = True
    promotion_allowed: Literal[True] = True
    evidence_only: Literal[False] = False
    dwell_class: Literal["mixed_2p5_5", "mixed_2p5_10"]
    legs: tuple[StandardNativeMixedLegV4, StandardNativeMixedLegV4]
    pipeline_definition_id: Sha256Digest
    promotion_authority_digest: Sha256Digest
    resampled: Literal[False] = False
    reason: Literal[
        "Promoted reviewed mixed Standard-native capture is Current",
        "Promoted reviewed mixed Standard-native capture is Current with partial validity coverage",
    ]

    @model_validator(mode="after")
    def _eligibility_is_exact(self) -> Self:
        committed = self.capture_state == "committed"
        if self.capture_committed != committed:
            raise ValueError("mixed native eligibility committed flag disagrees with capture state")
        identities = tuple((item.stream_id, item.radio_id) for item in self.legs)
        if identities != tuple(sorted(identities)) or len(set(identities)) != 2:
            raise ValueError("mixed native presentation leg inventory is not exact")
        expected_rates = {
            "mixed_2p5_5": {2_500_000, 5_000_000},
            "mixed_2p5_10": {2_500_000, 10_000_000},
        }[self.dwell_class]
        if {item.sample_rate_hz for item in self.legs} != expected_rates:
            raise ValueError("mixed native presentation rate pair disagrees with its dwell class")
        expected_reason = (
            "Promoted reviewed mixed Standard-native capture is Current"
            if committed
            else (
                "Promoted reviewed mixed Standard-native capture is Current with partial "
                "validity coverage"
            )
        )
        if self.reason != expected_reason:
            raise ValueError("mixed native eligibility reason disagrees with capture state")
        return self


class StandardNativeTerminalSummaryV3(ContractModel):
    """Terminal sufficient statistics for one displayed subject.

    The embedded counters are copied from the sealed path/radio/paired terminal
    report.  Derived ratios therefore remain auditable and reducers never
    average child ratios.
    """

    schema_version: Literal[3] = 3
    expected_complex_sample_count: Annotated[int, Field(gt=0)]
    valid_complex_sample_count: Annotated[int, Field(gt=0)]
    missing_complex_sample_count: Annotated[int, Field(ge=0)]
    coverage_fraction: Annotated[float, Field(gt=0, le=1)]
    coverage_status: NativeCoverageStatusV3
    sufficient_statistics: NativeSufficientStatisticsV1
    terminal_opportunities: NativeProbeExecutionAccountingV1
    qam_statistics: NativeQamSufficientStatisticsV1
    terminal_tracks: NativeTerminalTrackAccountingV1
    scientific_disposition: NativePathScientificDispositionV1
    valid_utc_intervals: tuple[NativeValidUtcIntervalV1, ...]
    valid_samples_only: Literal[True] = True
    stateful_resets_at_continuity_boundaries: Literal[True] = True
    cross_gap_operation_permitted: Literal[False] = False
    reducer_uses_sufficient_statistics: Literal[True] = True

    @model_validator(mode="after")
    def _terminal_counts_close(self) -> Self:
        if self.valid_complex_sample_count != self.sufficient_statistics.valid_complex_sample_count:
            raise ValueError("native presentation support differs from terminal statistics")
        if self.expected_complex_sample_count != (
            self.valid_complex_sample_count + self.missing_complex_sample_count
        ):
            raise ValueError("native presentation expected/valid/missing counts do not close")
        expected_fraction = self.valid_complex_sample_count / self.expected_complex_sample_count
        if not math.isclose(self.coverage_fraction, expected_fraction, abs_tol=1e-15):
            raise ValueError("native presentation coverage differs from terminal counts")
        if self.coverage_status == "complete" and self.missing_complex_sample_count:
            raise ValueError("complete native presentation carries missing samples")
        if self.coverage_status == "partial_coverage" and not self.missing_complex_sample_count:
            raise ValueError("partial native presentation lacks missing samples")
        return self


class StandardNativeSubjectSummaryV3(ContractModel):
    schema_version: Literal[3] = 3
    subject_id: Identifier
    session_id: Identifier
    subject_kind: StandardSubjectKindV2
    label: BoundedText
    derived: bool
    receiver_paths: tuple[StandardReceiverPathRefV2, ...] = Field(min_length=1, max_length=4)
    expected_path_count: Annotated[int, Field(ge=1, le=4)]
    completed_path_count: Annotated[int, Field(ge=1, le=4)]
    child_subject_ids: tuple[Identifier, ...] = Field(max_length=4)
    state: Literal[StandardSubjectStateV2.CURRENT] = StandardSubjectStateV2.CURRENT
    ordinary_current: Literal[True] = True
    coverage_status: NativeCoverageStatusV3
    scientific_disposition: NativePathScientificDispositionV1
    pipeline_release: StandardNativePipelineReleaseV3
    desired_pipeline_release_id: GitSha
    reuse: StandardReuseSummaryV2
    eligibility: StandardNativeEligibilityV3
    terminal: StandardNativeTerminalSummaryV3
    evidence_label: Literal["candidate evidence only"] = "candidate evidence only"

    @model_validator(mode="after")
    def _subject_is_current_and_shaped(self) -> Self:
        path_ids = tuple(item.path_id for item in self.receiver_paths)
        path_subject_ids = tuple(item.subject_id for item in self.receiver_paths)
        if (
            self.expected_path_count != len(self.receiver_paths)
            or self.completed_path_count != self.expected_path_count
            or len(path_ids) != len(set(path_ids))
            or len(path_subject_ids) != len(set(path_subject_ids))
        ):
            raise ValueError("native current subject path inventory is not exact")
        if self.coverage_status != self.terminal.coverage_status:
            raise ValueError("native subject coverage differs from terminal evidence")
        if self.scientific_disposition is not self.terminal.scientific_disposition:
            raise ValueError("native subject science differs from terminal evidence")
        if (
            self.desired_pipeline_release_id
            != self.pipeline_release.authoritative_pipeline_release_id
            or self.eligibility.pipeline_definition_id
            != self.pipeline_release.pipeline_definition_id
        ):
            raise ValueError("native subject release authority is crossed")
        if self.subject_kind is StandardSubjectKindV2.RECEIVER_PATH:
            if self.derived or len(self.receiver_paths) != 1 or self.child_subject_ids:
                raise ValueError("native receiver-path subject shape is invalid")
            if self.subject_id != self.receiver_paths[0].subject_id:
                raise ValueError("native receiver-path subject identity changed")
        elif self.subject_kind is StandardSubjectKindV2.RADIO:
            if not self.derived or len(self.receiver_paths) != 2:
                raise ValueError("native radio subject requires two derived paths")
            if self.child_subject_ids != path_subject_ids:
                raise ValueError("native radio children differ from its path inventory")
            if len({item.radio_id for item in self.receiver_paths}) != 1:
                raise ValueError("native radio subject crosses radios")
        else:
            if (
                not self.derived
                or len({item.radio_id for item in self.receiver_paths}) != 2
                or len(self.child_subject_ids) != 2
            ):
                raise ValueError("native paired subject shape is invalid")
        return self


class StandardNativeSubjectSummaryV4(StandardNativeSubjectSummaryV3):
    """Mixed-rate subject summary with run-level V4 promotion truth."""

    schema_version: Literal[4] = 4  # type: ignore[assignment]
    eligibility: StandardNativeEligibilityV4  # type: ignore[assignment]


class StandardNativeSubjectHierarchyV3(ContractModel):
    schema_version: Literal[3] = 3
    session_id: Identifier
    source_type: Literal["LIVE"] = "LIVE"
    eligibility: StandardNativeEligibilityV3
    generated_at: datetime
    rows: tuple[StandardNativeSubjectSummaryV3, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def _hierarchy_is_exact(self) -> Self:
        if any(item.session_id != self.session_id for item in self.rows):
            raise ValueError("native hierarchy contains a foreign subject")
        if any(item.eligibility != self.eligibility for item in self.rows):
            raise ValueError("native hierarchy eligibility is crossed")
        if len({item.subject_id for item in self.rows}) != len(self.rows):
            raise ValueError("native hierarchy repeats a subject")
        radios = tuple(
            item for item in self.rows if item.subject_kind is StandardSubjectKindV2.RADIO
        )
        pairs = tuple(
            item for item in self.rows if item.subject_kind is StandardSubjectKindV2.PAIRED
        )
        if len(radios) == 2:
            if len(self.rows) != 3 or len(pairs) != 1 or self.rows[0] is not pairs[0]:
                raise ValueError("dual-radio native hierarchy requires pair then two radios")
            if pairs[0].child_subject_ids != tuple(item.subject_id for item in radios):
                raise ValueError("native paired children differ from radio rows")
            if pairs[0].receiver_paths != tuple(
                path for radio in radios for path in radio.receiver_paths
            ):
                raise ValueError("native paired paths differ from the radio union")
        elif len(radios) != 1 or pairs or len(self.rows) != 1:
            raise ValueError("native hierarchy requires one radio or an exact radio pair")
        return self


class StandardNativeSubjectHierarchyV4(ContractModel):
    """Exact pair/radio hierarchy for a mixed-rate Current run."""

    schema_version: Literal[4] = 4
    session_id: Identifier
    source_type: Literal["LIVE"] = "LIVE"
    eligibility: StandardNativeEligibilityV4
    generated_at: datetime
    rows: tuple[StandardNativeSubjectSummaryV4, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _hierarchy_is_exact(self) -> Self:
        if any(item.session_id != self.session_id for item in self.rows):
            raise ValueError("mixed native hierarchy contains a foreign subject")
        if any(item.eligibility != self.eligibility for item in self.rows):
            raise ValueError("mixed native hierarchy eligibility is crossed")
        if len({item.subject_id for item in self.rows}) != len(self.rows):
            raise ValueError("mixed native hierarchy repeats a subject")
        paired = tuple(
            item for item in self.rows if item.subject_kind is StandardSubjectKindV2.PAIRED
        )
        radios = tuple(
            item for item in self.rows if item.subject_kind is StandardSubjectKindV2.RADIO
        )
        if len(paired) != 1 or len(radios) != 2 or self.rows[0] is not paired[0]:
            raise ValueError("mixed native hierarchy requires pair then two radios")
        if paired[0].child_subject_ids != tuple(item.subject_id for item in radios):
            raise ValueError("mixed native paired children differ from radio rows")
        if paired[0].receiver_paths != tuple(
            path for radio in radios for path in radio.receiver_paths
        ):
            raise ValueError("mixed native paired paths differ from the radio union")
        return self


class StandardNativePathEvidenceV3(ContractModel):
    schema_version: Literal[3] = 3
    receiver_path: StandardReceiverPathRefV2
    terminal: StandardNativeTerminalSummaryV3
    declared_seconds: Annotated[float, Field(gt=0)]
    valid_seconds: Annotated[float, Field(gt=0)]
    continuity_segment_count: Annotated[int, Field(gt=0)]
    continuity_boundary_count: Annotated[int, Field(ge=0)]
    invalid_zero_fill_excluded: Literal[True] = True

    @model_validator(mode="after")
    def _path_evidence_closes(self) -> Self:
        if not math.isclose(
            self.valid_seconds / self.declared_seconds,
            self.terminal.coverage_fraction,
            abs_tol=1e-15,
        ):
            raise ValueError("native path seconds disagree with terminal coverage")
        if self.continuity_boundary_count != self.continuity_segment_count - 1:
            raise ValueError("native path continuity boundary count is invalid")
        return self


class StandardNativeTrajectoryV3(ContractModel):
    schema_version: Literal[3] = 3
    receiver_path_id: Identifier
    continuity_segment_index: Annotated[int, Field(ge=0)]
    trajectory_id: Sha256Digest
    start_s: Annotated[float, Field(ge=0)]
    end_s: Annotated[float, Field(ge=0)]
    reference_time_s: Annotated[float, Field(ge=0)]
    polynomial_degree: Literal[1, 2, 3]
    absolute_coefficients_hz: tuple[float, ...] = Field(min_length=2, max_length=4)
    support_count: Annotated[int, Field(ge=3)]
    automatic_correction_eligible: bool
    replay_tier: BoundedText
    cross_segment_association_permitted: Literal[False] = False

    @field_validator("start_s", "end_s", "reference_time_s")
    @classmethod
    def _times_are_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("native trajectory time must be finite")
        return value

    @model_validator(mode="after")
    def _trajectory_is_local(self) -> Self:
        if self.end_s < self.start_s or len(self.absolute_coefficients_hz) != (
            self.polynomial_degree + 1
        ):
            raise ValueError("native trajectory geometry is invalid")
        if any(not math.isfinite(value) for value in self.absolute_coefficients_hz):
            raise ValueError("native trajectory coefficients must be finite")
        return self


class StandardNativeViewDescriptorV3(ContractModel):
    schema_version: Literal[3] = 3
    view_kind: StandardViewKindV2
    state: StandardViewStateV2
    href: Annotated[str, StringConstraints(min_length=9, max_length=512, pattern=r"^/api/v2/")]
    source_point_count: Annotated[int, Field(ge=0)]
    png_available: bool
    png_href: Annotated[
        str | None,
        StringConstraints(min_length=9, max_length=512, pattern=r"^/api/v2/"),
    ] = None
    reason: BoundedText

    @model_validator(mode="after")
    def _png_state_closes(self) -> Self:
        if self.png_available != (self.png_href is not None):
            raise ValueError("native PNG availability differs from its immutable href")
        if self.state is StandardViewStateV2.UNAVAILABLE and self.source_point_count:
            raise ValueError("unavailable native view claims source evidence")
        return self


class StandardNativeSubjectDetailV3(ContractModel):
    schema_version: Literal[3] = 3
    subject: StandardNativeSubjectSummaryV3
    time_domain: StandardTimeDomainV2
    receiver_path_expansions: tuple[StandardNativeSubjectSummaryV3, ...] = Field(
        min_length=1, max_length=4
    )
    receiver_path_evidence: tuple[StandardNativePathEvidenceV3, ...] = Field(
        min_length=1, max_length=4
    )
    stage_source_count: Annotated[int, Field(ge=0)]
    stages: tuple[StandardStageStatusV2, ...] = Field(max_length=256)
    stages_truncated: bool
    trajectory_source_count: Annotated[int, Field(ge=0)]
    trajectories: tuple[StandardNativeTrajectoryV3, ...] = Field(max_length=256)
    trajectories_truncated: bool
    views: tuple[StandardNativeViewDescriptorV3, ...] = Field(min_length=6, max_length=6)
    available_artifacts: tuple[NativeArtifactNameV3, ...] = Field(max_length=2)
    limitations: tuple[
        Literal[
            "Candidate evidence only; source identity is unassessed; "
            "no payload recovery is claimed",
            "Stateful algorithms reset at every continuity boundary",
            "Power, quality, QAM, and opportunity reducers use valid samples "
            "and sufficient statistics",
            "Waterfall tiles retain the global device-time axis and mark missing cells invalid",
            "Paired-radio support is the intersection of valid UTC intervals",
        ],
        ...,
    ]

    @model_validator(mode="after")
    def _detail_is_exact(self) -> Self:
        if self.stage_source_count < len(self.stages) or self.stages_truncated != (
            self.stage_source_count > len(self.stages)
        ):
            raise ValueError("native detail stage bounds are inconsistent")
        if self.trajectory_source_count < len(self.trajectories) or self.trajectories_truncated != (
            self.trajectory_source_count > len(self.trajectories)
        ):
            raise ValueError("native detail trajectory bounds are inconsistent")
        if {item.view_kind for item in self.views} != set(StandardViewKindV2):
            raise ValueError("native detail must describe every Standard view")
        expected_paths = tuple(item.path_id for item in self.subject.receiver_paths)
        expansion_paths = tuple(
            item.receiver_paths[0].path_id for item in self.receiver_path_expansions
        )
        evidence_paths = tuple(item.receiver_path.path_id for item in self.receiver_path_evidence)
        if expansion_paths != expected_paths or evidence_paths != expected_paths:
            raise ValueError("native detail path expansion/evidence inventory is crossed")
        return self


class StandardNativeSubjectDetailV4(StandardNativeSubjectDetailV3):
    """Mixed-rate detail; evidence rows remain the same per-path native contracts."""

    schema_version: Literal[4] = 4  # type: ignore[assignment]
    subject: StandardNativeSubjectSummaryV4
    receiver_path_expansions: tuple[StandardNativeSubjectSummaryV4, ...] = Field(
        min_length=1, max_length=4
    )


class StandardNativePresentationProductRefV3(ContractModel):
    schema_version: Literal[3] = 3
    product_id: Annotated[int, Field(gt=0)]
    scope_key: Identifier
    kind: Identifier
    product_schema_version: Annotated[int, Field(gt=0)]
    digest: Sha256Digest


class StandardNativeSourceProofV3(ContractModel):
    schema_version: Literal[3] = 3
    run_manifest_digest: Sha256Digest
    products: tuple[StandardNativePresentationProductRefV3, ...] = Field(
        min_length=1, max_length=16
    )
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _proof_is_canonical(self) -> Self:
        identities = tuple(
            (item.scope_key, item.kind, item.product_schema_version) for item in self.products
        )
        if identities != tuple(sorted(set(identities))):
            raise ValueError("native presentation source products are not canonical")
        expected = canonical_digest(
            {
                "schema_version": self.schema_version,
                "run_manifest_digest": self.run_manifest_digest,
                "products": tuple(item.model_dump(mode="json") for item in self.products),
            }
        )
        if self.content_digest != expected:
            raise ValueError("native presentation source proof digest does not match")
        return self


class StandardNativeMetricPointV3(ContractModel):
    schema_version: Literal[3] = 3
    time_s: Annotated[float, Field(ge=0)]
    value: float | None
    valid: bool

    @field_validator("time_s", "value")
    @classmethod
    def _values_are_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("native metric value must be finite")
        return value

    @model_validator(mode="after")
    def _validity_is_explicit(self) -> Self:
        if self.valid != (self.value is not None):
            raise ValueError("native metric validity differs from its value")
        return self


class StandardNativeMetricSeriesV3(ContractModel):
    schema_version: Literal[3] = 3
    series_id: Identifier
    receiver_path_id: Identifier
    label: BoundedText
    unit: Literal["dBFS", "fraction", "response", "accuracy", "EVM"]
    source_point_count: Annotated[int, Field(ge=0)]
    points: tuple[StandardNativeMetricPointV3, ...] = Field(max_length=2048)
    truncated: bool

    @model_validator(mode="after")
    def _series_is_bounded(self) -> Self:
        if self.source_point_count < len(self.points) or self.truncated != (
            self.source_point_count > len(self.points)
        ):
            raise ValueError("native metric series bounds are inconsistent")
        times = tuple(item.time_s for item in self.points)
        if times != tuple(sorted(times)):
            raise ValueError("native metric series is not time ordered")
        return self


class StandardNativeWaterfallTileV3(ContractModel):
    """One path/time cell row retaining nullable frequency-bin power."""

    schema_version: Literal[3] = 3
    receiver_path_id: Identifier
    time_bin: Annotated[int, Field(ge=0)]
    time_start_s: Annotated[float, Field(ge=0)]
    time_stop_s: Annotated[float, Field(gt=0)]
    sample_start: Annotated[int, Field(ge=0)]
    sample_stop: Annotated[int, Field(gt=0)]
    transform_count: Annotated[int, Field(ge=0)]
    valid: bool
    power_dbfs: tuple[float | None, ...] = Field(min_length=1, max_length=1024)

    @field_validator("time_start_s", "time_stop_s", "power_dbfs")
    @classmethod
    def _tile_values_are_finite(cls, value: object) -> object:
        values = value if isinstance(value, tuple) else ()
        if values and any(item is not None and not math.isfinite(item) for item in values):
            raise ValueError("native waterfall tile power must be finite")
        return value

    @model_validator(mode="after")
    def _tile_validity_is_explicit(self) -> Self:
        if self.time_stop_s <= self.time_start_s or self.sample_stop <= self.sample_start:
            raise ValueError("native waterfall tile extent is invalid")
        measured = self.transform_count > 0
        if self.valid != measured:
            raise ValueError("native waterfall validity differs from transform support")
        if (measured and not all(item is not None for item in self.power_dbfs)) or (
            not measured and any(item is not None for item in self.power_dbfs)
        ):
            raise ValueError("native waterfall missing cells are not explicitly invalid")
        return self


class StandardNativePlotViewV3(ContractModel):
    schema_version: Literal[3] = 3
    session_id: Identifier
    subject_id: Identifier
    view_kind: StandardViewKindV2
    state: StandardViewStateV2
    time_domain: StandardTimeDomainV2
    receiver_path_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=4)
    sample_rate_hz: Literal[2_500_000, 3_000_000, 5_000_000, 10_000_000]
    source_proof: StandardNativeSourceProofV3
    source_point_count: Annotated[int, Field(ge=0)]
    returned_point_count: Annotated[int, Field(ge=0, le=8192)]
    truncated: bool
    metric_series: tuple[StandardNativeMetricSeriesV3, ...] = Field(default=(), max_length=32)
    frequency_bin_centers_hz: tuple[float, ...] = Field(default=(), max_length=1024)
    waterfall_tiles: tuple[StandardNativeWaterfallTileV3, ...] = Field(default=(), max_length=2048)
    trajectories: tuple[StandardNativeTrajectoryV3, ...] = Field(default=(), max_length=256)
    reason: BoundedText
    projection_digest: Sha256Digest

    @field_validator("frequency_bin_centers_hz")
    @classmethod
    def _frequencies_are_finite(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(not math.isfinite(item) for item in value):
            raise ValueError("native waterfall frequency axis must be finite")
        return value

    @model_validator(mode="after")
    def _plot_is_closed(self) -> Self:
        returned = (
            sum(len(item.points) for item in self.metric_series)
            + len(self.waterfall_tiles)
            + len(self.trajectories)
        )
        if (
            self.returned_point_count != returned
            or self.source_point_count < returned
            or self.truncated != (self.source_point_count > returned)
        ):
            raise ValueError("native plot source/returned counts are inconsistent")
        lanes = {
            *[item.receiver_path_id for item in self.metric_series],
            *[item.receiver_path_id for item in self.waterfall_tiles],
            *[item.receiver_path_id for item in self.trajectories],
        }
        if not lanes <= set(self.receiver_path_ids):
            raise ValueError("native plot contains a foreign receiver path")
        if self.view_kind is StandardViewKindV2.WATERFALL:
            if self.metric_series or self.trajectories or not self.frequency_bin_centers_hz:
                raise ValueError("native waterfall plot payload shape is invalid")
            if any(
                len(item.power_dbfs) != len(self.frequency_bin_centers_hz)
                for item in self.waterfall_tiles
            ):
                raise ValueError("native waterfall tile width differs from its frequency axis")
        elif self.view_kind is StandardViewKindV2.CFO_TRAJECTORY:
            if self.metric_series or self.waterfall_tiles or self.frequency_bin_centers_hz:
                raise ValueError("native trajectory plot payload shape is invalid")
        elif self.waterfall_tiles or self.trajectories or self.frequency_bin_centers_hz:
            raise ValueError("native metric plot payload shape is invalid")
        if self.state is StandardViewStateV2.UNAVAILABLE and returned:
            raise ValueError("unavailable native plot carries evidence")
        if self.projection_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"projection_digest"})
        ):
            raise ValueError("native plot projection digest does not match")
        return self


class StandardNativeFrequencyAxisV4(ContractModel):
    schema_version: Literal[4] = 4
    receiver_path_id: Identifier
    frequency_bin_centers_hz: tuple[float, ...] = Field(min_length=1, max_length=1024)

    @field_validator("frequency_bin_centers_hz")
    @classmethod
    def _frequencies_are_finite(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(not math.isfinite(item) for item in value):
            raise ValueError("mixed native waterfall frequency axis must be finite")
        return value


class StandardNativePlotViewV4(ContractModel):
    """Mixed-rate plot projection retaining every source path's native axis."""

    schema_version: Literal[4] = 4
    session_id: Identifier
    subject_id: Identifier
    view_kind: StandardViewKindV2
    state: StandardViewStateV2
    time_domain: StandardTimeDomainV2
    receiver_path_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=4)
    sample_rates_hz: tuple[Literal[2_500_000, 5_000_000, 10_000_000], ...] = Field(
        min_length=1,
        max_length=2,
    )
    source_proof: StandardNativeSourceProofV3
    source_point_count: Annotated[int, Field(ge=0)]
    returned_point_count: Annotated[int, Field(ge=0, le=8192)]
    truncated: bool
    metric_series: tuple[StandardNativeMetricSeriesV3, ...] = Field(default=(), max_length=32)
    frequency_axes: tuple[StandardNativeFrequencyAxisV4, ...] = Field(default=(), max_length=4)
    waterfall_tiles: tuple[StandardNativeWaterfallTileV3, ...] = Field(default=(), max_length=2048)
    trajectories: tuple[StandardNativeTrajectoryV3, ...] = Field(default=(), max_length=256)
    reason: BoundedText
    projection_digest: Sha256Digest

    @field_validator("sample_rates_hz")
    @classmethod
    def _rate_inventory_is_canonical(
        cls, value: tuple[Literal[2_500_000, 5_000_000, 10_000_000], ...]
    ) -> tuple[Literal[2_500_000, 5_000_000, 10_000_000], ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("mixed native plot rates must be unique and ordered")
        return value

    @model_validator(mode="after")
    def _plot_is_closed(self) -> Self:
        returned = (
            sum(len(item.points) for item in self.metric_series)
            + len(self.waterfall_tiles)
            + len(self.trajectories)
        )
        if (
            self.returned_point_count != returned
            or self.source_point_count < returned
            or self.truncated != (self.source_point_count > returned)
        ):
            raise ValueError("mixed native plot source/returned counts are inconsistent")
        lanes = {
            *[item.receiver_path_id for item in self.metric_series],
            *[item.receiver_path_id for item in self.waterfall_tiles],
            *[item.receiver_path_id for item in self.trajectories],
        }
        if not lanes <= set(self.receiver_path_ids):
            raise ValueError("mixed native plot contains a foreign receiver path")
        if self.view_kind is StandardViewKindV2.WATERFALL:
            axes = {
                item.receiver_path_id: item.frequency_bin_centers_hz for item in self.frequency_axes
            }
            if self.metric_series or self.trajectories or set(axes) != set(self.receiver_path_ids):
                raise ValueError("mixed native waterfall plot payload shape is invalid")
            if any(
                len(item.power_dbfs) != len(axes[item.receiver_path_id])
                for item in self.waterfall_tiles
            ):
                raise ValueError("mixed native waterfall tile differs from its path axis")
        elif self.view_kind is StandardViewKindV2.CFO_TRAJECTORY:
            if self.metric_series or self.waterfall_tiles or self.frequency_axes:
                raise ValueError("mixed native trajectory plot payload shape is invalid")
        elif self.waterfall_tiles or self.trajectories or self.frequency_axes:
            raise ValueError("mixed native metric plot payload shape is invalid")
        if self.state is StandardViewStateV2.UNAVAILABLE and returned:
            raise ValueError("unavailable mixed native plot carries evidence")
        if self.projection_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"projection_digest"})
        ):
            raise ValueError("mixed native plot projection digest does not match")
        return self


type StandardHierarchy = StandardNativeSubjectHierarchyV3 | StandardNativeSubjectHierarchyV4
type StandardDetail = StandardNativeSubjectDetailV3 | StandardNativeSubjectDetailV4
type StandardPlot = StandardNativePlotViewV3 | StandardNativePlotViewV4


def native_stage_status_v3(
    *, stage_key: str, subject_id: str, output_digest: str | None
) -> StandardStageStatusV2:
    """Build the shared frozen stage row without changing its V2 contract."""

    return StandardStageStatusV2(
        stage_key=stage_key,
        subject_id=subject_id,
        disposition=StandardComputationDispositionV2.COMPUTED,
        output_digest=None if output_digest is None else output_digest.removeprefix("sha256:"),
        reason="Rendered for this run",
    )
