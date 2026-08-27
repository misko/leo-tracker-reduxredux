"""Fail-closed protocol for the two opened POST-FIX satellite/PNT long arcs."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from leo.analysis.research.long_arc_dataset import (
    PostFixLongArcCohortV1,
    load_post_fix_long_arc_cohort,
    verify_repository_bindings,
)
from leo.contracts.digests import Sha256Digest, canonical_digest


class _ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)


class FileBindingV1(_ProtocolModel):
    path: str
    sha256: Sha256Digest

    @field_validator("path")
    @classmethod
    def _path_is_repository_relative(cls, value: str) -> str:
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
            raise ValueError("protocol file binding must be repository-relative")
        return candidate.as_posix()


class ObserverPresetV1(_ProtocolModel):
    name: Literal["spinnaker-sausalito"]
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    position_uncertainty_m: float
    capture_bound: Literal[False]
    antenna_boresight_known: Literal[False]

    @model_validator(mode="after")
    def _preset_is_exact(self) -> Self:
        if (
            self.latitude_deg,
            self.longitude_deg,
            self.altitude_m,
            self.position_uncertainty_m,
        ) != (37.858988, -122.478103, -29.0, 50.0):
            raise ValueError("observer preset does not match the frozen reviewed site")
        return self


class TleSnapshotAuthorityV1(_ProtocolModel):
    provider: Literal["space-track"]
    collected_utc_ns: Annotated[int, Field(gt=0)]
    raw_sha256: Sha256Digest
    object_count: Literal[10972]
    raw_bytes_required_before_propagation: Literal[True]
    dynamic_snapshot_selection_forbidden: Literal[True]


class ArcObservationV1(_ProtocolModel):
    arc_id: Literal[
        "long-arc-9981-r19f2-s1-rx1-upper-0-30s",
        "long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s",
    ]
    expected_observation_count: Annotated[int, Field(gt=0)]
    cfo_evidence: FileBindingV1
    timing_authority: FileBindingV1
    cfo_json_pointer: str
    cfo_time_rule: Literal[
        "probe-start-plus-uniform-50000-sample-center-v1",
        "supported-symbol-centre-mean-v1",
    ]
    window_sample_count: Literal[50000]
    sample_rate_hz: Literal[2500000]
    retain_historical_probe_start_as_sensitivity: bool
    tle_snapshot: TleSnapshotAuthorityV1
    previously_examined_catalog_number: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def _arc_specific_observation_authority(self) -> Self:
        if self.arc_id.startswith("long-arc-9981"):
            expected = (
                881,
                "/glrt/unique_observations",
                "probe-start-plus-uniform-50000-sample-center-v1",
                True,
                1787594647459418079,
                "sha256:ac36512e603e6a21bc2ca16d0512a1e14db846ccbad9409d9ac601b371f16dee",
                67930,
            )
        else:
            expected = (
                550,
                "/detections/*/(tracking_cfo_hz,detection_sample_start,local_epoch_sample)",
                "supported-symbol-centre-mean-v1",
                False,
                1787666532658586719,
                "sha256:9bb59fcf68fa36ce234ae9be79a492f0b92abc23bcf4f040bb5b64b61d3e31ad",
                59748,
            )
        actual = (
            self.expected_observation_count,
            self.cfo_json_pointer,
            self.cfo_time_rule,
            self.retain_historical_probe_start_as_sensitivity,
            self.tle_snapshot.collected_utc_ns,
            self.tle_snapshot.raw_sha256,
            self.previously_examined_catalog_number,
        )
        if actual != expected:
            raise ValueError("long-arc observation authority disagrees with frozen arc semantics")
        return self


class CandidatePopulationV1(_ProtocolModel):
    object_class: Literal["STARLINK"]
    source: Literal["complete-checksum-valid-causal-snapshot"]
    population_rule: Literal["field-specific-horizon-union-over-delta-plus-tau-support-v1"]
    minimum_elevation_deg: float
    fields_s: tuple[Literal[-500], Literal[0], Literal[500]]
    response_accessed: Literal[False]
    equal_tau_opportunity_required: Literal[True]
    population_frozen_before_response: Literal[True]
    candidate_truncation_forbidden: Literal[True]

    @model_validator(mode="after")
    def _fields_are_exact(self) -> Self:
        if self.fields_s != (-500, 0, 500) or self.minimum_elevation_deg != 0.0:
            raise ValueError("catalogue fields or horizon do not match the frozen design")
        return self


class TimeTreatmentV1(_ProtocolModel):
    primary_tau_s: float
    sensitivity_lower_s: float
    sensitivity_upper_s: float
    sensitivity_step_s: float
    expected_tau_state_count: Literal[41]
    boundary_disposition: Literal["report-abstain-no-widen"]
    wrong_epoch_fields_s: tuple[Literal[-500], Literal[500]]
    wrong_epoch_policy: Literal["observe-only-no-p-value-no-threshold-no-veto"]
    same_tau_support_for_every_field: Literal[True]
    tau_reoptimized_on_future_response: Literal[False]

    @model_validator(mode="after")
    def _tau_grid_is_closed(self) -> Self:
        count = (
            round((self.sensitivity_upper_s - self.sensitivity_lower_s) / self.sensitivity_step_s)
            + 1
        )
        if (
            self.primary_tau_s,
            self.sensitivity_lower_s,
            self.sensitivity_upper_s,
            self.sensitivity_step_s,
            self.expected_tau_state_count,
            self.wrong_epoch_fields_s,
        ) != (0.0, -5.0, 5.0, 0.25, 41, (-500, 500)) or count != 41:
            raise ValueError("time-treatment grid or fields do not match the frozen design")
        return self


class SplitAndScoringV1(_ProtocolModel):
    main_training_fraction: float
    main_future_fraction: float
    rolling_training_fractions: tuple[float, float, float]
    rolling_next_block_fraction: float
    calendar_block_duration_s: float
    split_basis: Literal["chronological-support-centred-observation-order"]
    selection_lane: Literal["training-only"]
    future_lane: Literal["freeze-candidate-tau-offset-then-score-once"]
    masks_identical_across_candidates_fields_and_models: Literal[True]
    primary_summary: Literal["equal-calendar-block-rms-hz"]
    pooled_rms_reported: Literal[True]
    overlapping_origins_are_independent_trials: Literal[False]

    @model_validator(mode="after")
    def _split_is_closed(self) -> Self:
        if not math.isclose(
            self.main_training_fraction + self.main_future_fraction,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-15,
        ) or (
            self.rolling_training_fractions,
            self.rolling_next_block_fraction,
            self.calendar_block_duration_s,
        ) != ((0.4, 0.6, 0.8), 0.2, 1.0):
            raise ValueError("chronological split does not match the frozen design")
        return self


class ModelHierarchyV1(_ProtocolModel):
    orbit_model: Literal["sgp4-received-minus-transmitted-doppler"]
    nominal_rf_hz: float
    primary_orbit_nuisance: Literal["one-training-fit-cfo-constant-per-continuity-component"]
    candidate_specific_rate_acceleration_jerk_scale_forbidden: Literal[True]
    primary_receiver_rate_sigma_hz_s: float
    diagnostic_receiver_rate_sigma_hz_s: float
    diagnostic_rate_may_change_identity: Literal[False]
    radio_only_polynomial_degrees: tuple[Literal[1], Literal[2], Literal[3]]
    radio_only_same_training_future_masks: Literal[True]
    observation_sigma_hz: float
    observation_error_model: Literal["conditional-diagonal-gaussian-after-source-collapse-v1"]
    component_offset_prior_sigma_hz: float
    numerical_scientific_thresholds: Literal["unset-development-reporting-only"]

    @model_validator(mode="after")
    def _model_hierarchy_is_exact(self) -> Self:
        if self.radio_only_polynomial_degrees != (1, 2, 3) or (
            self.nominal_rf_hz,
            self.primary_receiver_rate_sigma_hz_s,
            self.diagnostic_receiver_rate_sigma_hz_s,
            self.observation_sigma_hz,
            self.component_offset_prior_sigma_hz,
        ) != (11440312498.0, 0.0, 20.0, 50.0, 1000000.0):
            raise ValueError("radio-only hierarchy must be line, quadratic, cubic")
        return self


class RequiredOutputV1(_ProtocolModel):
    complete_candidate_inventory: Literal[True]
    winner_runner_element_epoch_and_age: Literal[True]
    tau_profiles_and_boundary_flags: Literal[True]
    training_future_and_rolling_scores: Literal[True]
    radio_only_comparison: Literal[True]
    wrong_epoch_winners_differences_and_ratios: Literal[True]
    block_level_uncertainty_and_effective_units: Literal[True]
    failure_ledger: Literal[True]
    machine_readable_evidence_and_manifest: Literal[True]
    matplotlib_figures: Literal[True]


class ClaimBoundaryV1(_ProtocolModel):
    opened_development_only: Literal[True]
    secure_norad_permitted: Literal[False]
    positioning_validation_permitted: Literal[False]
    historical_final_holdout_reinterpretation_permitted: Literal[False]
    wrong_epoch_is_null_distribution: Literal[False]
    tau_is_receiver_clock_correction: Literal[False]
    receiver_relative_cfo_is_physical_doppler_truth: Literal[False]
    new_rf_collection_authorized: Literal[False]


class ExecutionBoundaryV1(_ProtocolModel):
    status: Literal["frozen-not-executed"]
    execution_authorized: Literal[False]
    iq_accessed_during_protocol_freeze: Literal[False]
    tle_propagation_run_during_protocol_freeze: Literal[False]
    response_scored_during_protocol_freeze: Literal[False]
    blockers: tuple[
        Literal[
            "qualified-response-free-long-arc-adapter",
            "equal-opportunity-radio-polynomial-null",
            "audited-execution-amendment-with-code-hashes",
        ],
        ...,
    ]

    @model_validator(mode="after")
    def _all_execution_blockers_are_frozen(self) -> Self:
        expected = (
            "qualified-response-free-long-arc-adapter",
            "equal-opportunity-radio-polynomial-null",
            "audited-execution-amendment-with-code-hashes",
        )
        if self.blockers != expected:
            raise ValueError("protocol execution blockers must be exact and ordered")
        return self


class SatellitePntLongArcProtocolV1(_ProtocolModel):
    schema_id: Literal["org.leo.research.satellite-pnt-long-arc-development/v1"] = Field(
        alias="schema"
    )
    protocol_id: Literal["satellite-pnt-long-arc-development-v1"]
    status: Literal["frozen-development-protocol-no-execution"]
    registry: FileBindingV1
    tracking_plan: FileBindingV1
    expected_arc_ids: tuple[
        Literal["long-arc-9981-r19f2-s1-rx1-upper-0-30s"],
        Literal["long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s"],
    ]
    dynamic_discovery_forbidden: Literal[True]
    capture_or_span_substitution_forbidden: Literal[True]
    observations: tuple[ArcObservationV1, ArcObservationV1]
    observer: ObserverPresetV1
    candidate_population: CandidatePopulationV1
    time_treatment: TimeTreatmentV1
    split_and_scoring: SplitAndScoringV1
    models: ModelHierarchyV1
    required_output: RequiredOutputV1
    claim_boundary: ClaimBoundaryV1
    execution: ExecutionBoundaryV1
    protocol_digest: Sha256Digest

    @model_validator(mode="after")
    def _protocol_is_closed(self) -> Self:
        if self.expected_arc_ids != (
            "long-arc-9981-r19f2-s1-rx1-upper-0-30s",
            "long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s",
        ):
            raise ValueError("protocol arc inventory is not exact")
        if tuple(item.arc_id for item in self.observations) != self.expected_arc_ids:
            raise ValueError("protocol observation inventory does not match exact arcs")
        expected_digest = canonical_digest(
            self.model_dump(mode="json", by_alias=True, exclude={"protocol_digest"})
        )
        if self.protocol_digest != expected_digest:
            raise ValueError("long-arc protocol digest does not match semantic content")
        return self


def load_satellite_pnt_long_arc_protocol(
    path: Path, *, repository_root: Path
) -> SatellitePntLongArcProtocolV1:
    """Load and verify the frozen protocol without opening IQ or TLE bytes."""

    document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    protocol = SatellitePntLongArcProtocolV1.model_validate(document)
    root = repository_root.resolve()
    _verify_file_binding(root, protocol.registry)
    _verify_file_binding(root, protocol.tracking_plan)
    for observation in protocol.observations:
        _verify_file_binding(root, observation.cfo_evidence)
        _verify_file_binding(root, observation.timing_authority)
    cohort = load_post_fix_long_arc_cohort(_resolve(root, protocol.registry.path))
    verify_repository_bindings(cohort, root)
    _verify_protocol_against_cohort(protocol, cohort)
    return protocol


def _verify_protocol_against_cohort(
    protocol: SatellitePntLongArcProtocolV1,
    cohort: PostFixLongArcCohortV1,
) -> None:
    if cohort.authority.arc_ids != protocol.expected_arc_ids:
        raise ValueError("protocol arcs disagree with the exact long-arc registry")
    for observation in protocol.observations:
        arc = cohort.arc(observation.arc_id)
        evidence = {item.path: item.sha256 for item in arc.evidence}
        for binding in (observation.cfo_evidence, observation.timing_authority):
            if evidence.get(binding.path) != binding.sha256:
                raise ValueError("protocol observation evidence is absent from arc registry")
        if (
            arc.path.sample_rate_hz != observation.sample_rate_hz
            or arc.research_status.holdout_authority
            or arc.research_status.secure_identity_authority
        ):
            raise ValueError("protocol observation semantics disagree with arc registry")


def _verify_file_binding(root: Path, binding: FileBindingV1) -> Path:
    path = _resolve(root, binding.path)
    digest = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    if digest != binding.sha256:
        raise ValueError(f"protocol file binding digest does not match: {binding.path}")
    return path


def _resolve(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("protocol path escapes repository root") from error
    if not candidate.is_file():
        raise ValueError(f"protocol-bound file is missing: {relative}")
    return candidate


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
