"""Blinded navigation over native joint satellite-correction modes."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier
from leo.contracts.satellite_pnt import (
    CalibrationSourceSpanV1,
    CorrectionEvidenceClass,
    CorrectionExpiryReason,
    EarthAltitudeConstraintV1,
    LocalEcefGaussianPriorV1,
    PositionEstimateReasonCode,
    PositionObservationSetRefV1,
    PositionPosteriorModeV1,
    SatelliteCorrectionModeV1,
    SatelliteFrequencyStateV1,
)
from leo.contracts.satellite_pnt_joint_calibration import (
    JointSatelliteCorrectionModeV1,
    JointSatelliteCorrectionProductV1,
)
from leo.contracts.standard_pipeline import StandardScientificStatus


class NativeJointCorrectionNavigationLane(StrEnum):
    UNKNOWN_IDENTITY_NATIVE_JOINT_CORRECTION = "unknown_identity_native_joint_correction"


class BlindedPositionNativeJointCorrectionChallengeV4(ContractModel):
    schema_version: Literal[4] = 4
    kind: Literal["blinded-position-native-joint-correction-challenge"] = (
        "blinded-position-native-joint-correction-challenge"
    )
    challenge_id: Identifier
    challenge_group_id: Identifier
    protocol_digest: Sha256Digest
    created_utc_ns: Annotated[int, Field(gt=0)]
    truth_commitment_digest: Sha256Digest
    truth_commitment_scheme: Literal["sha256-canonical-json-with-256-bit-nonce-v1"] = (
        "sha256-canonical-json-with-256-bit-nonce-v1"
    )
    target_evidence_digest: Sha256Digest
    source_fingerprint_authority_digest: Sha256Digest
    observations: Annotated[
        tuple[PositionObservationSetRefV1, ...], Field(min_length=1, max_length=4096)
    ]
    motion_model: Literal["stationary"] = "stationary"
    reference_utc_ns: Annotated[int, Field(gt=0)]
    prior: LocalEcefGaussianPriorV1
    earth_constraint: EarthAltitudeConstraintV1
    lane: Literal[NativeJointCorrectionNavigationLane.UNKNOWN_IDENTITY_NATIVE_JOINT_CORRECTION] = (
        NativeJointCorrectionNavigationLane.UNKNOWN_IDENTITY_NATIVE_JOINT_CORRECTION
    )
    candidate_state_bank_digest: Sha256Digest
    joint_correction_product: JointSatelliteCorrectionProductV1
    truth_access_policy: Literal["truth-inaccessible-until-estimate-sealed-v1"] = (
        "truth-inaccessible-until-estimate-sealed-v1"
    )
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _challenge_is_closed(self) -> Self:
        product = JointSatelliteCorrectionProductV1.model_validate(
            self.joint_correction_product.model_dump(mode="json")
        )
        keys = tuple(_observation_key(item) for item in self.observations)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("native-joint target observations must be unique and ordered")
        if len({item.product_digest for item in self.observations}) != len(self.observations):
            raise ValueError("native-joint observation product digests must be unique")
        if len({item.source_binding_digest for item in self.observations}) != len(
            self.observations
        ):
            raise ValueError("native-joint observation bindings must be unique")
        if any(
            item.source_fingerprint_authority_digest != self.source_fingerprint_authority_digest
            for item in self.observations
        ):
            raise ValueError("native-joint target uses the wrong source authority")
        if product.source_fingerprint_authority_digest != (
            self.source_fingerprint_authority_digest
        ):
            raise ValueError("native-joint calibration and target need one source authority")
        _validate_nonoverlapping_observations(self.observations)
        expected_evidence = canonical_digest(
            tuple(item.model_dump(mode="json") for item in self.observations)
        )
        if self.target_evidence_digest != expected_evidence:
            raise ValueError("native-joint target evidence digest is inconsistent")
        target_start = min(item.start_utc_ns for item in self.observations)
        target_end = max(item.end_utc_ns for item in self.observations)
        if not any(
            item.start_utc_ns <= self.reference_utc_ns < item.end_utc_ns
            for item in self.observations
        ):
            raise ValueError("native-joint reference must lie inside target evidence")
        if (
            target_start < product.valid_from_utc_ns
            or target_end > product.valid_until_utc_ns
            or self.created_utc_ns < target_end
        ):
            raise ValueError("native-joint target/challenge lies outside frozen validity")
        for target in self.observations:
            for calibration in product.calibration_source_spans:
                if _spans_overlap(target, calibration):
                    raise ValueError("native-joint target overlaps calibration samples")
                if (
                    _same_source_stream(target, calibration)
                    and target.source_sample_start < calibration.source_sample_stop
                ):
                    raise ValueError("native-joint target must follow shared-stream calibration")
        protected = {
            self.protocol_digest,
            self.truth_commitment_digest,
            self.target_evidence_digest,
            self.source_fingerprint_authority_digest,
            self.candidate_state_bank_digest,
            product.content_digest,
            product.calibration_protocol_digest,
            product.calibration_evidence_digest,
            product.association_result_digest,
            product.prediction_bank_digest,
            product.frequency_calibration_authority_digest,
            product.tle_snapshot.digest,
            product.tle_membership_authority_digest,
            *(item.mode_digest for item in product.modes),
        }
        if self.prior.prior_provenance_digest in protected:
            raise ValueError("native-joint position prior is not response-isolated")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("native-joint challenge digest does not match content")
        return self


class BlindedPositionNativeJointCorrectionEstimateV4(ContractModel):
    schema_version: Literal[4] = 4
    kind: Literal["blinded-position-native-joint-correction-estimate"] = (
        "blinded-position-native-joint-correction-estimate"
    )
    challenge_id: Identifier
    challenge_group_id: Identifier
    challenge_content_digest: Sha256Digest
    truth_commitment_digest: Sha256Digest
    lane: Literal[NativeJointCorrectionNavigationLane.UNKNOWN_IDENTITY_NATIVE_JOINT_CORRECTION] = (
        NativeJointCorrectionNavigationLane.UNKNOWN_IDENTITY_NATIVE_JOINT_CORRECTION
    )
    reference_utc_ns: Annotated[int, Field(gt=0)]
    consumed_joint_correction_product_digest: Sha256Digest
    consumed_candidate_state_bank_digest: Sha256Digest
    solver_algorithm_version: Annotated[str, Field(min_length=1, max_length=128)]
    solver_config_digest: Sha256Digest
    solver_execution_digest: Sha256Digest
    sealed_utc_ns: Annotated[int, Field(gt=0)]
    status: Literal[StandardScientificStatus.PARTIAL] = StandardScientificStatus.PARTIAL
    reason_code: Literal[PositionEstimateReasonCode.POSTERIOR_MODES_AVAILABLE] = (
        PositionEstimateReasonCode.POSTERIOR_MODES_AVAILABLE
    )
    source_hypothesis_count: Annotated[int, Field(gt=0)]
    evaluated_hypothesis_count: Annotated[int, Field(gt=0, le=256)]
    unevaluable_hypothesis_count: Annotated[int, Field(ge=0)]
    conditioning_event_prior_probability: Annotated[float, Field(gt=0.0, le=1.0)]
    modes: Annotated[tuple[PositionPosteriorModeV1, ...], Field(min_length=1, max_length=256)]
    reported_mode_id: Sha256Digest
    unresolved_probability: Annotated[float, Field(ge=0.0, lt=1.0)]
    minimum_data_information_rank: Literal[4] = 4
    time_diverse_two_satellite_modes_permitted: Literal[True] = True
    joint_frequency_covariance_consumed: Literal[True] = True
    target_likelihood_compared_to_unresolved: Literal[False] = False
    posterior_conditioning: Literal[
        "target-likelihood-normalized-within-full-rank-eligible-native-modes-v1"
    ] = "target-likelihood-normalized-within-full-rank-eligible-native-modes-v1"
    identity_claimed: Literal[False] = False
    truth_accessed: Literal[False] = False
    truth_metrics_included: Literal[False] = False
    content_digest: Sha256Digest

    @field_validator("conditioning_event_prior_probability", "unresolved_probability")
    @classmethod
    def _finite_probability(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("native-joint position probabilities must be finite")
        return value

    @model_validator(mode="after")
    def _estimate_is_closed(self) -> Self:
        if (
            self.evaluated_hypothesis_count + self.unevaluable_hypothesis_count
            != self.source_hypothesis_count
            or self.evaluated_hypothesis_count != len(self.modes)
        ):
            raise ValueError("native-joint hypothesis accounting is inconsistent")
        if tuple(item.rank for item in self.modes) != tuple(range(1, len(self.modes) + 1)):
            raise ValueError("native-joint position modes need contiguous ranks")
        if len({item.mode_id for item in self.modes}) != len(self.modes):
            raise ValueError("native-joint position mode identities must be unique")
        probabilities = tuple(item.posterior_probability for item in self.modes)
        if any(right > left for left, right in zip(probabilities, probabilities[1:], strict=False)):
            raise ValueError("native-joint position modes must be probability ordered")
        if not math.isclose(
            math.fsum(probabilities),
            self.conditioning_event_prior_probability,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("native-joint returned mass disagrees with conditioning")
        if not math.isclose(
            self.unresolved_probability,
            1.0 - self.conditioning_event_prior_probability,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("native-joint unresolved mass is inconsistent")
        if self.modes[0].mode_id != self.reported_mode_id:
            raise ValueError("native-joint reported mode must be rank one")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("native-joint estimate digest does not match content")
        return self


def native_joint_ephemeral_corrections(
    product: JointSatelliteCorrectionProductV1,
    mode: JointSatelliteCorrectionModeV1,
) -> tuple[SatelliteCorrectionModeV1, ...]:
    """Derive the exact solver-facing correction identities for one native mode."""

    product = JointSatelliteCorrectionProductV1.model_validate(product.model_dump(mode="json"))
    mode_by_digest = {item.mode_digest: item for item in product.modes}
    validated_mode = mode_by_digest.get(mode.mode_digest)
    if validated_mode is None or validated_mode != mode:
        raise ValueError("native joint mode is not an exact member of its product")
    corrections = []
    for state in validated_mode.satellite_states:
        frequency = SatelliteFrequencyStateV1(
            activity_epoch_id=(f"native-{state.catalog_number}-{validated_mode.mode_digest[-16:]}"),
            scope=state.frequency.scope,
            beam_channel_id=state.frequency.beam_channel_id,
            reference_utc_ns=state.frequency.reference_utc_ns,
            bias_hz=state.frequency.bias_hz,
            drift_hz_s=state.frequency.drift_hz_s,
            bias_variance_hz2=state.frequency.bias_variance_hz2,
            drift_variance_hz2_s2=state.frequency.drift_variance_hz2_s2,
            bias_drift_covariance_hz2_s=state.frequency.bias_drift_covariance_hz2_s,
        )
        payload: dict[str, object] = {
            "schema_version": 1,
            "catalog_number": state.catalog_number,
            "posterior_probability": 1.0,
            "evidence_class": CorrectionEvidenceClass.AMBIGUITY_MEMBER.value,
            "selected_element_digest": state.selected_element_digest,
            "element_epoch_utc_ns": state.element_epoch_utc_ns,
            "element_age_s_at_reference": state.element_age_s_at_reference,
            "ephemeris": state.ephemeris.model_dump(mode="json"),
            "frequency": frequency.model_dump(mode="json"),
            "valid_from_utc_ns": product.valid_from_utc_ns,
            "valid_until_utc_ns": product.valid_until_utc_ns,
            "expiry_reason": CorrectionExpiryReason.FIXED_VALIDITY_HORIZON.value,
            "navigation_eligible": validated_mode.navigation_eligible,
        }
        corrections.append(
            SatelliteCorrectionModeV1.model_validate(
                {**payload, "mode_digest": canonical_digest(payload)}
            )
        )
    return tuple(sorted(corrections, key=lambda item: item.mode_digest))


def _observation_key(item: PositionObservationSetRefV1) -> tuple[str, int, int, int, str]:
    return (
        item.source_recording_fingerprint,
        item.source_stream_index,
        item.source_sample_start,
        item.source_sample_stop,
        item.product_digest,
    )


def _validate_nonoverlapping_observations(
    observations: tuple[PositionObservationSetRefV1, ...],
) -> None:
    last_by_stream: dict[tuple[str, int], tuple[int, int]] = {}
    for item in sorted(observations, key=_observation_key):
        key = (item.source_recording_fingerprint, item.source_stream_index)
        previous = last_by_stream.get(key)
        if previous is not None:
            if item.source_sample_start < previous[0]:
                raise ValueError("native-joint target sample spans overlap")
            if item.start_utc_ns < previous[1]:
                raise ValueError("native-joint target sample and UTC order disagree")
        last_by_stream[key] = (item.source_sample_stop, item.end_utc_ns)


type _SourceSpan = PositionObservationSetRefV1 | CalibrationSourceSpanV1


def _same_source_stream(left: _SourceSpan, right: _SourceSpan) -> bool:
    return left.source_recording_fingerprint == right.source_recording_fingerprint and (
        left.source_stream_index == right.source_stream_index
    )


def _spans_overlap(left: _SourceSpan, right: _SourceSpan) -> bool:
    return (
        _same_source_stream(left, right)
        and left.source_sample_start < right.source_sample_stop
        and right.source_sample_start < left.source_sample_stop
    )
