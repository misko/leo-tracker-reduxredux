"""Closed protocol and derived-manifest contracts for Doppler holdout feasibility."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from leo.analysis.research.doppler_dataset_policy import (
    CaptureBinding,
    DopplerDatasetPolicy,
    authorize_consumed_inputs,
)
from leo.contracts.digests import Sha256Digest, canonical_digest

PROTOCOL_SCHEMA = "org.leo.research.doppler-holdout-feasibility-protocol/v1"
MANIFEST_SCHEMA = "org.leo.research.doppler-holdout-derived-manifest/v1"

Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
ReasonCode = Annotated[
    str,
    StringConstraints(min_length=1, max_length=256, pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$"),
]
GitCommit = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]


class _ResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)


class HoldoutProductRequirementV1(_ResearchModel):
    kind: Identifier
    schema_version: Annotated[int, Field(gt=0)]
    stage_key: Identifier
    role: Literal["scientific"] = "scientific"
    media_type: Literal["application/json"] = "application/json"


class SourceEpisodeSelectorV1(_ResearchModel):
    algorithm: Literal["longest-source-bounded-window-v1"]
    maximum_source_gap_ms: Annotated[float, Field(gt=0)]
    minimum_episode_duration_ms: Annotated[float, Field(gt=0)]
    maximum_episode_duration_ms: Annotated[float, Field(gt=0)]
    minimum_source_observation_count: Annotated[int, Field(ge=3)]
    require_automatic_correction_eligible: Literal[True]
    require_one_raw_source_per_canonical_observation: Literal[True]
    rank_order: Literal[
        "source-count-desc,duration-desc,median-source-margin-desc,"
        "evaluated-probe-count-desc,scope-trajectory-start-asc"
    ]
    even_failure_fallback: Literal["none"]

    @model_validator(mode="after")
    def _durations_are_ordered(self) -> Self:
        if self.minimum_episode_duration_ms > self.maximum_episode_duration_ms:
            raise ValueError("minimum episode duration exceeds maximum")
        if self.maximum_source_gap_ms >= self.minimum_episode_duration_ms:
            raise ValueError("source gap cannot span the minimum episode")
        return self


class EvenQinMaskConfigV1(_ResearchModel):
    training_symbol_indices: Literal["zero-based-even-0-through-298"]
    sealed_response_symbol_indices: Literal["zero-based-odd-1-through-299"]
    raw_span_loading: Literal["guarded-full-frame-loaded-before-even-only-demodulation"]
    residual_cfo_half_width_hz: Annotated[float, Field(gt=0)]
    minimum_exact_coherence: Annotated[float, Field(ge=0, le=1)]
    minimum_coherence_margin: Annotated[float, Field(ge=-1, le=1)]
    minimum_frame_opportunities: Annotated[int, Field(gt=0)]
    minimum_supported_frames: Annotated[int, Field(gt=0)]
    minimum_support_fraction: Annotated[float, Field(gt=0, le=1)]
    minimum_contiguous_supported_frames: Annotated[int, Field(gt=0)]
    unsupported_frames_retained: Literal[True]

    @model_validator(mode="after")
    def _frame_thresholds_are_consistent(self) -> Self:
        if self.minimum_supported_frames > self.minimum_frame_opportunities:
            raise ValueError("supported-frame minimum exceeds opportunity minimum")
        if self.minimum_contiguous_supported_frames > self.minimum_supported_frames:
            raise ValueError("contiguous-frame minimum exceeds supported-frame minimum")
        return self


class DopplerHoldoutFeasibilityProtocolV1(_ResearchModel):
    schema: Literal[  # type: ignore[assignment]
        "org.leo.research.doppler-holdout-feasibility-protocol/v1"
    ]
    dataset_policy_schema: Literal["org.leo.research.doppler-experiment-dataset-policy/v1"]
    dataset_policy_repository_commit: GitCommit
    dataset_policy_sha256: Sha256Digest
    experiment_role: Literal["holdout_foundation"]
    phase: Literal["feasibility_only"]
    future_odd_qin_outcomes_opened_at_freeze: Literal[False]
    candidate_estimators_permitted: Literal[False]
    upstream_source_and_epoch_conditioning: Literal[
        "frozen-standard-products-may-use-all-qin-for-source-alias-trajectory-and-epoch"
    ]
    dynamic_discovery_permitted: Literal[False]
    capture_substitution_permitted: Literal[False]
    expected_capture_ids: tuple[Identifier, ...]
    minimum_evaluable_capture_count: Annotated[int, Field(gt=0)]
    product_requirements: tuple[HoldoutProductRequirementV1, ...]
    source_episode_selector: SourceEpisodeSelectorV1
    even_qin_mask: EvenQinMaskConfigV1
    failure_policy: Literal["retain-all-15-no-replacement-and-freeze-mask-before-response-scoring"]

    @field_validator("expected_capture_ids")
    @classmethod
    def _capture_ids_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(set(value)) != len(value):
            raise ValueError("protocol capture IDs must be nonempty and unique")
        return value

    @field_validator("product_requirements")
    @classmethod
    def _products_are_unique(
        cls,
        value: tuple[HoldoutProductRequirementV1, ...],
    ) -> tuple[HoldoutProductRequirementV1, ...]:
        identities = tuple((item.stage_key, item.kind, item.schema_version) for item in value)
        if not identities or len(set(identities)) != len(identities):
            raise ValueError("protocol product requirements must be nonempty and unique")
        return value


class InspectedProductV1(_ResearchModel):
    product_id: Annotated[int, Field(gt=0)]
    stage_key: Identifier
    scope_key: Identifier
    kind: Identifier
    schema_version: Annotated[int, Field(gt=0)]
    role: Literal["scientific"]
    status: Identifier
    media_type: Literal["application/json"]
    logical_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    artifact_sha256: Sha256Digest
    artifact_bytes: Annotated[int, Field(gt=0)]
    document_content_digest: Sha256Digest


class SourceWindowAuditV1(_ResearchModel):
    candidate_id: Sha256Digest
    trajectory_id: Sha256Digest
    branch_id: Sha256Digest
    source_start_sample: Annotated[int, Field(ge=0)]
    source_stop_sample: Annotated[int, Field(gt=0)]
    source_observation_count: Annotated[int, Field(ge=0)]
    source_inventory_digest: Sha256Digest
    median_source_margin: float | None
    evaluated_probe_count: Annotated[int, Field(ge=0)]
    status: Literal["eligible", "rejected"]
    reason: ReasonCode

    @field_validator("median_source_margin")
    @classmethod
    def _margin_is_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("source-window margin must be finite")
        return value

    @model_validator(mode="after")
    def _span_is_positive(self) -> Self:
        if self.source_stop_sample <= self.source_start_sample:
            raise ValueError("source window must have positive extent")
        return self


class ScopeFeasibilityAuditV1(_ResearchModel):
    scope_key: Identifier
    stream_id: Identifier
    radio_id: Identifier
    receiver_id: Annotated[int, Field(ge=0, le=255)]
    edge: Literal["lower", "upper"]
    sample_rate_hz: Annotated[int, Field(gt=0)]
    declared_sample_count: Annotated[int, Field(gt=0)]
    products: tuple[InspectedProductV1, ...]
    source_windows: tuple[SourceWindowAuditV1, ...]
    status: Literal["eligible", "no_source_supported_episode", "product_unavailable"]
    reason: ReasonCode

    @model_validator(mode="after")
    def _scope_inventory_is_unique(self) -> Self:
        product_ids = tuple(item.product_id for item in self.products)
        if len(set(product_ids)) != len(product_ids):
            raise ValueError("scope contains duplicate inspected products")
        candidate_ids = tuple(item.candidate_id for item in self.source_windows)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("scope contains duplicate source-window candidates")
        if self.status == "eligible" and not any(
            item.status == "eligible" for item in self.source_windows
        ):
            raise ValueError("eligible scope requires an eligible source window")
        return self


class SelectedUpstreamSourceV1(_ResearchModel):
    source_id: Sha256Digest
    detection_sample_start: Annotated[int, Field(ge=0)]
    detection_time_s: Annotated[float, Field(ge=0)]
    candidate_rank: Annotated[int, Field(ge=0)]
    local_epoch_sample: Annotated[int, Field(ge=0)]
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float
    canonical_observation_id: Sha256Digest
    observed_alias_index: int

    @field_validator(
        "detection_time_s", "tracking_cfo_hz", "exact_score", "control_score", "margin"
    )
    @classmethod
    def _source_values_are_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("selected source value must be finite")
        return value


class SelectedAliasTrajectoryV1(_ResearchModel):
    branch_id: Sha256Digest
    trajectory_id: Sha256Digest
    component_id: Sha256Digest
    final_alias_index: int
    polynomial_degree: Literal[1, 2, 3]
    reference_time_s: Annotated[float, Field(ge=0)]
    absolute_coefficients_hz: Annotated[tuple[float, ...], Field(min_length=2, max_length=4)]
    trajectory_start_s: Annotated[float, Field(ge=0)]
    trajectory_end_s: Annotated[float, Field(ge=0)]
    source_observation_ids: tuple[Sha256Digest, ...]
    source_ids: tuple[Sha256Digest, ...]
    source_support: tuple[SourceSupportPoint, ...]

    @field_validator("reference_time_s", "trajectory_start_s", "trajectory_end_s")
    @classmethod
    def _trajectory_values_are_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("trajectory value must be finite")
        return value

    @field_validator("absolute_coefficients_hz")
    @classmethod
    def _coefficients_are_finite(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(not math.isfinite(item) for item in value):
            raise ValueError("trajectory coefficients must be finite")
        return value

    @model_validator(mode="after")
    def _trajectory_inventory_is_closed(self) -> Self:
        if self.trajectory_end_s < self.trajectory_start_s:
            raise ValueError("selected trajectory interval is reversed")
        if len(self.absolute_coefficients_hz) != self.polynomial_degree + 1:
            raise ValueError("selected trajectory coefficient count disagrees with degree")
        if not self.source_observation_ids or not self.source_ids:
            raise ValueError("selected trajectory requires source membership")
        if len(set(self.source_observation_ids)) != len(self.source_observation_ids):
            raise ValueError("source observation IDs must be unique")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("source IDs must be unique")
        if self.source_observation_ids != tuple(
            item.observation_id for item in self.source_support
        ) or self.source_ids != tuple(item.source_id for item in self.source_support):
            raise ValueError("selected trajectory source support disagrees with its IDs")
        return self


class FrameMaskDispositionV1(_ResearchModel):
    frame_start_sample: Annotated[int, Field(ge=1)]
    reference_sample: Annotated[float, Field(gt=0)]
    continuity_segment_id: int | None
    status: Literal["supported", "unsupported"]
    rejection_reasons: tuple[ReasonCode, ...]
    even_absolute_cfo_hz: float | None
    even_frequency_uncertainty_hz: float | None
    even_exact_coherence: float | None
    even_control_coherence: float | None
    even_coherence_margin: float | None
    even_search_boundary: bool

    @field_validator(
        "reference_sample",
        "even_absolute_cfo_hz",
        "even_frequency_uncertainty_hz",
        "even_exact_coherence",
        "even_control_coherence",
        "even_coherence_margin",
    )
    @classmethod
    def _frame_values_are_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("frame-mask value must be finite")
        return value

    @model_validator(mode="after")
    def _frame_status_is_consistent(self) -> Self:
        measurements = (
            self.even_absolute_cfo_hz,
            self.even_frequency_uncertainty_hz,
            self.even_exact_coherence,
            self.even_control_coherence,
            self.even_coherence_margin,
        )
        if self.status == "supported":
            if (
                self.rejection_reasons
                or self.continuity_segment_id is None
                or any(item is None for item in measurements)
            ):
                raise ValueError("supported frame requires complete even evidence")
        elif not self.rejection_reasons:
            raise ValueError("unsupported frame requires an explicit reason")
        return self


class DerivedHoldoutEpisodeV1(_ResearchModel):
    episode_id: Sha256Digest
    scope_key: Identifier
    stream_id: Identifier
    radio_id: Identifier
    receiver_id: Annotated[int, Field(ge=0, le=255)]
    edge: Literal["lower", "upper"]
    device_sample_start: Annotated[int, Field(ge=0)]
    device_sample_stop: Annotated[int, Field(gt=0)]
    frame_epoch_sample: Annotated[int, Field(ge=0)]
    source: SelectedUpstreamSourceV1
    alias_trajectory: SelectedAliasTrajectoryV1
    frame_opportunity_count: Annotated[int, Field(gt=0)]
    supported_frame_count: Annotated[int, Field(ge=0)]
    support_fraction: Annotated[float, Field(ge=0, le=1)]
    maximum_contiguous_supported_frames: Annotated[int, Field(ge=0)]
    frame_mask_digest: Sha256Digest
    frame_mask: tuple[FrameMaskDispositionV1, ...]
    status: Literal["evaluable", "non_evaluable"]
    reason: ReasonCode

    @model_validator(mode="after")
    def _episode_is_closed(self) -> Self:
        if self.device_sample_stop <= self.device_sample_start:
            raise ValueError("episode device interval is reversed")
        starts = tuple(item.frame_start_sample for item in self.frame_mask)
        if starts != tuple(sorted(set(starts))):
            raise ValueError("frame mask must be uniquely sample-ordered")
        supported = sum(item.status == "supported" for item in self.frame_mask)
        if self.frame_opportunity_count != len(self.frame_mask) or supported != (
            self.supported_frame_count
        ):
            raise ValueError("episode frame accounting is inconsistent")
        expected_fraction = supported / len(self.frame_mask)
        if not math.isclose(self.support_fraction, expected_fraction, abs_tol=1e-15):
            raise ValueError("episode support fraction disagrees with its mask")
        if self.frame_mask_digest != canonical_digest(
            [item.model_dump(mode="json") for item in self.frame_mask]
        ):
            raise ValueError("episode frame-mask digest does not match")
        identity = {
            "scope_key": self.scope_key,
            "stream_id": self.stream_id,
            "radio_id": self.radio_id,
            "receiver_id": self.receiver_id,
            "edge": self.edge,
            "device_sample_start": self.device_sample_start,
            "device_sample_stop": self.device_sample_stop,
            "frame_epoch_sample": self.frame_epoch_sample,
            "source": self.source.model_dump(mode="json"),
            "alias_trajectory": self.alias_trajectory.model_dump(mode="json"),
        }
        if self.episode_id != canonical_digest(identity):
            raise ValueError("episode identity digest does not match")
        return self


class HoldoutCaptureDispositionV1(_ResearchModel):
    session_id: Identifier
    recording_manifest_sha256: Sha256Digest
    analysis_run_id: Identifier
    analysis_manifest_sha256: Sha256Digest
    recording_manifest_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    analysis_manifest_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    raw_integrity_attestation_id: Identifier
    scopes: tuple[ScopeFeasibilityAuditV1, ...]
    episode: DerivedHoldoutEpisodeV1 | None
    status: Literal["evaluable", "non_evaluable"]
    failure_stage: Literal[
        "none",
        "recording_manifest",
        "analysis_manifest",
        "path_products",
        "source_selection",
        "even_mask",
    ]
    reason: ReasonCode

    @model_validator(mode="after")
    def _capture_disposition_is_closed(self) -> Self:
        scope_ids = tuple(item.scope_key for item in self.scopes)
        if len(set(scope_ids)) != len(scope_ids):
            raise ValueError("capture scope audit contains duplicates")
        if self.status == "evaluable":
            if self.episode is None or self.episode.status != "evaluable":
                raise ValueError("evaluable capture requires one evaluable episode")
            if self.failure_stage != "none":
                raise ValueError("evaluable capture cannot report a failure stage")
        elif self.failure_stage == "none":
            raise ValueError("non-evaluable capture requires a failure stage")
        if self.episode is not None and self.episode.scope_key not in set(scope_ids):
            raise ValueError("selected episode is absent from the inspected scopes")
        return self


class DopplerHoldoutDerivedManifestV1(_ResearchModel):
    schema: Literal[  # type: ignore[assignment]
        "org.leo.research.doppler-holdout-derived-manifest/v1"
    ]
    phase: Literal["feasibility_only"]
    protocol_repository_commit: GitCommit
    dataset_policy_repository_commit: GitCommit
    dataset_policy_sha256: Sha256Digest
    protocol_configuration_sha256: Sha256Digest
    selector_implementation_sha256: Sha256Digest
    even_estimator_implementation_sha256: Sha256Digest
    manifest_contract_implementation_sha256: Sha256Digest
    inventory_sha256: Sha256Digest
    experiment_role: Literal["holdout_foundation"]
    future_odd_qin_outcomes_opened: Literal[False]
    candidate_estimators_run: Literal[False]
    upstream_source_and_epoch_conditioning: Literal[
        "frozen-standard-products-may-use-all-qin-for-source-alias-trajectory-and-epoch"
    ]
    guarded_full_frame_iq_loaded: Literal[True]
    odd_qin_symbols_demodulated_or_scored: Literal[False]
    capture_count: Literal[15]
    evaluable_capture_count: Annotated[int, Field(ge=0, le=15)]
    minimum_evaluable_capture_count: Annotated[int, Field(gt=0, le=15)]
    launch_gate: Literal["pass", "fail"]
    runtime_seconds: Annotated[float, Field(ge=0)]
    captures: tuple[HoldoutCaptureDispositionV1, ...]
    manifest_digest: Sha256Digest

    @field_validator("runtime_seconds")
    @classmethod
    def _runtime_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("manifest runtime must be finite")
        return value

    @model_validator(mode="after")
    def _manifest_accounting_is_closed(self) -> Self:
        sessions = tuple(item.session_id for item in self.captures)
        if len(self.captures) != self.capture_count or len(set(sessions)) != len(sessions):
            raise ValueError("holdout manifest must contain 15 unique capture dispositions")
        evaluable = sum(item.status == "evaluable" for item in self.captures)
        if evaluable != self.evaluable_capture_count:
            raise ValueError("holdout evaluable count disagrees with capture dispositions")
        expected_gate = "pass" if evaluable >= self.minimum_evaluable_capture_count else "fail"
        if self.launch_gate != expected_gate:
            raise ValueError("holdout launch gate disagrees with evaluability")
        content = self.model_dump(mode="json", exclude={"manifest_digest"})
        if self.manifest_digest != canonical_digest(content):
            raise ValueError("holdout manifest content digest does not match")
        return self


class SourceSupportPoint(_ResearchModel):
    source_id: Sha256Digest
    observation_id: Sha256Digest
    sample_start: Annotated[int, Field(ge=0)]
    margin: float

    @field_validator("margin")
    @classmethod
    def _finite_margin(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("source support margin must be finite")
        return value


def load_holdout_protocol(payload: bytes) -> DopplerHoldoutFeasibilityProtocolV1:
    """Parse one duplicate-key-free protocol document."""

    document = json.loads(payload, object_pairs_hook=_unique_object)
    return DopplerHoldoutFeasibilityProtocolV1.model_validate(document)


def load_derived_holdout_manifest(payload: bytes) -> DopplerHoldoutDerivedManifestV1:
    """Parse one duplicate-key-free derived holdout manifest."""

    document = json.loads(payload, object_pairs_hook=_unique_object)
    return DopplerHoldoutDerivedManifestV1.model_validate(document)


def validate_protocol_authority(
    protocol: DopplerHoldoutFeasibilityProtocolV1,
    policy: DopplerDatasetPolicy,
    *,
    policy_sha256: str,
) -> None:
    """Bind a frozen feasibility protocol to the exact capture policy."""

    role = policy.role(protocol.experiment_role)
    if protocol.dataset_policy_repository_commit != ("2e17b4477b38494e14bab7ff39303cf3a219bb03"):
        raise ValueError("protocol is not based on the reviewed dataset-policy commit")
    if protocol.dataset_policy_sha256 != policy_sha256:
        raise ValueError("protocol dataset-policy bytes disagree")
    if protocol.expected_capture_ids != role.capture_ids:
        raise ValueError("protocol capture cohort disagrees with the exact role allowlist")
    if protocol.minimum_evaluable_capture_count != role.minimum_evaluable_capture_count:
        raise ValueError("protocol evaluability gate disagrees with dataset policy")


def validate_derived_holdout_manifest(
    manifest: DopplerHoldoutDerivedManifestV1,
    protocol: DopplerHoldoutFeasibilityProtocolV1,
    policy: DopplerDatasetPolicy,
) -> None:
    """Validate capture, product, mask, and response-blind closure."""

    if tuple(item.session_id for item in manifest.captures) != protocol.expected_capture_ids:
        raise ValueError("derived manifest capture order or membership changed")
    if (
        manifest.dataset_policy_repository_commit != protocol.dataset_policy_repository_commit
        or manifest.dataset_policy_sha256 != protocol.dataset_policy_sha256
        or manifest.minimum_evaluable_capture_count != protocol.minimum_evaluable_capture_count
    ):
        raise ValueError("derived manifest authority disagrees with protocol")
    consumed: list[CaptureBinding] = []
    required_products = {
        (item.stage_key, item.kind, item.schema_version) for item in protocol.product_requirements
    }
    for disposition in manifest.captures:
        capture = policy.capture(disposition.session_id)
        if (
            disposition.recording_manifest_sha256 != capture.recording_manifest_sha256
            or disposition.analysis_run_id != capture.analysis_run_id
            or disposition.analysis_manifest_sha256 != capture.analysis_manifest_sha256
        ):
            raise ValueError(f"derived capture binding drifted: {disposition.session_id}")
        consumed.append(capture)
        for scope in disposition.scopes:
            actual_products = {
                (item.stage_key, item.kind, item.schema_version) for item in scope.products
            }
            if not actual_products <= required_products:
                raise ValueError("scope inspected a product outside the frozen protocol")
            if scope.status != "product_unavailable" and actual_products != required_products:
                raise ValueError("inspected scope does not bind the complete product inventory")
        episode = disposition.episode
        if episode is None:
            continue
        mask = protocol.even_qin_mask
        if (
            episode.frame_opportunity_count < mask.minimum_frame_opportunities
            or episode.supported_frame_count < mask.minimum_supported_frames
            or episode.support_fraction < mask.minimum_support_fraction
            or episode.maximum_contiguous_supported_frames
            < mask.minimum_contiguous_supported_frames
        ) != (episode.status == "non_evaluable"):
            raise ValueError("episode status disagrees with frozen even-mask thresholds")
    authorize_consumed_inputs(
        policy,
        experiment_role=protocol.experiment_role,
        inputs=consumed,
    )


def best_source_supported_window(
    points: Sequence[SourceSupportPoint],
    *,
    sample_rate_hz: int,
    probe_samples: int,
    selector: SourceEpisodeSelectorV1,
) -> tuple[SourceSupportPoint, ...]:
    """Return the best source-bounded window without consulting response data."""

    if sample_rate_hz <= 0 or probe_samples <= 0:
        raise ValueError("source-window geometry must be positive")
    ordered = tuple(sorted(points, key=lambda item: (item.sample_start, item.source_id)))
    starts = tuple(item.sample_start for item in ordered)
    if len(set(starts)) != len(starts):
        raise ValueError("source support points must have unique sample starts")
    maximum_gap = round(selector.maximum_source_gap_ms * sample_rate_hz / 1_000.0)
    minimum_span = round(selector.minimum_episode_duration_ms * sample_rate_hz / 1_000.0)
    maximum_span = round(selector.maximum_episode_duration_ms * sample_rate_hz / 1_000.0)
    runs: list[tuple[SourceSupportPoint, ...]] = []
    begin = 0
    for index in range(1, len(ordered)):
        if ordered[index].sample_start - ordered[index - 1].sample_start > maximum_gap:
            runs.append(ordered[begin:index])
            begin = index
    if ordered:
        runs.append(ordered[begin:])

    candidates: list[tuple[SourceSupportPoint, ...]] = []
    for run in runs:
        stop_index = 0
        for start_index in range(len(run)):
            stop_index = max(stop_index, start_index)
            while (
                stop_index + 1 < len(run)
                and run[stop_index + 1].sample_start + probe_samples - run[start_index].sample_start
                <= maximum_span
            ):
                stop_index += 1
            candidate = run[start_index : stop_index + 1]
            duration = candidate[-1].sample_start + probe_samples - candidate[0].sample_start
            if (
                len(candidate) >= selector.minimum_source_observation_count
                and minimum_span <= duration <= maximum_span
            ):
                candidates.append(candidate)
    if not candidates:
        return ()

    def rank(window: tuple[SourceSupportPoint, ...]) -> tuple[object, ...]:
        duration = window[-1].sample_start + probe_samples - window[0].sample_start
        margins = sorted(item.margin for item in window)
        middle = len(margins) // 2
        median = (
            margins[middle] if len(margins) % 2 else 0.5 * (margins[middle - 1] + margins[middle])
        )
        return (-len(window), -duration, -median, window[0].sample_start, window[0].source_id)

    return min(candidates, key=rank)


def frame_opportunity_starts(
    *,
    epoch_sample: int,
    sample_rate_hz: int,
    device_sample_start: int,
    device_sample_stop: int,
    frame_content_samples: int,
    frame_rate_hz: float = 750.0,
) -> tuple[int, ...]:
    """Construct the fixed frame lattice inside one source-bounded device span."""

    if (
        epoch_sample < 0
        or sample_rate_hz <= 0
        or device_sample_start < 0
        or device_sample_stop <= device_sample_start
        or frame_content_samples <= 0
        or not math.isfinite(frame_rate_hz)
        or frame_rate_hz <= 0
    ):
        raise ValueError("frame opportunity geometry is invalid")
    period = sample_rate_hz / frame_rate_hz
    first = math.ceil((device_sample_start - epoch_sample) / period)
    last = math.floor((device_sample_stop - frame_content_samples - epoch_sample) / period)
    starts = tuple(epoch_sample + round(index * period) for index in range(first, last + 1))
    if starts != tuple(sorted(set(starts))):
        raise ValueError("rounded frame lattice is not unique and ordered")
    return starts


def maximum_contiguous_supported(statuses: Sequence[bool]) -> int:
    """Return the longest consecutive run of supported mask rows."""

    maximum = 0
    current = 0
    for supported in statuses:
        current = current + 1 if supported else 0
        maximum = max(maximum, current)
    return maximum


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
