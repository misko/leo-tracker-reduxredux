"""Research joint clock-position objective with a differentiable horizon."""

import sys
from pathlib import Path

import numpy as np

REPORTS = Path(__file__).resolve().parent.parent
sys.path[:0] = [
    str(REPORTS / name)
    for name in (
        "2026_10_09_position_error_iter56",
        "2026_10_09_position_error_iter57",
        "2026_10_08_position_error_iter04",
    )
]
from joint_clock import JointClockObjective  # noqa: E402
from native_elevation import predict_elevation  # noqa: E402
from smooth_likelihood import evaluate  # noqa: E402

from leo.analysis.hard60_score import predict_orbits  # noqa: E402
from leo.analysis.regional_position_score import WindowLikelihood, circular  # noqa: E402


class SmoothJointObjective(JointClockObjective):
    def evaluate_joint(self, vector, clock):
        relative = self.basis @ vector[8:]
        shifts = vector[7] + relative
        prediction, _, spatial, timing = predict_orbits(
            self.bank, self.observations, self.prior, vector[:2], shifts
        )
        elevation, e_spatial, e_timing = predict_elevation(
            self.bank, self.observations, self.prior, vector[:2], shifts
        )
        prediction += (self.design @ vector[2:7] + self.baseline + self.clock_design @ clock)[
            :, None
        ]
        result = evaluate(self.observations.measured_hz, prediction, elevation, self.score)
        weight, e_weight = result["prediction_gradient"], result["elevation_gradient"]
        shift = np.sum(weight * timing + e_weight * e_timing, axis=0)
        gradient = np.zeros(self.size)
        gradient[:2] = np.einsum("nk,nki->i", weight, spatial)
        gradient[:2] += np.einsum("nk,nki->i", e_weight, e_spatial)
        gradient[2:7] = self.design.T @ weight.sum(axis=1)
        gradient[7] = shift.sum() + vector[7] / self.score.common_sigma_s**2
        gradient[8:] = self.basis.T @ (shift + relative / self.score.relative_sigma_s**2)
        clock_gradient = self.clock_design.T @ weight.sum(axis=1) + self.precision @ clock
        penalty = 0.5 * (vector[7] / self.score.common_sigma_s) ** 2
        penalty += 0.5 * np.sum((relative / self.score.relative_sigma_s) ** 2)
        penalty += 0.5 * clock @ self.precision @ clock
        terms = WindowLikelihood(
            result["nll"],
            result["responsibility"],
            1 - result["responsibility"].sum(axis=1),
            weight,
            circular(self.observations.measured_hz[:, None] - prediction),
        )
        return terms.nll + penalty, gradient, clock_gradient, terms
