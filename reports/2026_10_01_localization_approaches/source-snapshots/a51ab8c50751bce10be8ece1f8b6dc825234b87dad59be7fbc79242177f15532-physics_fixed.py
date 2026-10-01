"""Reduced-state adapter that fixes receiver height to a spatial surface."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "2026_09_30_gaussian_sum_64_scan"
sys.path.append(str(BASE))

from physics import PhysicsFactor, Prediction, build_physics_factor  # noqa: E402

from leo.analysis.gaussian_sum_location import Candidate, ObservationFactor  # noqa: E402


class HeightCallable(Protocol):
    def __call__(self, east_km: float, north_km: float) -> float: ...


@dataclass(frozen=True)
class ReducedStateLayout:
    """The frozen full layout with its height coordinate removed."""

    full_layout: object

    @property
    def norad_ids(self) -> tuple[int, ...]:
        return self.full_layout.norad_ids

    @property
    def dimension(self) -> int:
        return self.full_layout.dimension - 1

    def satellite_epoch_index(self, norad_id: int) -> int:
        return self.full_layout.satellite_epoch_index(norad_id) - 1


def expand_state(reduced_state: object, height: HeightCallable) -> np.ndarray:
    reduced = np.asarray(reduced_state, dtype=np.float64)
    if reduced.ndim != 1 or reduced.size < 5 or np.any(~np.isfinite(reduced)):
        raise ValueError("reduced state must be a finite vector with at least five coordinates")
    full = np.empty(reduced.size + 1)
    full[:2] = reduced[:2]
    full[2] = float(height(float(reduced[0]), float(reduced[1])))
    full[3:] = reduced[2:]
    if not np.isfinite(full[2]):
        raise ValueError("fixed height surface returned a nonfinite height")
    return full


def _height_gradient(height: HeightCallable, east: float, north: float) -> tuple[float, float]:
    step_km = 1e-3
    east_gradient = (height(east + step_km, north) - height(east - step_km, north)) / (
        2.0 * step_km
    )
    north_gradient = (height(east, north + step_km) - height(east, north - step_km)) / (
        2.0 * step_km
    )
    if not np.isfinite(east_gradient) or not np.isfinite(north_gradient):
        raise ValueError("fixed height surface has a nonfinite numerical gradient")
    return float(east_gradient), float(north_gradient)


def _translate_support_error(error: ValueError) -> None:
    if "prediction time lacks four-knot orbit support" in str(error):
        raise ValueError(
            "fixed-height prediction exceeds shared four-knot orbit support; "
            "this exact-ablation adapter preserves the frozen global support behavior"
        ) from error
    raise error


def build_fixed_height_factor(
    track, bank, full_layout, config, height: HeightCallable
) -> PhysicsFactor:
    """Wrap the frozen factor while removing height from the persistent state.

    The height gradient is evaluated by a centered one-metre finite difference.
    Orbit-time support behavior remains global across the catalogue, matching the
    frozen implementation for the first fixed-height ablation.
    """
    built = build_physics_factor(track, bank, full_layout, config)

    def full_state(reduced: np.ndarray) -> np.ndarray:
        if np.asarray(reduced).shape != (full_layout.dimension - 1,):
            raise ValueError("reduced state dimension does not match the full layout")
        return expand_state(reduced, height)

    candidates = []
    for original in built.factor.candidates:
        def prior(reduced, original=original):
            try:
                value = (
                    original.prior(full_state(reduced))
                    if callable(original.prior)
                    else original.prior
                )
            except ValueError as error:
                _translate_support_error(error)
            return value

        def predict(reduced, original=original):
            reduced = np.asarray(reduced, dtype=np.float64)
            full = full_state(reduced)
            try:
                prediction = original.predict(full)
            except ValueError as error:
                _translate_support_error(error)
            east_gradient, north_gradient = _height_gradient(
                height, float(reduced[0]), float(reduced[1])
            )
            jacobian = np.empty((prediction.mean.size, reduced.size))
            jacobian[:, 0] = prediction.jacobian[:, 0] + prediction.jacobian[:, 2] * east_gradient
            jacobian[:, 1] = prediction.jacobian[:, 1] + prediction.jacobian[:, 2] * north_gradient
            jacobian[:, 2:] = prediction.jacobian[:, 3:]
            return Prediction(
                prediction.mean, jacobian, prediction.covariance, prediction.eligible
            )

        candidates.append(
            Candidate(original.label, prior, predict, prior_is_local=original.prior_is_local)
        )

    def background_prior(reduced):
        original = built.factor.background_prior
        try:
            return original(full_state(reduced)) if callable(original) else original
        except ValueError as error:
            _translate_support_error(error)

    factor = ObservationFactor(
        built.factor.observation_ids,
        built.factor.observation,
        tuple(candidates),
        background_prior,
        built.factor.background_log_likelihood,
    )
    return PhysicsFactor(
        factor,
        built.selected_indices,
        built.visible_norad_ids,
        built.flags + ("fixed_height_surface", "global_orbit_support_preserved"),
    )
