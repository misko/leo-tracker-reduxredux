"""Blinded unknown-identity challenge over exact joint correction hypotheses.

This additive lane is deliberately partial.  It can compare target-position
likelihoods only among fully assigned, navigation-eligible hypotheses.  The
prior mass of null, expired, or otherwise unevaluable hypotheses remains
unresolved and is never given a fabricated target likelihood.
"""

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
    EarthAltitudeConstraintV1,
    LocalEcefGaussianPriorV1,
    PositionEstimateReasonCode,
    PositionObservationSetRefV1,
    PositionPosteriorModeV1,
)
from leo.contracts.satellite_pnt_hypotheses import SatelliteCorrectionHypothesisSetV1
from leo.contracts.standard_pipeline import StandardScientificStatus


class JointCorrectionNavigationLane(StrEnum):
    UNKNOWN_IDENTITY_JOINT_CORRECTION_SET = "unknown_identity_joint_correction_set"


class BlindedPositionJointCorrectionChallengeV3(ContractModel):
    schema_version: Literal[3] = 3
    kind: Literal["blinded-position-joint-correction-challenge"] = (
        "blinded-position-joint-correction-challenge"
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
    lane: Literal[JointCorrectionNavigationLane.UNKNOWN_IDENTITY_JOINT_CORRECTION_SET] = (
        JointCorrectionNavigationLane.UNKNOWN_IDENTITY_JOINT_CORRECTION_SET
    )
    candidate_state_bank_digest: Sha256Digest
    correction_hypothesis_set: SatelliteCorrectionHypothesisSetV1
    truth_access_policy: Literal["truth-inaccessible-until-estimate-sealed-v1"] = (
        "truth-inaccessible-until-estimate-sealed-v1"
    )
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _challenge_is_closed(self) -> Self:
        family = SatelliteCorrectionHypothesisSetV1.model_validate(
            self.correction_hypothesis_set.model_dump(mode="json")
        )
        keys = tuple(_observation_key(item) for item in self.observations)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("joint position observations must be unique and ordered")
        if len({item.product_digest for item in self.observations}) != len(self.observations):
            raise ValueError("joint target observation product digests must be unique")
        if len({item.source_binding_digest for item in self.observations}) != len(
            self.observations
        ):
            raise ValueError("joint target observation bindings must be unique")
        if any(
            item.source_fingerprint_authority_digest != self.source_fingerprint_authority_digest
            for item in self.observations
        ):
            raise ValueError("joint target fingerprints use the wrong authority namespace")
        _validate_nonoverlapping_observations(self.observations)
        expected_evidence = canonical_digest(
            tuple(item.model_dump(mode="json") for item in self.observations)
        )
        if self.target_evidence_digest != expected_evidence:
            raise ValueError("joint target evidence digest does not match observations")
        target_start = min(item.start_utc_ns for item in self.observations)
        target_end = max(item.end_utc_ns for item in self.observations)
        if not any(
            item.start_utc_ns <= self.reference_utc_ns < item.end_utc_ns
            for item in self.observations
        ):
            raise ValueError("joint position reference must lie inside target evidence")
        latest_product_time = max(
            slot.correction_product.produced_utc_ns for slot in family.source_slots
        )
        if target_start < latest_product_time or self.created_utc_ns < target_end:
            raise ValueError("joint target/challenge chronology predates frozen inputs")

        protected = {
            self.protocol_digest,
            self.truth_commitment_digest,
            self.target_evidence_digest,
            self.source_fingerprint_authority_digest,
            self.candidate_state_bank_digest,
            family.content_digest,
            family.jointing_protocol_digest,
        }
        for slot in family.source_slots:
            product = slot.correction_product
            if (
                product.source_fingerprint_authority_digest
                != self.source_fingerprint_authority_digest
            ):
                raise ValueError(
                    "joint calibration and target fingerprints need one authority namespace"
                )
            protected.update(
                {
                    product.content_digest,
                    product.calibration_protocol_digest,
                    product.calibration_evidence_digest,
                    product.association_hypothesis_digest,
                    product.tle_snapshot.digest,
                    product.tle_membership_authority_digest,
                    *(mode.mode_digest for mode in product.modes),
                }
            )
            for target in self.observations:
                for calibration in product.calibration_source_spans:
                    if _spans_overlap(target, calibration):
                        raise ValueError("joint target and calibration samples must be disjoint")
                    if (
                        _same_source_stream(target, calibration)
                        and target.source_sample_start < calibration.source_sample_stop
                    ):
                        raise ValueError(
                            "joint target samples must follow shared-stream calibration"
                        )
        if self.prior.prior_provenance_digest in protected:
            raise ValueError("joint position prior is not response-isolated")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("joint blinded-position challenge digest does not match content")
        return self


class BlindedPositionJointCorrectionEstimateV3(ContractModel):
    schema_version: Literal[3] = 3
    kind: Literal["blinded-position-joint-correction-estimate"] = (
        "blinded-position-joint-correction-estimate"
    )
    challenge_id: Identifier
    challenge_group_id: Identifier
    challenge_content_digest: Sha256Digest
    truth_commitment_digest: Sha256Digest
    lane: Literal[JointCorrectionNavigationLane.UNKNOWN_IDENTITY_JOINT_CORRECTION_SET] = (
        JointCorrectionNavigationLane.UNKNOWN_IDENTITY_JOINT_CORRECTION_SET
    )
    reference_utc_ns: Annotated[int, Field(gt=0)]
    consumed_correction_hypothesis_set_digest: Sha256Digest
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
    target_likelihood_compared_to_unresolved: Literal[False] = False
    posterior_conditioning: Literal[
        "target-likelihood-normalized-within-fully-assigned-eligible-family-v1"
    ] = "target-likelihood-normalized-within-fully-assigned-eligible-family-v1"
    identity_claimed: Literal[False] = False
    truth_accessed: Literal[False] = False
    truth_metrics_included: Literal[False] = False
    content_digest: Sha256Digest

    @field_validator(
        "conditioning_event_prior_probability",
        "unresolved_probability",
    )
    @classmethod
    def _finite_probability(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("joint position probabilities must be finite")
        return value

    @model_validator(mode="after")
    def _estimate_is_closed(self) -> Self:
        if (
            self.evaluated_hypothesis_count + self.unevaluable_hypothesis_count
            != self.source_hypothesis_count
            or self.evaluated_hypothesis_count != len(self.modes)
        ):
            raise ValueError("joint position hypothesis accounting is inconsistent")
        if tuple(item.rank for item in self.modes) != tuple(range(1, len(self.modes) + 1)):
            raise ValueError("joint position modes need contiguous ranks")
        if len({item.mode_id for item in self.modes}) != len(self.modes):
            raise ValueError("joint position mode identities must be unique")
        probabilities = tuple(item.posterior_probability for item in self.modes)
        if any(right > left for left, right in zip(probabilities, probabilities[1:], strict=False)):
            raise ValueError("joint position modes must be ordered by probability")
        if not math.isclose(
            math.fsum(probabilities),
            self.conditioning_event_prior_probability,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("joint returned posterior mass does not match conditioning mass")
        if not math.isclose(
            self.unresolved_probability,
            1.0 - self.conditioning_event_prior_probability,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("joint unresolved mass does not match unevaluable prior mass")
        if self.modes[0].mode_id != self.reported_mode_id:
            raise ValueError("joint reported mode must be rank one")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("joint blinded-position estimate digest does not match content")
        return self


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
                raise ValueError("joint target sample spans must not overlap")
            if item.start_utc_ns < previous[1]:
                raise ValueError("joint target sample and UTC order must agree")
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
