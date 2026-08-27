"""Reveal-only join for the partial joint-correction navigation lane."""

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
from leo.contracts.satellite_pnt_joint_challenge import (
    BlindedPositionJointCorrectionChallengeV3,
    BlindedPositionJointCorrectionEstimateV3,
)


class BlindedPositionJointCorrectionRevealReceiptV3(ContractModel):
    schema_version: Literal[3] = 3
    kind: Literal["blinded-position-joint-correction-reveal-receipt"] = (
        "blinded-position-joint-correction-reveal-receipt"
    )
    challenge: BlindedPositionJointCorrectionChallengeV3
    estimate: BlindedPositionJointCorrectionEstimateV3
    truth: BlindedPositionTruthV1
    revealed_utc_ns: Annotated[int, Field(gt=0)]
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def _receipt_is_exact_and_chronological(self) -> Self:
        challenge = BlindedPositionJointCorrectionChallengeV3.model_validate(
            self.challenge.model_dump(mode="json")
        )
        estimate = BlindedPositionJointCorrectionEstimateV3.model_validate(
            self.estimate.model_dump(mode="json")
        )
        truth = BlindedPositionTruthV1.model_validate(self.truth.model_dump(mode="json"))
        if not (
            truth.sealed_utc_ns
            <= challenge.created_utc_ns
            <= estimate.sealed_utc_ns
            < self.revealed_utc_ns
        ):
            raise ValueError("joint position seal and reveal chronology is invalid")
        if estimate.sealed_utc_ns < max(item.end_utc_ns for item in challenge.observations):
            raise ValueError("joint estimate predates target evidence completion")
        if (
            truth.content_digest != challenge.truth_commitment_digest
            or truth.challenge_group_id != challenge.challenge_group_id
            or truth.target_evidence_digest != challenge.target_evidence_digest
            or truth.reference_utc_ns != challenge.reference_utc_ns
        ):
            raise ValueError("revealed truth does not match the joint challenge")
        if (
            estimate.challenge_id != challenge.challenge_id
            or estimate.challenge_group_id != challenge.challenge_group_id
            or estimate.challenge_content_digest != challenge.content_digest
            or estimate.truth_commitment_digest != challenge.truth_commitment_digest
            or estimate.reference_utc_ns != challenge.reference_utc_ns
            or estimate.consumed_correction_hypothesis_set_digest
            != challenge.correction_hypothesis_set.content_digest
            or estimate.consumed_candidate_state_bank_digest
            != challenge.candidate_state_bank_digest
        ):
            raise ValueError("sealed joint estimate is not bound to this exact challenge")

        family = challenge.correction_hypothesis_set
        hypotheses = {item.hypothesis_digest: item for item in family.hypotheses}
        mode_by_digest = {
            mode.mode_digest: mode
            for slot in family.source_slots
            for mode in slot.correction_product.modes
        }
        for position_mode in estimate.modes:
            association_digest = position_mode.association_hypothesis_digest
            association = hypotheses.get(association_digest or "")
            if association is None:
                raise ValueError("joint position mode names an unknown association")
            expected_mode_digests = tuple(
                sorted(
                    assignment.selected_mode_digest
                    for assignment in association.assignments
                    if assignment.selected_mode_digest is not None
                )
            )
            expected_catalogues = tuple(
                sorted(mode_by_digest[item].catalog_number for item in expected_mode_digests)
            )
            if (
                position_mode.consumed_correction_mode_digests != expected_mode_digests
                or position_mode.associated_catalog_numbers != expected_catalogues
            ):
                raise ValueError(
                    "joint position mode does not match its exact association hypothesis"
                )
        truth_ecef = _geodetic_to_ecef_m(truth.position)
        _validate_position_against_prior_and_constraint(
            truth_ecef,
            challenge.prior,
            challenge.earth_constraint,
            label="revealed joint truth",
        )
        for mode in estimate.modes:
            _validate_position_against_prior_and_constraint(
                mode.mean_ecef_m,
                challenge.prior,
                challenge.earth_constraint,
                label="joint position posterior mode",
            )
        if self.receipt_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"receipt_digest"})
        ):
            raise ValueError("joint reveal receipt digest does not match content")
        return self
