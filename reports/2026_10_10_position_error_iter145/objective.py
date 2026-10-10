"""Research emission adapter preserving the supplied control's geometry and priors."""

import numpy as np

from leo.analysis.hard60_satellite_correction import SatelliteCorrection
from leo.analysis.hard60_score import predict_orbits


def timestamp_prediction(model, vector):
    relative = model.basis @ vector[8:]
    prediction, visible, spatial, timing = predict_orbits(
        model.bank, model.observations, model.prior, vector[:2], vector[7] + relative
    )
    return prediction, visible, spatial, timing, timing


class PairedObjective(SatelliteCorrection):
    def evaluate_joint(self, vector, clock):
        if self.pair_rho == 0:
            return self.control_model.evaluate_joint(vector, clock)
        relative = self.basis @ vector[8:]
        prediction, visible, spatial, common, individual = self.prediction_provider(self, vector)
        prediction += (self.design @ vector[2:7] + self.baseline + self.clock_design @ clock)[
            :, None
        ]
        offsets, slopes = self.physical_corrections(clock)
        prediction += offsets[None, :] + self.delta_time * (100 * slopes)[None, :]
        terms = self.emission_provider(
            self.observations.measured_hz,
            prediction,
            visible,
            self.score,
            self.observation_pairs,
            rho=self.pair_rho,
        )
        weight = terms.prediction_gradient
        gradient = np.zeros(self.size)
        gradient[:2] = np.einsum("nk,nki->i", weight, spatial)
        gradient[2:7] = self.design.T @ weight.sum(axis=1)
        gradient[7] = np.sum(weight * common) + vector[7] / self.score.common_sigma_s**2
        gradient[8:] = self.basis.T @ (
            np.sum(weight * individual, axis=0) + relative / self.score.relative_sigma_s**2
        )
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


def convert(control, pairs, rho, *, prediction_provider, emission_provider):
    """Explicit geometry/emission ports; no mutation of control or module globals."""
    pairs = np.asarray(pairs)
    if pairs.ndim != 2 or pairs.shape[1] != 2 or pairs.dtype.kind not in "iu":
        raise ValueError("Integer disjoint row pairs required")
    if (
        np.any(pairs < 0)
        or np.any(pairs >= len(control.observations.times_s))
        or len(np.unique(pairs)) != pairs.size
        or not np.isfinite(rho)
        or rho not in (0, 0.25)
    ):
        raise ValueError("Disjoint valid pairs and fixed exploratory rho required")
    if not callable(prediction_provider) or not callable(emission_provider):
        raise ValueError("Explicit prediction and emission providers required")
    result = object.__new__(PairedObjective)
    result.__dict__.update(control.__dict__)
    result.control_model = control
    result.observation_pairs = pairs.copy()
    result.observation_pairs.flags.writeable = False
    result.pair_rho = rho
    result.prediction_provider = prediction_provider
    result.emission_provider = emission_provider
    return result
