"""Reveal-only evaluation for native joint-correction positioning."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from leo.analysis.blinded_position_evaluation import (
    BlindedPositionEvaluationError,
    PositionModeEvaluation,
    _ecef_to_enu_rotation,
    _evaluate_mode,
    _geodetic_to_ecef_m,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.satellite_pnt_native_joint_challenge import (
    NativeJointCorrectionNavigationLane,
)
from leo.contracts.satellite_pnt_native_joint_reveal import (
    BlindedPositionNativeJointCorrectionRevealReceiptV4,
)


@dataclass(frozen=True, slots=True)
class NativeJointCorrectionBlindedPositionEvaluation:
    reveal_receipt_digest: Sha256Digest
    challenge_content_digest: Sha256Digest
    estimate_content_digest: Sha256Digest
    truth_content_digest: Sha256Digest
    lane: NativeJointCorrectionNavigationLane
    reported_mode_id: Sha256Digest
    reported_mode: PositionModeEvaluation
    modes: tuple[PositionModeEvaluation, ...]
    returned_posterior_mass: float
    unresolved_probability: float
    conditional_mean_three_dimensional_error_m: float
    conditional_rms_three_dimensional_error_m: float
    target_likelihood_compared_to_unresolved: bool
    evaluation_algorithm: str = field(
        default="blinded-position-native-joint-reveal-evaluation-v1", init=False
    )
    content_digest: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if not self.modes or self.reported_mode != self.modes[0]:
            raise BlindedPositionEvaluationError(
                "native-joint evaluation requires its rank-one reported mode"
            )
        if self.target_likelihood_compared_to_unresolved:
            raise BlindedPositionEvaluationError(
                "native-joint evaluation cannot claim a null likelihood comparison"
            )
        if not math.isclose(
            self.returned_posterior_mass + self.unresolved_probability,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise BlindedPositionEvaluationError(
                "native-joint evaluation posterior accounting is not closed"
            )
        object.__setattr__(self, "content_digest", canonical_digest(self._digest_payload()))

    def _digest_payload(self) -> dict[str, object]:
        return {
            "reveal_receipt_digest": self.reveal_receipt_digest,
            "challenge_content_digest": self.challenge_content_digest,
            "estimate_content_digest": self.estimate_content_digest,
            "truth_content_digest": self.truth_content_digest,
            "lane": self.lane,
            "reported_mode_id": self.reported_mode_id,
            "mode_ids": tuple(item.mode_id for item in self.modes),
            "mode_probabilities": tuple(item.posterior_probability for item in self.modes),
            "mode_three_dimensional_errors_m": tuple(
                item.three_dimensional_error_m for item in self.modes
            ),
            "returned_posterior_mass": self.returned_posterior_mass,
            "unresolved_probability": self.unresolved_probability,
            "conditional_mean_three_dimensional_error_m": (
                self.conditional_mean_three_dimensional_error_m
            ),
            "conditional_rms_three_dimensional_error_m": (
                self.conditional_rms_three_dimensional_error_m
            ),
            "target_likelihood_compared_to_unresolved": (
                self.target_likelihood_compared_to_unresolved
            ),
            "evaluation_algorithm": self.evaluation_algorithm,
        }


def evaluate_blinded_position_native_joint_reveal(
    receipt: BlindedPositionNativeJointCorrectionRevealReceiptV4,
) -> NativeJointCorrectionBlindedPositionEvaluation:
    """Recompute truth errors while retaining unresolved association mass."""

    receipt = BlindedPositionNativeJointCorrectionRevealReceiptV4.model_validate(
        receipt.model_dump(mode="json")
    )
    truth_site = receipt.truth.position
    truth_ecef = np.asarray(
        _geodetic_to_ecef_m(
            truth_site.latitude_deg,
            truth_site.longitude_deg,
            truth_site.altitude_m,
        ),
        dtype=np.float64,
    )
    rotation = _ecef_to_enu_rotation(truth_site.latitude_deg, truth_site.longitude_deg)
    modes = tuple(
        _evaluate_mode(mode=mode, truth_ecef=truth_ecef, ecef_to_enu=rotation)
        for mode in receipt.estimate.modes
    )
    returned_mass = math.fsum(item.posterior_probability for item in modes)
    if returned_mass <= 0.0:
        raise BlindedPositionEvaluationError("native-joint returned posterior mass is zero")
    conditional_mean = (
        math.fsum(item.posterior_probability * item.three_dimensional_error_m for item in modes)
        / returned_mass
    )
    conditional_rms = math.sqrt(
        math.fsum(item.posterior_probability * item.three_dimensional_error_m**2 for item in modes)
        / returned_mass
    )
    return NativeJointCorrectionBlindedPositionEvaluation(
        reveal_receipt_digest=receipt.receipt_digest,
        challenge_content_digest=receipt.challenge.content_digest,
        estimate_content_digest=receipt.estimate.content_digest,
        truth_content_digest=receipt.truth.content_digest,
        lane=receipt.estimate.lane,
        reported_mode_id=receipt.estimate.reported_mode_id,
        reported_mode=modes[0],
        modes=modes,
        returned_posterior_mass=returned_mass,
        unresolved_probability=receipt.estimate.unresolved_probability,
        conditional_mean_three_dimensional_error_m=conditional_mean,
        conditional_rms_three_dimensional_error_m=conditional_rms,
        target_likelihood_compared_to_unresolved=(
            receipt.estimate.target_likelihood_compared_to_unresolved
        ),
    )
