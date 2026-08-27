"""Reveal-only join for native joint-correction blinded positioning."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.satellite_pnt import (
    BlindedPositionTruthV1,
    _geodetic_to_ecef_m,
    _validate_position_against_prior_and_constraint,
)
from leo.contracts.satellite_pnt_native_joint_challenge import (
    BlindedPositionNativeJointCorrectionChallengeV4,
    BlindedPositionNativeJointCorrectionEstimateV4,
    native_joint_ephemeral_corrections,
)


class BlindedPositionNativeJointCorrectionRevealReceiptV4(ContractModel):
    """Bind inaccessible truth only after the native-joint estimate is sealed."""

    schema_version: Literal[4] = 4
    kind: Literal["blinded-position-native-joint-correction-reveal-receipt"] = (
        "blinded-position-native-joint-correction-reveal-receipt"
    )
    challenge: BlindedPositionNativeJointCorrectionChallengeV4
    estimate: BlindedPositionNativeJointCorrectionEstimateV4
    truth: BlindedPositionTruthV1
    revealed_utc_ns: Annotated[int, Field(gt=0)]
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def _receipt_is_exact_and_chronological(self) -> Self:
        challenge = BlindedPositionNativeJointCorrectionChallengeV4.model_validate(
            self.challenge.model_dump(mode="json")
        )
        estimate = BlindedPositionNativeJointCorrectionEstimateV4.model_validate(
            self.estimate.model_dump(mode="json")
        )
        truth = BlindedPositionTruthV1.model_validate(self.truth.model_dump(mode="json"))
        if not (
            truth.sealed_utc_ns
            <= challenge.created_utc_ns
            <= estimate.sealed_utc_ns
            < self.revealed_utc_ns
        ):
            raise ValueError("native-joint position seal and reveal chronology is invalid")
        if estimate.sealed_utc_ns < max(item.end_utc_ns for item in challenge.observations):
            raise ValueError("native-joint estimate predates target evidence completion")
        if (
            truth.content_digest != challenge.truth_commitment_digest
            or truth.challenge_group_id != challenge.challenge_group_id
            or truth.target_evidence_digest != challenge.target_evidence_digest
            or truth.reference_utc_ns != challenge.reference_utc_ns
        ):
            raise ValueError("revealed truth does not match the native-joint challenge")
        if (
            estimate.challenge_id != challenge.challenge_id
            or estimate.challenge_group_id != challenge.challenge_group_id
            or estimate.challenge_content_digest != challenge.content_digest
            or estimate.truth_commitment_digest != challenge.truth_commitment_digest
            or estimate.reference_utc_ns != challenge.reference_utc_ns
            or estimate.consumed_joint_correction_product_digest
            != challenge.joint_correction_product.content_digest
            or estimate.consumed_candidate_state_bank_digest
            != challenge.candidate_state_bank_digest
        ):
            raise ValueError("sealed native-joint estimate is not bound to this challenge")

        product = challenge.joint_correction_product
        mode_by_association = {item.association_mode_digest: item for item in product.modes}
        for position_mode in estimate.modes:
            association_digest = position_mode.association_hypothesis_digest
            joint_mode = mode_by_association.get(association_digest or "")
            if joint_mode is None:
                raise ValueError("native-joint position mode names an unknown association")
            corrections = native_joint_ephemeral_corrections(product, joint_mode)
            expected_mode_digests = tuple(item.mode_digest for item in corrections)
            if (
                position_mode.consumed_correction_mode_digests != expected_mode_digests
                or position_mode.associated_catalog_numbers != joint_mode.active_catalog_numbers
            ):
                raise ValueError(
                    "native-joint position mode does not match its exact correction mode"
                )

        truth_ecef = _geodetic_to_ecef_m(truth.position)
        _validate_position_against_prior_and_constraint(
            truth_ecef,
            challenge.prior,
            challenge.earth_constraint,
            label="revealed native-joint truth",
        )
        for mode in estimate.modes:
            _validate_position_against_prior_and_constraint(
                mode.mean_ecef_m,
                challenge.prior,
                challenge.earth_constraint,
                label="native-joint position posterior mode",
            )
        if self.receipt_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"receipt_digest"})
        ):
            raise ValueError("native-joint reveal receipt digest does not match content")
        return self
