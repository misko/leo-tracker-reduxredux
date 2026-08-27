"""Reveal-only evaluation for the oracle correction-set navigation lane."""

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
from leo.contracts.satellite_pnt_challenge_v2 import CorrectionSetNavigationLane
from leo.contracts.satellite_pnt_reveal_v2 import (
    BlindedPositionCorrectionSetRevealReceiptV2,
)


@dataclass(frozen=True, slots=True)
class CorrectionSetBlindedPositionEvaluation:
    reveal_receipt_digest: Sha256Digest
    challenge_content_digest: Sha256Digest
    estimate_content_digest: Sha256Digest
    truth_content_digest: Sha256Digest
    lane: CorrectionSetNavigationLane
    reported_mode_id: Sha256Digest
    reported_mode: PositionModeEvaluation
    modes: tuple[PositionModeEvaluation, ...]
    returned_posterior_mass: float
    unresolved_probability: float
    conditional_mean_three_dimensional_error_m: float
    conditional_rms_three_dimensional_error_m: float
    evaluation_algorithm: str = field(
        default="blinded-position-correction-set-reveal-evaluation-v1", init=False
    )
    content_digest: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if not self.modes or self.reported_mode != self.modes[0]:
            raise BlindedPositionEvaluationError(
                "correction-set evaluation requires its rank-one reported mode"
            )
        if not math.isclose(
            self.returned_posterior_mass + self.unresolved_probability,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise BlindedPositionEvaluationError(
                "correction-set evaluation posterior accounting is not closed"
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
            "modes": [
                {
                    "mode_id": item.mode_id,
                    "rank": item.rank,
                    "posterior_probability": item.posterior_probability,
                    "associated_catalog_numbers": item.associated_catalog_numbers,
                    "east_error_m": item.east_error_m,
                    "north_error_m": item.north_error_m,
                    "signed_up_error_m": item.signed_up_error_m,
                    "horizontal_error_m": item.horizontal_error_m,
                    "three_dimensional_error_m": item.three_dimensional_error_m,
                    "position_nees": item.position_nees,
                    "horizontal_nees": item.horizontal_nees,
                    "vertical_standardized_error": item.vertical_standardized_error,
                    "inside_95_percent_position_ellipsoid": (
                        item.inside_95_percent_position_ellipsoid
                    ),
                    "inside_95_percent_horizontal_ellipse": (
                        item.inside_95_percent_horizontal_ellipse
                    ),
                }
                for item in self.modes
            ],
            "returned_posterior_mass": self.returned_posterior_mass,
            "unresolved_probability": self.unresolved_probability,
            "conditional_mean_three_dimensional_error_m": (
                self.conditional_mean_three_dimensional_error_m
            ),
            "conditional_rms_three_dimensional_error_m": (
                self.conditional_rms_three_dimensional_error_m
            ),
            "evaluation_algorithm": self.evaluation_algorithm,
        }


def evaluate_blinded_position_correction_set_reveal(
    receipt: BlindedPositionCorrectionSetRevealReceiptV2,
) -> CorrectionSetBlindedPositionEvaluation:
    """Recompute truth errors without changing the sealed V2 estimate."""

    receipt = BlindedPositionCorrectionSetRevealReceiptV2.model_validate(
        receipt.model_dump(mode="json")
    )
    if not receipt.estimate.modes or receipt.estimate.reported_mode_id is None:
        raise BlindedPositionEvaluationError("sealed V2 estimate has no evaluable mode")
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
        raise BlindedPositionEvaluationError("returned V2 posterior mass is zero")
    conditional_mean = (
        math.fsum(item.posterior_probability * item.three_dimensional_error_m for item in modes)
        / returned_mass
    )
    conditional_rms = math.sqrt(
        math.fsum(item.posterior_probability * item.three_dimensional_error_m**2 for item in modes)
        / returned_mass
    )
    return CorrectionSetBlindedPositionEvaluation(
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
    )
