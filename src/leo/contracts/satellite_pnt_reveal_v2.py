"""Reveal-only join for the V2 correction-set navigation lane."""

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
from leo.contracts.satellite_pnt_challenge_v2 import (
    BlindedPositionCorrectionSetChallengeV2,
    BlindedPositionCorrectionSetEstimateV2,
)


class BlindedPositionCorrectionSetRevealReceiptV2(ContractModel):
    """Exact post-seal truth join; never a solver input."""

    schema_version: Literal[2] = 2
    kind: Literal["blinded-position-correction-set-reveal-receipt"] = (
        "blinded-position-correction-set-reveal-receipt"
    )
    challenge: BlindedPositionCorrectionSetChallengeV2
    estimate: BlindedPositionCorrectionSetEstimateV2
    truth: BlindedPositionTruthV1
    revealed_utc_ns: Annotated[int, Field(gt=0)]
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def _receipt_is_exact_and_chronological(self) -> Self:
        challenge = BlindedPositionCorrectionSetChallengeV2.model_validate(
            self.challenge.model_dump(mode="json")
        )
        estimate = BlindedPositionCorrectionSetEstimateV2.model_validate(
            self.estimate.model_dump(mode="json")
        )
        truth = BlindedPositionTruthV1.model_validate(self.truth.model_dump(mode="json"))
        if not (
            truth.sealed_utc_ns
            <= challenge.created_utc_ns
            <= estimate.sealed_utc_ns
            < self.revealed_utc_ns
        ):
            raise ValueError("V2 position seal and reveal chronology is invalid")
        if estimate.sealed_utc_ns < max(item.end_utc_ns for item in challenge.observations):
            raise ValueError("V2 estimate predates complete target evidence")
        if (
            truth.content_digest != challenge.truth_commitment_digest
            or truth.challenge_group_id != challenge.challenge_group_id
            or truth.target_evidence_digest != challenge.target_evidence_digest
            or truth.reference_utc_ns != challenge.reference_utc_ns
        ):
            raise ValueError("revealed truth does not match the V2 challenge commitment")
        if (
            estimate.challenge_id != challenge.challenge_id
            or estimate.challenge_group_id != challenge.challenge_group_id
            or estimate.challenge_content_digest != challenge.content_digest
            or estimate.truth_commitment_digest != challenge.truth_commitment_digest
            or estimate.reference_utc_ns != challenge.reference_utc_ns
            or estimate.consumed_correction_set_digest != challenge.correction_set.content_digest
            or estimate.consumed_oracle_assignment_digest != challenge.oracle_assignment_digest
        ):
            raise ValueError("sealed V2 estimate is not bound to this exact challenge")
        selected_by_digest = {
            member.selected_mode_digest: member.selected_catalog_number
            for member in challenge.correction_set.members
        }
        expected_mode_digests = tuple(sorted(selected_by_digest))
        expected_catalogues = tuple(sorted(selected_by_digest.values()))
        for mode in estimate.modes:
            if (
                mode.consumed_correction_mode_digests != expected_mode_digests
                or mode.associated_catalog_numbers != expected_catalogues
                or mode.association_hypothesis_digest != challenge.oracle_assignment_digest
            ):
                raise ValueError("V2 position mode does not consume the exact correction set")
        truth_ecef = _geodetic_to_ecef_m(truth.position)
        _validate_position_against_prior_and_constraint(
            truth_ecef,
            challenge.prior,
            challenge.earth_constraint,
            label="revealed V2 truth",
        )
        for mode in estimate.modes:
            _validate_position_against_prior_and_constraint(
                mode.mean_ecef_m,
                challenge.prior,
                challenge.earth_constraint,
                label="V2 position posterior mode",
            )
        if self.receipt_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"receipt_digest"})
        ):
            raise ValueError("V2 reveal receipt digest does not match content")
        return self
