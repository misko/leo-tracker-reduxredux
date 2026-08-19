"""Offline generation of empirical receiver-path acquisition centers.

The observed pilot offset contains satellite Doppler.  This module therefore
does not estimate an LNB's intrinsic error.  It builds a conservative,
content-addressed acquisition/search center for one fixed radio, RX path, and
hardware-topology epoch from a separately scheduled pre-campaign campaign.
"""

from __future__ import annotations

import math
import statistics
from typing import Annotated, Any, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.calibration import (
    CalibrationEvidenceV1,
    ReceiverFrequencyCalibrationSetV1,
    ReceiverFrequencyCalibrationV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest

SafeIdentifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


class FrequencyCalibrationPlanV1(ContractModel):
    """Predeclared design for one physical receiver-path calibration."""

    schema_version: Literal[1] = 1
    plan_id: SafeIdentifier
    plan_digest: Sha256Digest
    declared_utc_ns: Annotated[int, Field(ge=0)]
    campaign_role: Literal["pre_acceptance_frequency_calibration"] = (
        "pre_acceptance_frequency_calibration"
    )
    raw_iq_reuse_policy: Literal["forbid_acceptance_evaluation"] = (
        "forbid_acceptance_evaluation"
    )
    radio_id: SafeIdentifier
    radio_serial: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    receiver_id: Literal[1] = 1
    physical_receiver_id: SafeIdentifier
    hardware_epoch_id: SafeIdentifier
    topology_evidence_digest: Sha256Digest
    profile_name: SafeIdentifier
    profile_revision_digest: Sha256Digest
    candidate_extractor_digest: Sha256Digest
    starlink_channel: Literal["ch4"] = "ch4"
    starlink_edge: Literal["lower"] = "lower"
    center_frequency_hz: Annotated[int, Field(gt=0)]
    sample_rate_hz: Annotated[int, Field(gt=0)] = 2_500_000
    bandwidth_hz: Annotated[int, Field(gt=0)] = 2_500_000
    dwell_seconds: Literal[60] = 60
    scheduled_session_ids: tuple[SafeIdentifier, ...]
    minimum_usable_candidates: Annotated[int, Field(ge=3)] = 9
    minimum_distinct_usable_sessions: Annotated[int, Field(ge=3)] = 3
    mad_outlier_multiplier: Annotated[float, Field(gt=0)] = 4.5
    minimum_outlier_threshold_hz: Annotated[float, Field(gt=0)] = 10_000.0
    maximum_robust_sigma_hz: Annotated[float, Field(gt=0)] = 100_000.0
    multimodal_gap_hz: Annotated[float, Field(gt=0)] = 75_000.0
    multimodal_minimum_cluster_candidates: Annotated[int, Field(ge=2)] = 3
    candidate_measurement_uncertainty_hz: Annotated[float, Field(ge=0)] = 500.0
    maximum_calibration_uncertainty_hz: Annotated[float, Field(gt=0)] = 200_000.0
    pilot_occupied_half_width_hz: Annotated[float, Field(gt=0)] = 937_500.0
    residual_search_half_width_hz: Annotated[float, Field(gt=0)] = 400_000.0
    minimum_satellite_doppler_guard_hz: Annotated[float, Field(gt=0)] = 300_000.0
    validity_delay_ns: Annotated[int, Field(ge=1)] = 1

    @field_validator(
        "mad_outlier_multiplier",
        "minimum_outlier_threshold_hz",
        "maximum_robust_sigma_hz",
        "multimodal_gap_hz",
        "candidate_measurement_uncertainty_hz",
        "maximum_calibration_uncertainty_hz",
        "pilot_occupied_half_width_hz",
        "residual_search_half_width_hz",
        "minimum_satellite_doppler_guard_hz",
    )
    @classmethod
    def _finite_float(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("frequency-calibration thresholds must be finite")
        return value

    @model_validator(mode="after")
    def _validate_design_and_digest(self) -> Self:
        if len(self.scheduled_session_ids) < 3:
            raise ValueError("at least three calibration sessions must be predeclared")
        if len(set(self.scheduled_session_ids)) != len(self.scheduled_session_ids):
            raise ValueError("scheduled calibration session ids must be unique")
        if self.minimum_distinct_usable_sessions > len(self.scheduled_session_ids):
            raise ValueError("usable-session minimum exceeds scheduled sessions")
        if self.bandwidth_hz > self.sample_rate_hz:
            raise ValueError("capture bandwidth cannot exceed sample rate")
        if self.pilot_occupied_half_width_hz >= self.sample_rate_hz / 2:
            raise ValueError("pilot occupied width does not fit sampled band")
        if self.plan_digest != _digest_without(self, "plan_digest"):
            raise ValueError("frequency-calibration plan digest does not match content")
        return self

    @classmethod
    def create(cls, **values: Any) -> Self:
        document: dict[str, Any] = {"schema_version": 1, **values}
        normalized = cls.model_construct(
            plan_digest="sha256:" + "0" * 64,
            **document,
        ).model_dump(mode="json", exclude={"plan_digest"})
        return cls(plan_digest=canonical_digest(normalized), **normalized)


class FrequencyCalibrationDwellV1(ContractModel):
    """Retained outcome for every predeclared 60-second calibration dwell."""

    schema_version: Literal[1] = 1
    scheduled_index: Annotated[int, Field(ge=0)]
    session_id: SafeIdentifier
    stream_id: SafeIdentifier
    capture_purpose: Literal["frequency_calibration_only"] = "frequency_calibration_only"
    acceptance_evaluation_forbidden: Literal[True] = True
    radio_id: SafeIdentifier
    radio_serial: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    receiver_id: Literal[1] = 1
    physical_receiver_id: SafeIdentifier
    hardware_epoch_id: SafeIdentifier
    topology_evidence_digest: Sha256Digest
    manifest_digest: Sha256Digest
    profile_revision_digest: Sha256Digest
    capture_start_utc_ns: Annotated[int, Field(ge=0)]
    capture_end_utc_ns: Annotated[int, Field(gt=0)]
    sample_rate_hz: Annotated[int, Field(gt=0)]
    sample_count: Annotated[int, Field(gt=0)]
    candidate_extractor_digest: Sha256Digest
    observation_digest: Sha256Digest
    status: Literal["usable", "unusable"]
    candidate_offsets_hz: tuple[float, ...] = ()
    status_reason: Annotated[str, StringConstraints(min_length=1, max_length=512)]

    @field_validator("candidate_offsets_hz")
    @classmethod
    def _candidate_offsets_are_finite(cls, values: tuple[float, ...]) -> tuple[float, ...]:
        if any(not math.isfinite(value) for value in values):
            raise ValueError("candidate offsets must be finite")
        return values

    @model_validator(mode="after")
    def _validate_dwell(self) -> Self:
        if self.capture_end_utc_ns <= self.capture_start_utc_ns:
            raise ValueError("calibration dwell interval must be non-empty")
        if self.sample_count != self.sample_rate_hz * 60:
            raise ValueError("calibration dwell must contain exactly 60 seconds of samples")
        if self.status == "unusable" and self.candidate_offsets_hz:
            raise ValueError("unusable dwell cannot contribute candidates")
        if self.status == "usable" and not self.candidate_offsets_hz:
            raise ValueError("usable dwell must contribute at least one candidate")
        return self


class FrequencyCalibrationEvidenceV1(ContractModel):
    """Immutable audit receipt; all scheduled dwell outcomes remain visible."""

    schema_version: Literal[1] = 1
    evidence_digest: Sha256Digest
    plan: FrequencyCalibrationPlanV1
    dwells: tuple[FrequencyCalibrationDwellV1, ...]
    status: Literal["sufficient", "insufficient"]
    reasons: tuple[str, ...]
    usable_candidate_count: Annotated[int, Field(ge=0)]
    usable_session_count: Annotated[int, Field(ge=0)]
    inlier_candidate_count: Annotated[int, Field(ge=0)]
    inlier_session_count: Annotated[int, Field(ge=0)]
    rejected_outlier_count: Annotated[int, Field(ge=0)]
    empirical_center_hz: float | None
    robust_sigma_hz: float | None
    uncertainty_lower_hz: float | None
    uncertainty_upper_hz: float | None
    sampled_band_margin_hz: float | None
    residual_search_margin_hz: float | None
    method: Literal["median_mad_empirical_pilot_acquisition_center_v1"] = (
        "median_mad_empirical_pilot_acquisition_center_v1"
    )
    interpretation: Literal[
        "empirical_search_center_including_satellite_doppler_not_intrinsic_lnb_error"
    ] = "empirical_search_center_including_satellite_doppler_not_intrinsic_lnb_error"

    @model_validator(mode="after")
    def _validate_receipt(self) -> Self:
        if tuple(item.session_id for item in self.dwells) != self.plan.scheduled_session_ids:
            raise ValueError("receipt must retain every scheduled dwell in predeclared order")
        if self.status == "sufficient" and self.reasons:
            raise ValueError("sufficient calibration evidence cannot carry failure reasons")
        estimates = (
            self.empirical_center_hz,
            self.robust_sigma_hz,
            self.uncertainty_lower_hz,
            self.uncertainty_upper_hz,
            self.sampled_band_margin_hz,
            self.residual_search_margin_hz,
        )
        if self.status == "sufficient" and any(value is None for value in estimates):
            raise ValueError("sufficient evidence requires complete estimates")
        if self.status == "insufficient" and not self.reasons:
            raise ValueError("insufficient evidence requires explicit reasons")
        if self.evidence_digest != _digest_without(self, "evidence_digest"):
            raise ValueError("frequency-calibration evidence digest does not match content")
        return self


class FrequencyCalibrationGenerationV1(ContractModel):
    """Evidence plus optional accepted public calibration contracts."""

    schema_version: Literal[1] = 1
    evidence: FrequencyCalibrationEvidenceV1
    calibration: ReceiverFrequencyCalibrationV1 | None
    calibration_set: ReceiverFrequencyCalibrationSetV1 | None

    @model_validator(mode="after")
    def _accepted_outputs_follow_status(self) -> Self:
        present = self.calibration is not None and self.calibration_set is not None
        if (self.evidence.status == "sufficient") != present:
            raise ValueError("accepted calibration outputs must exactly follow evidence status")
        if self.calibration_set is not None and self.calibration_set.calibrations != (
            self.calibration,
        ):
            raise ValueError("generated calibration set must contain exactly its calibration")
        return self


def generate_frequency_calibration(
    *,
    plan: FrequencyCalibrationPlanV1,
    dwells: tuple[FrequencyCalibrationDwellV1, ...],
    calibration_id: str,
    calibration_set_id: str,
    created_utc_ns: int,
    valid_until_utc_ns: int | None = None,
) -> FrequencyCalibrationGenerationV1:
    """Evaluate a frozen campaign without reading IQ or inventing a fallback."""

    reasons: list[str] = []
    if tuple(item.session_id for item in dwells) != plan.scheduled_session_ids:
        raise ValueError("dwell evidence must match every predeclared session in order")
    if tuple(item.scheduled_index for item in dwells) != tuple(range(len(dwells))):
        raise ValueError("dwell scheduled indexes must be contiguous and ordered")

    for item in dwells:
        mismatches = (
            item.radio_id != plan.radio_id,
            item.radio_serial != plan.radio_serial,
            item.receiver_id != plan.receiver_id,
            item.physical_receiver_id != plan.physical_receiver_id,
            item.hardware_epoch_id != plan.hardware_epoch_id,
            item.topology_evidence_digest != plan.topology_evidence_digest,
            item.profile_revision_digest != plan.profile_revision_digest,
            item.candidate_extractor_digest != plan.candidate_extractor_digest,
            item.sample_rate_hz != plan.sample_rate_hz,
            item.sample_count != plan.sample_rate_hz * plan.dwell_seconds,
        )
        if any(mismatches):
            raise ValueError(f"calibration dwell {item.session_id} does not match frozen plan")
        if item.capture_start_utc_ns <= plan.declared_utc_ns:
            raise ValueError("calibration plan must predate every scheduled dwell")

    candidate_rows = [
        (offset, item.session_id)
        for item in dwells
        if item.status == "usable"
        for offset in item.candidate_offsets_hz
    ]
    usable_sessions = {session_id for _, session_id in candidate_rows}
    if len(candidate_rows) < plan.minimum_usable_candidates:
        reasons.append("minimum_usable_candidates_not_met")
    if len(usable_sessions) < plan.minimum_distinct_usable_sessions:
        reasons.append("minimum_distinct_usable_sessions_not_met")

    center: float | None = None
    robust_sigma: float | None = None
    lower: float | None = None
    upper: float | None = None
    margin: float | None = None
    residual_margin: float | None = None
    inlier_rows: list[tuple[float, str]] = []
    if candidate_rows:
        values = [row[0] for row in candidate_rows]
        initial_center = float(statistics.median(values))
        mad = float(statistics.median(abs(value - initial_center) for value in values))
        robust_sigma = 1.4826 * mad
        threshold = max(
            plan.minimum_outlier_threshold_hz,
            plan.mad_outlier_multiplier * robust_sigma,
        )
        inlier_rows = [row for row in candidate_rows if abs(row[0] - initial_center) <= threshold]
        inlier_sessions = {session_id for _, session_id in inlier_rows}
        if len(inlier_rows) < plan.minimum_usable_candidates:
            reasons.append("minimum_inlier_candidates_not_met")
        if len(inlier_sessions) < plan.minimum_distinct_usable_sessions:
            reasons.append("minimum_distinct_inlier_sessions_not_met")
        if robust_sigma > plan.maximum_robust_sigma_hz:
            reasons.append("robust_dispersion_exceeds_limit")

        # Detect a well-populated second mode before outlier removal; otherwise
        # an imbalanced second cluster could be silently labelled as outliers.
        sorted_candidates = sorted(values)
        for split in range(plan.multimodal_minimum_cluster_candidates, len(sorted_candidates)):
            if len(sorted_candidates) - split < plan.multimodal_minimum_cluster_candidates:
                continue
            if sorted_candidates[split] - sorted_candidates[split - 1] > plan.multimodal_gap_hz:
                reasons.append("multimodal_candidate_evidence")
                break

        if inlier_rows:
            inlier_values = [row[0] for row in inlier_rows]
            center = float(statistics.median(inlier_values))
            observed_radius = max(abs(value - center) for value in inlier_values)
            uncertainty = observed_radius + plan.candidate_measurement_uncertainty_hz
            lower = center - uncertainty
            upper = center + uncertainty
            if uncertainty > plan.maximum_calibration_uncertainty_hz:
                reasons.append("calibration_uncertainty_exceeds_limit")
            margin = (
                plan.sample_rate_hz / 2
                - plan.pilot_occupied_half_width_hz
                - abs(center)
                - uncertainty
                - plan.minimum_satellite_doppler_guard_hz
            )
            if margin < 0:
                reasons.append(
                    "sampled_band_does_not_cover_pilot_uncertainty_and_doppler_guard"
                )
            residual_margin = (
                plan.residual_search_half_width_hz
                - uncertainty
                - plan.minimum_satellite_doppler_guard_hz
            )
            if residual_margin < 0:
                reasons.append("residual_search_does_not_cover_uncertainty_and_doppler_guard")

    status: Literal["sufficient", "insufficient"] = "insufficient" if reasons else "sufficient"
    receipt_values: dict[str, Any] = {
        "schema_version": 1,
        "plan": plan,
        "dwells": dwells,
        "status": status,
        "reasons": tuple(dict.fromkeys(reasons)),
        "usable_candidate_count": len(candidate_rows),
        "usable_session_count": len(usable_sessions),
        "inlier_candidate_count": len(inlier_rows),
        "inlier_session_count": len({session for _, session in inlier_rows}),
        "rejected_outlier_count": len(candidate_rows) - len(inlier_rows),
        "empirical_center_hz": center,
        "robust_sigma_hz": robust_sigma,
        "uncertainty_lower_hz": lower,
        "uncertainty_upper_hz": upper,
        "sampled_band_margin_hz": margin,
        "residual_search_margin_hz": residual_margin,
        "method": "median_mad_empirical_pilot_acquisition_center_v1",
        "interpretation": (
            "empirical_search_center_including_satellite_doppler_not_intrinsic_lnb_error"
        ),
    }
    evidence = FrequencyCalibrationEvidenceV1(
        evidence_digest=canonical_digest(_jsonable(receipt_values)),
        **receipt_values,
    )
    if status == "insufficient":
        return FrequencyCalibrationGenerationV1(
            evidence=evidence,
            calibration=None,
            calibration_set=None,
        )

    assert center is not None and lower is not None and upper is not None
    last_dwell_end = max(item.capture_end_utc_ns for item in dwells)
    valid_from = last_dwell_end + plan.validity_delay_ns
    if created_utc_ns < last_dwell_end:
        raise ValueError("calibration creation time cannot predate its evidence")
    evidence_ref = CalibrationEvidenceV1(
        kind="frequency_calibration_campaign_v1",
        uri=f"qualification://frequency-calibration/{evidence.evidence_digest}",
        digest=evidence.evidence_digest,
        source_revision=None,
    )
    calibration = ReceiverFrequencyCalibrationV1.create(
        calibration_id=calibration_id,
        radio_id=plan.radio_id,
        radio_serial=plan.radio_serial,
        receiver_id=plan.receiver_id,
        physical_receiver_id=plan.physical_receiver_id,
        hardware_epoch_id=plan.hardware_epoch_id,
        center_hz=center,
        uncertainty_lower_hz=lower,
        uncertainty_upper_hz=upper,
        valid_from_utc_ns=valid_from,
        valid_until_utc_ns=valid_until_utc_ns,
        method="median_mad_empirical_pilot_acquisition_center_v1",
        created_utc_ns=created_utc_ns,
        evidence=(evidence_ref,),
    )
    calibration_set = ReceiverFrequencyCalibrationSetV1.create(
        calibration_set_id=calibration_set_id,
        calibrations=(calibration,),
    )
    return FrequencyCalibrationGenerationV1(
        evidence=evidence,
        calibration=calibration,
        calibration_set=calibration_set,
    )


def _digest_without(value: ContractModel, field: str) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={field}))


def _jsonable(value: object) -> Any:
    if isinstance(value, ContractModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value
