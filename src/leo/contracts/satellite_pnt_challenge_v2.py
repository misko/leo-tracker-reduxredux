"""Truth-free oracle correction-set challenge and estimate contracts.

These contracts are additive to the V1 single-emitter-product challenge.  They
exist because a set of simultaneous satellites is not a probability simplex of
alternative identities.  The solver sees only the safe correction set, target
observation references, a broad precommitted local prior, and a salted truth
commitment.  Receiver truth and reveal artifacts are intentionally absent from
this module.
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
from leo.contracts.satellite_pnt_sets import SatelliteCorrectionSetV1
from leo.contracts.standard_pipeline import StandardScientificStatus


class CorrectionSetNavigationLane(StrEnum):
    ORACLE_IDENTITY_CORRECTION_SET = "oracle_identity_correction_set"


class BlindedPositionCorrectionSetChallengeV2(ContractModel):
    """Complete solver-visible V2 challenge; receiver truth is absent."""

    schema_version: Literal[2] = 2
    kind: Literal["blinded-position-correction-set-challenge"] = (
        "blinded-position-correction-set-challenge"
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
    lane: Literal[CorrectionSetNavigationLane.ORACLE_IDENTITY_CORRECTION_SET] = (
        CorrectionSetNavigationLane.ORACLE_IDENTITY_CORRECTION_SET
    )
    oracle_assignment_digest: Sha256Digest
    correction_set: SatelliteCorrectionSetV1
    truth_access_policy: Literal["truth-inaccessible-until-estimate-sealed-v1"] = (
        "truth-inaccessible-until-estimate-sealed-v1"
    )
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _challenge_is_closed(self) -> Self:
        correction_set = SatelliteCorrectionSetV1.model_validate(
            self.correction_set.model_dump(mode="json")
        )
        keys = tuple(_observation_key(item) for item in self.observations)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("position observation references must be unique and ordered")
        product_digests = tuple(item.product_digest for item in self.observations)
        source_bindings = tuple(item.source_binding_digest for item in self.observations)
        if len(set(product_digests)) != len(product_digests):
            raise ValueError("target observation product digests must be unique")
        if len(set(source_bindings)) != len(source_bindings):
            raise ValueError("target observation source bindings must be unique")
        if any(
            item.source_fingerprint_authority_digest != self.source_fingerprint_authority_digest
            for item in self.observations
        ):
            raise ValueError("target source fingerprints use the wrong authority namespace")
        _validate_nonoverlapping_observations(self.observations)
        expected_evidence = canonical_digest(
            tuple(item.model_dump(mode="json") for item in self.observations)
        )
        if self.target_evidence_digest != expected_evidence:
            raise ValueError("target evidence digest does not match observation references")
        target_start = min(item.start_utc_ns for item in self.observations)
        target_end = max(item.end_utc_ns for item in self.observations)
        if not any(
            item.start_utc_ns <= self.reference_utc_ns < item.end_utc_ns
            for item in self.observations
        ):
            raise ValueError("position reference instant must lie inside target observations")
        if target_start < correction_set.produced_utc_ns:
            raise ValueError("target observations cannot predate correction-set production")
        if self.created_utc_ns < max(correction_set.produced_utc_ns, target_end):
            raise ValueError("challenge must follow correction production and target evidence")
        if (
            target_start < correction_set.valid_from_utc_ns
            or target_end > correction_set.valid_until_utc_ns
        ):
            raise ValueError("target observations fall outside correction-set validity")

        protected_digests = {
            self.protocol_digest,
            self.truth_commitment_digest,
            self.target_evidence_digest,
            self.source_fingerprint_authority_digest,
            self.oracle_assignment_digest,
            correction_set.content_digest,
            correction_set.selection_authority_digest,
        }
        for member in correction_set.members:
            product = member.correction_product
            protected_digests.update(
                {
                    member.selection_evidence_digest,
                    product.content_digest,
                    product.calibration_protocol_digest,
                    product.calibration_evidence_digest,
                    product.association_hypothesis_digest,
                    product.tle_snapshot.digest,
                    product.tle_membership_authority_digest,
                    member.selected_mode_digest,
                }
            )
        for target in self.observations:
            protected_digests.update(
                {
                    target.product_digest,
                    target.source_binding_digest,
                    target.source_recording_fingerprint,
                }
            )
            for member in correction_set.members:
                product = member.correction_product
                if (
                    product.source_fingerprint_authority_digest
                    != self.source_fingerprint_authority_digest
                ):
                    raise ValueError(
                        "calibration and target fingerprints need one authority namespace"
                    )
                for calibration in product.calibration_source_spans:
                    if _spans_overlap(target, calibration):
                        raise ValueError("target and calibration raw-source spans must be disjoint")
                    if (
                        _same_source_stream(target, calibration)
                        and target.source_sample_start < calibration.source_sample_stop
                    ):
                        raise ValueError(
                            "target raw samples must follow calibration on a shared source stream"
                        )
        if self.prior.prior_provenance_digest in protected_digests:
            raise ValueError("position-prior provenance is not response-isolated")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("V2 blinded-position challenge digest does not match content")
        return self


class BlindedPositionCorrectionSetEstimateV2(ContractModel):
    """Truth-free position posterior bound to one correction-set challenge."""

    schema_version: Literal[2] = 2
    kind: Literal["blinded-position-correction-set-estimate"] = (
        "blinded-position-correction-set-estimate"
    )
    challenge_id: Identifier
    challenge_group_id: Identifier
    challenge_content_digest: Sha256Digest
    truth_commitment_digest: Sha256Digest
    lane: Literal[CorrectionSetNavigationLane.ORACLE_IDENTITY_CORRECTION_SET] = (
        CorrectionSetNavigationLane.ORACLE_IDENTITY_CORRECTION_SET
    )
    reference_utc_ns: Annotated[int, Field(gt=0)]
    consumed_correction_set_digest: Sha256Digest
    consumed_oracle_assignment_digest: Sha256Digest
    solver_algorithm_version: Annotated[str, Field(min_length=1, max_length=128)]
    solver_config_digest: Sha256Digest
    solver_execution_digest: Sha256Digest
    sealed_utc_ns: Annotated[int, Field(gt=0)]
    status: StandardScientificStatus
    reason_code: PositionEstimateReasonCode
    source_mode_count: Annotated[int, Field(ge=0)]
    returned_mode_count: Annotated[int, Field(ge=0, le=256)]
    truncated_mode_count: Annotated[int, Field(ge=0)]
    modes: Annotated[tuple[PositionPosteriorModeV1, ...], Field(max_length=256)]
    reported_mode_id: Sha256Digest | None
    unresolved_probability: Annotated[float, Field(ge=0.0, le=1.0)]
    truth_accessed: Literal[False] = False
    truth_metrics_included: Literal[False] = False
    content_digest: Sha256Digest

    @field_validator("unresolved_probability")
    @classmethod
    def _finite_probability(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("unresolved posterior probability must be finite")
        return value

    @model_validator(mode="after")
    def _estimate_is_closed(self) -> Self:
        if (
            len(
                {
                    self.challenge_content_digest,
                    self.truth_commitment_digest,
                    self.consumed_correction_set_digest,
                    self.consumed_oracle_assignment_digest,
                    self.solver_config_digest,
                    self.solver_execution_digest,
                }
            )
            != 6
        ):
            raise ValueError("V2 estimate evidence and solver digests must be distinct")
        if (
            self.returned_mode_count + self.truncated_mode_count != self.source_mode_count
            or self.returned_mode_count != len(self.modes)
        ):
            raise ValueError("V2 position posterior mode accounting is inconsistent")
        if tuple(item.rank for item in self.modes) != tuple(range(1, len(self.modes) + 1)):
            raise ValueError("V2 position modes must have contiguous canonical ranks")
        if len({item.mode_id for item in self.modes}) != len(self.modes):
            raise ValueError("V2 position mode identities must be unique")
        probabilities = tuple(item.posterior_probability for item in self.modes)
        if any(right > left for left, right in zip(probabilities, probabilities[1:], strict=False)):
            raise ValueError("V2 position modes must be ordered by probability")
        if not math.isclose(
            math.fsum(probabilities) + self.unresolved_probability,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("V2 position posterior probabilities must sum to one")
        reported = next(
            (item for item in self.modes if item.mode_id == self.reported_mode_id), None
        )
        if self.modes:
            if reported is None or reported.rank != 1:
                raise ValueError("V2 reported position must be the rank-one mode")
            if self.status in {
                StandardScientificStatus.NO_RESULT,
                StandardScientificStatus.INSUFFICIENT_DATA,
            }:
                raise ValueError("V2 position no-result cannot contain modes")
        elif self.reported_mode_id is not None or self.unresolved_probability != 1.0:
            raise ValueError("empty V2 position posterior must remain unresolved")
        expected_reason = (
            PositionEstimateReasonCode.POSTERIOR_MODES_AVAILABLE
            if self.modes
            else PositionEstimateReasonCode.INSUFFICIENT_TARGET_EVIDENCE
            if self.status is StandardScientificStatus.INSUFFICIENT_DATA
            else PositionEstimateReasonCode.NO_POSITION_SOLUTION
        )
        if self.reason_code is not expected_reason:
            raise ValueError("V2 position reason code does not match its result")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("V2 blinded-position estimate digest does not match content")
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
            previous_stop, previous_end_utc_ns = previous
            if item.source_sample_start < previous_stop:
                raise ValueError("target raw-source sample spans must not overlap")
            if item.start_utc_ns < previous_end_utc_ns:
                raise ValueError("target sample and UTC span order must agree")
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
