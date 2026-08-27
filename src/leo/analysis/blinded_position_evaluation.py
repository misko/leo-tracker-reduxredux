"""Reveal-only evaluation of a sealed blinded Doppler position estimate.

The navigation solver has no truth input port.  This module deliberately sits
on the other side of that boundary: it accepts only a validated
``BlindedPositionRevealReceiptV1``, recomputes the truth ECEF position, and
derives ENU errors and covariance-consistency diagnostics.  It never refits or
changes the sealed estimate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.satellite_pnt import (
    BlindedPositionRevealReceiptV1,
    NavigationLane,
    PositionPosteriorModeV1,
)

_WGS84_SEMI_MAJOR_AXIS_M = 6_378_137.0
_WGS84_FLATTENING = 1.0 / 298.257223563
_WGS84_ECCENTRICITY_SQUARED = _WGS84_FLATTENING * (2.0 - _WGS84_FLATTENING)
_CHI_SQUARE_95_DF2 = 5.991_464_547_107_979
_CHI_SQUARE_95_DF3 = 7.814_727_903_251_179


class BlindedPositionEvaluationError(ValueError):
    """A reveal receipt or covariance diagnostic is not evaluable."""


@dataclass(frozen=True, slots=True)
class PositionModeEvaluation:
    mode_id: Sha256Digest
    rank: int
    posterior_probability: float
    associated_catalog_numbers: tuple[int, ...]
    east_error_m: float
    north_error_m: float
    signed_up_error_m: float
    horizontal_error_m: float
    three_dimensional_error_m: float
    position_nees: float | None
    horizontal_nees: float | None
    vertical_standardized_error: float | None
    inside_95_percent_position_ellipsoid: bool | None
    inside_95_percent_horizontal_ellipse: bool | None

    def __post_init__(self) -> None:
        finite_values = (
            self.posterior_probability,
            self.east_error_m,
            self.north_error_m,
            self.signed_up_error_m,
            self.horizontal_error_m,
            self.three_dimensional_error_m,
        )
        if any(not math.isfinite(item) for item in finite_values):
            raise BlindedPositionEvaluationError("position evaluation values must be finite")
        if not 0.0 < self.posterior_probability <= 1.0:
            raise BlindedPositionEvaluationError("mode probability is outside (0, 1]")
        if self.rank < 1:
            raise BlindedPositionEvaluationError("mode rank must be positive")
        diagnostics = (
            self.position_nees,
            self.horizontal_nees,
            self.vertical_standardized_error,
        )
        if any(
            item is not None and (not math.isfinite(item) or item < 0.0) for item in diagnostics
        ):
            raise BlindedPositionEvaluationError(
                "covariance-consistency diagnostics must be finite and nonnegative"
            )


@dataclass(frozen=True, slots=True)
class BlindedPositionEvaluation:
    reveal_receipt_digest: Sha256Digest
    challenge_content_digest: Sha256Digest
    estimate_content_digest: Sha256Digest
    truth_content_digest: Sha256Digest
    lane: NavigationLane
    reported_mode_id: Sha256Digest
    reported_mode: PositionModeEvaluation
    modes: tuple[PositionModeEvaluation, ...]
    returned_posterior_mass: float
    unresolved_probability: float
    conditional_mean_three_dimensional_error_m: float
    conditional_rms_three_dimensional_error_m: float
    evaluation_algorithm: str = field(default="blinded-position-reveal-evaluation-v1", init=False)
    content_digest: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if not self.modes:
            raise BlindedPositionEvaluationError("position evaluation needs returned modes")
        if tuple(item.rank for item in self.modes) != tuple(range(1, len(self.modes) + 1)):
            raise BlindedPositionEvaluationError("position evaluation ranks are not contiguous")
        if self.reported_mode.rank != 1 or self.reported_mode.mode_id != self.reported_mode_id:
            raise BlindedPositionEvaluationError("reported evaluation mode is not rank one")
        if self.reported_mode != self.modes[0]:
            raise BlindedPositionEvaluationError("reported evaluation mode is not first")
        if not math.isclose(
            self.returned_posterior_mass + self.unresolved_probability,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise BlindedPositionEvaluationError("evaluation posterior accounting is not closed")
        aggregates = (
            self.returned_posterior_mass,
            self.unresolved_probability,
            self.conditional_mean_three_dimensional_error_m,
            self.conditional_rms_three_dimensional_error_m,
        )
        if any(not math.isfinite(item) or item < 0.0 for item in aggregates):
            raise BlindedPositionEvaluationError("position evaluation aggregates are invalid")
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


def evaluate_blinded_position_reveal(
    receipt: BlindedPositionRevealReceiptV1,
) -> BlindedPositionEvaluation:
    """Recompute position errors from an exact post-seal reveal receipt."""

    receipt = BlindedPositionRevealReceiptV1.model_validate(receipt.model_dump(mode="json"))
    if not receipt.estimate.modes or receipt.estimate.reported_mode_id is None:
        raise BlindedPositionEvaluationError("sealed position estimate has no evaluable mode")
    truth_site = receipt.truth.position
    truth_ecef = np.asarray(
        _geodetic_to_ecef_m(
            truth_site.latitude_deg,
            truth_site.longitude_deg,
            truth_site.altitude_m,
        ),
        dtype=np.float64,
    )
    ecef_to_enu = _ecef_to_enu_rotation(
        truth_site.latitude_deg,
        truth_site.longitude_deg,
    )
    evaluations = tuple(
        _evaluate_mode(mode=mode, truth_ecef=truth_ecef, ecef_to_enu=ecef_to_enu)
        for mode in receipt.estimate.modes
    )
    returned_mass = math.fsum(item.posterior_probability for item in evaluations)
    if returned_mass <= 0.0:
        raise BlindedPositionEvaluationError("returned position posterior mass is zero")
    conditional_mean = (
        math.fsum(
            item.posterior_probability * item.three_dimensional_error_m for item in evaluations
        )
        / returned_mass
    )
    conditional_rms = math.sqrt(
        math.fsum(
            item.posterior_probability * item.three_dimensional_error_m**2 for item in evaluations
        )
        / returned_mass
    )
    return BlindedPositionEvaluation(
        reveal_receipt_digest=receipt.receipt_digest,
        challenge_content_digest=receipt.challenge.content_digest,
        estimate_content_digest=receipt.estimate.content_digest,
        truth_content_digest=receipt.truth.content_digest,
        lane=receipt.estimate.lane,
        reported_mode_id=receipt.estimate.reported_mode_id,
        reported_mode=evaluations[0],
        modes=evaluations,
        returned_posterior_mass=returned_mass,
        unresolved_probability=receipt.estimate.unresolved_probability,
        conditional_mean_three_dimensional_error_m=conditional_mean,
        conditional_rms_three_dimensional_error_m=conditional_rms,
    )


def _evaluate_mode(
    *,
    mode: PositionPosteriorModeV1,
    truth_ecef: NDArray[np.float64],
    ecef_to_enu: NDArray[np.float64],
) -> PositionModeEvaluation:
    estimate_ecef = np.asarray(mode.mean_ecef_m, dtype=np.float64)
    error_ecef = estimate_ecef - truth_ecef
    error_enu = ecef_to_enu @ error_ecef
    covariance_ecef = np.asarray(mode.covariance_ecef_m2, dtype=np.float64)
    covariance_enu = ecef_to_enu @ covariance_ecef @ ecef_to_enu.T
    covariance_enu = 0.5 * (covariance_enu + covariance_enu.T)
    position_nees = _semidefinite_quadratic(error_ecef, covariance_ecef)
    horizontal_nees = _semidefinite_quadratic(error_enu[:2], covariance_enu[:2, :2])
    vertical_variance = float(covariance_enu[2, 2])
    vertical_standardized = (
        abs(float(error_enu[2])) / math.sqrt(vertical_variance)
        if vertical_variance > 0.0
        else 0.0
        if error_enu[2] == 0.0
        else None
    )
    horizontal_error = math.hypot(float(error_enu[0]), float(error_enu[1]))
    three_dimensional_error = float(np.linalg.norm(error_ecef))
    return PositionModeEvaluation(
        mode_id=mode.mode_id,
        rank=mode.rank,
        posterior_probability=mode.posterior_probability,
        associated_catalog_numbers=mode.associated_catalog_numbers,
        east_error_m=float(error_enu[0]),
        north_error_m=float(error_enu[1]),
        signed_up_error_m=float(error_enu[2]),
        horizontal_error_m=horizontal_error,
        three_dimensional_error_m=three_dimensional_error,
        position_nees=position_nees,
        horizontal_nees=horizontal_nees,
        vertical_standardized_error=vertical_standardized,
        inside_95_percent_position_ellipsoid=(
            None if position_nees is None else position_nees <= _CHI_SQUARE_95_DF3
        ),
        inside_95_percent_horizontal_ellipse=(
            None if horizontal_nees is None else horizontal_nees <= _CHI_SQUARE_95_DF2
        ),
    )


def _semidefinite_quadratic(
    error: NDArray[np.float64], covariance: NDArray[np.float64]
) -> float | None:
    covariance = 0.5 * (covariance + covariance.T)
    if not np.all(np.isfinite(covariance)) or not np.all(np.isfinite(error)):
        raise BlindedPositionEvaluationError("position error/covariance is not finite")
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    scale = float(np.max(np.abs(eigenvalues)))
    tolerance = 64.0 * np.finfo(np.float64).eps * scale
    if float(np.min(eigenvalues)) < -tolerance:
        raise BlindedPositionEvaluationError("position covariance is not semidefinite")
    projected = eigenvectors.T @ error
    positive = eigenvalues > tolerance
    null_projection = projected[~positive]
    null_tolerance = 64.0 * np.finfo(np.float64).eps * max(1.0, float(np.linalg.norm(error)))
    if null_projection.size and float(np.linalg.norm(null_projection)) > null_tolerance:
        return None
    if not np.any(positive):
        return 0.0
    value = float(np.sum(projected[positive] ** 2 / eigenvalues[positive]))
    if not math.isfinite(value) or value < 0.0:
        raise BlindedPositionEvaluationError("position covariance diagnostic is invalid")
    return value


def _geodetic_to_ecef_m(
    latitude_deg: float, longitude_deg: float, altitude_m: float
) -> tuple[float, float, float]:
    latitude = math.radians(latitude_deg)
    longitude = math.radians(longitude_deg)
    sin_latitude = math.sin(latitude)
    cos_latitude = math.cos(latitude)
    prime_vertical = _WGS84_SEMI_MAJOR_AXIS_M / math.sqrt(
        1.0 - _WGS84_ECCENTRICITY_SQUARED * sin_latitude**2
    )
    return (
        (prime_vertical + altitude_m) * cos_latitude * math.cos(longitude),
        (prime_vertical + altitude_m) * cos_latitude * math.sin(longitude),
        (prime_vertical * (1.0 - _WGS84_ECCENTRICITY_SQUARED) + altitude_m) * sin_latitude,
    )


def _ecef_to_enu_rotation(latitude_deg: float, longitude_deg: float) -> NDArray[np.float64]:
    latitude = math.radians(latitude_deg)
    longitude = math.radians(longitude_deg)
    sin_latitude = math.sin(latitude)
    cos_latitude = math.cos(latitude)
    sin_longitude = math.sin(longitude)
    cos_longitude = math.cos(longitude)
    return np.asarray(
        (
            (-sin_longitude, cos_longitude, 0.0),
            (
                -sin_latitude * cos_longitude,
                -sin_latitude * sin_longitude,
                cos_latitude,
            ),
            (
                cos_latitude * cos_longitude,
                cos_latitude * sin_longitude,
                sin_latitude,
            ),
        ),
        dtype=np.float64,
    )
