"""Conditional shared-track mark likelihood around the existing B7 objective."""

import numpy as np

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.hard60_slope_prior import SlopePrior
from leo.analysis.shared_track_likelihood import shared_track_terms


class SharedTrackObjective(SlopePrior):
    def __init__(self, base, nodes, knots, centers_s, groups, *, shared_prior=0.5):
        super().__init__(base, nodes, knots, centers_s, 0.5)
        self.groups = tuple(tuple(g) for g in groups)
        if not np.isfinite(shared_prior) or not 0 <= shared_prior <= 1:
            raise ValueError("shared prior must lie in [0, 1]")
        self.shared_prior = shared_prior

    def evaluate_joint(self, vector, clock):
        value, gradient, nuisance, original = super().evaluate_joint(vector, clock)
        if self.shared_prior == 0:
            return value, gradient, nuisance, original
        grouped, _ = shared_track_terms(original, self.groups, shared_prior=self.shared_prior)
        delta = grouped.prediction_gradient - original.prediction_gradient
        relative = self.basis @ vector[8:]
        _, _, spatial, timing = predict_orbits(
            self.bank, self.observations, self.prior, vector[:2], vector[7] + relative
        )
        shift = np.sum(delta * timing, axis=0)
        gradient[:2] += np.einsum("nk,nki->i", delta, spatial)
        gradient[2:7] += self.design.T @ delta.sum(axis=1)
        gradient[7] += shift.sum()
        gradient[8:] += self.basis.T @ shift
        nuisance += self.clock_design.T @ delta.sum(axis=1)
        if self.offset_slice.stop > self.offset_slice.start:
            nuisance[self.offset_slice] += self.satellite_basis.T @ delta.sum(axis=0)
        if self.slope_slice.stop > self.slope_slice.start:
            nuisance[self.slope_slice] += self.satellite_basis.T @ (delta * self.delta_time).sum(
                axis=0
            )
        return value + grouped.nll - original.nll, gradient, nuisance, grouped
