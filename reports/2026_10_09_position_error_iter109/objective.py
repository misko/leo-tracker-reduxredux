"""Research-only composed B7 objective; sequence occupancies replace row posteriors."""

import runpy
from pathlib import Path

import numpy as np

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import WindowLikelihood

KERNEL = runpy.run_path(str(Path(__file__).with_name("persistence.py")))["evaluate"]


class PersistenceObjective:
    def __init__(self, base, permutation, reset, *, rho):
        permutation = np.asarray(permutation)
        count = len(base.observations.times_s)
        if (
            permutation.shape != (count,)
            or permutation.dtype.kind not in "iu"
            or not np.array_equal(np.sort(permutation), np.arange(count))
        ):
            raise ValueError("Every original row must occur exactly once")
        reset = np.asarray(reset)
        if reset.shape != (count,) or reset.dtype != bool or not reset[0]:
            raise ValueError("Boolean packed reset flags required")
        if not np.isfinite(rho) or not 0 <= rho < 1:
            raise ValueError("rho must lie in [0,1)")
        self.base, self.permutation, self.reset, self.rho = base, permutation, reset.copy(), rho
        self.inverse = np.argsort(permutation)

    def __getattr__(self, name):
        return getattr(self.base, name)

    def evaluate_joint(self, vector, clock):
        # Delegate the exact zero control, preserving all original arithmetic order.
        if self.rho == 0:
            return self.base.evaluate_joint(vector, clock)
        relative = self.basis @ vector[8:]
        prediction, visible, spatial, timing = predict_orbits(
            self.bank, self.observations, self.prior, vector[:2], vector[7] + relative
        )
        prediction += (self.design @ vector[2:7] + self.baseline + self.clock_design @ clock)[
            :, None
        ]
        offsets, slopes = self.physical_corrections(clock)
        prediction += offsets[None, :] + self.delta_time * (100 * slopes)[None, :]
        packed = self.permutation
        result = KERNEL(
            self.observations.measured_hz[packed],
            prediction[packed],
            visible[packed],
            self.score,
            rho=self.rho,
            reset=self.reset,
        )
        occupancy = result["occupancy"][self.inverse]
        terms = WindowLikelihood(
            result["nll"],
            occupancy[:, 1:],
            occupancy[:, 0],
            result["prediction_gradient"][self.inverse],
            result["residual_hz"][self.inverse],
        )
        weight = terms.prediction_gradient
        shift = np.sum(weight * timing, axis=0)
        gradient = np.zeros(self.size)
        gradient[:2] = np.einsum("nk,nki->i", weight, spatial)
        gradient[2:7] = self.design.T @ weight.sum(axis=1)
        gradient[7] = shift.sum() + vector[7] / self.score.common_sigma_s**2
        gradient[8:] = self.basis.T @ (shift + relative / self.score.relative_sigma_s**2)
        nuisance = self.clock_design.T @ weight.sum(axis=1) + self.precision @ clock
        if self.offset_slice.stop > self.offset_slice.start:
            nuisance[self.offset_slice] += self.satellite_basis.T @ weight.sum(axis=0)
        if self.slope_slice.stop > self.slope_slice.start:
            nuisance[self.slope_slice] += self.satellite_basis.T @ (weight * self.delta_time).sum(
                axis=0
            )
        penalty = 0.5 * (vector[7] / self.score.common_sigma_s) ** 2
        penalty += 0.5 * np.sum((relative / self.score.relative_sigma_s) ** 2)
        penalty += 0.5 * clock @ self.precision @ clock
        return terms.nll + penalty, gradient, nuisance, terms

    @staticmethod
    def assert_zero_c(vector, clock):
        if vector[6] != 0 or np.any(np.asarray(clock)[-2:] != 0):
            raise ValueError("c=0 requires unchanged static and RF-time locks")
