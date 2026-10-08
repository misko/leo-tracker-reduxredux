"""Regularized satellite-common offsets/slopes around the frozen joint-clock model."""

import numpy as np
from dynamic_rf import DynamicRFObjective

from leo.analysis.hard60_score import likelihood, predict_orbits


class SatelliteCorrection(DynamicRFObjective):
    def __init__(self, base, nodes, knots, centers_s, variant):
        if variant not in ("offset", "slope", "both"):
            raise ValueError("Unknown satellite correction")
        super().__init__(base, nodes, knots, 50)
        count = len(self.bank.numbers)
        self.satellite_basis = np.linalg.svd(np.ones((1, count)), full_matrices=True)[2][1:].T
        self.centers_s = np.asarray(centers_s, float)
        if self.centers_s.shape != (count,) or not np.isfinite(self.centers_s).all():
            raise ValueError("One finite inference-only time center per satellite")
        start = self.smooth_clock_count
        self.offset_slice = slice(
            start, start + (count - 1 if variant in ("offset", "both") else 0)
        )
        start = self.offset_slice.stop
        self.slope_slice = slice(start, start + (count - 1 if variant in ("slope", "both") else 0))
        extra = self.slope_slice.stop - self.smooth_clock_count
        old_indices = np.r_[
            np.arange(self.smooth_clock_count),
            np.arange(self.slope_slice.stop, self.slope_slice.stop + 2),
        ]
        precision = np.zeros((len(self.initial_clock) + extra,) * 2)
        precision[np.ix_(old_indices, old_indices)] = self.precision
        # Offsets: sigma 50 Hz. Slopes: sigma 100 Hz/100 s = 1 Hz/s.
        for selection, sigma in ((self.offset_slice, 50), (self.slope_slice, 100)):
            precision[selection, selection] = np.eye(selection.stop - selection.start) / sigma**2
        self.precision = precision
        design = np.zeros((len(self.observations.times_s), len(precision)))
        design[:, old_indices] = self.clock_design
        self.clock_design = design
        self.initial_clock = np.r_[
            self.initial_clock[:-2], np.zeros(extra), self.initial_clock[-2:]
        ]
        self.delta_time = (self.observations.times_s[:, None] - self.centers_s[None, :]) / 100

    def expand_clock(self, original):
        original = np.asarray(original)
        if original.shape != (self.smooth_clock_count + 2,):
            raise ValueError("Expected frozen drift-50 clock coefficients")
        return np.r_[
            original[:-2], np.zeros(self.slope_slice.stop - self.smooth_clock_count), original[-2:]
        ]

    def physical_corrections(self, clock):
        values = []
        for selection in (self.offset_slice, self.slope_slice):
            values.append(
                self.satellite_basis @ clock[selection]
                if selection.stop > selection.start
                else np.zeros(len(self.bank.numbers))
            )
        return values[0], values[1] / 100

    def evaluate_joint(self, vector, clock):
        relative = self.basis @ vector[8:]
        prediction, visible, spatial, timing = predict_orbits(
            self.bank, self.observations, self.prior, vector[:2], vector[7] + relative
        )
        prediction += (self.design @ vector[2:7] + self.baseline + self.clock_design @ clock)[
            :, None
        ]
        offsets, slopes = self.physical_corrections(clock)
        prediction += offsets[None, :] + self.delta_time * (100 * slopes)[None, :]
        terms = likelihood(self.observations.measured_hz, prediction, visible, self.score)
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
