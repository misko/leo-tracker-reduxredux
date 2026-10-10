"""Research relative-phase SatelliteCorrection objective; no truth inputs."""

import runpy
from pathlib import Path

import numpy as np

from leo.analysis.hard60_score import likelihood
from leo.analysis.hard60_satellite_correction import SatelliteCorrection
from leo.analysis.regional_position_score import observer

PHASE = runpy.run_path(
    str(Path(__file__).parents[1] / "2026_10_09_position_error_iter126/phase.py")
)


def predict(model, vector):
    relative = model.basis @ vector[8:]
    query = model.observations.times_s[:, None] + vector[7] + relative
    nodes = model.bank.nodes_s
    if np.any((query < nodes[0]) | (query > nodes[-1])):
        raise ValueError("query outside support")
    index = np.minimum(np.searchsorted(nodes, query, side="right") - 1, len(nodes) - 2)
    sat = np.arange(len(relative))[None, :]
    dt = nodes[index + 1] - nodes[index]
    f = (query - nodes[index]) / dt
    states = []
    for array in (model.bank.position_km, model.bank.velocity_km_s):
        left, right = array[sat, index], array[sat, index + 1]
        states.append(
            PHASE["transformed"](
                left + f[..., None] * (right - left), (right - left) / dt[..., None], relative
            )
        )
    (p, pc, pr), (v, vc, vr) = states
    site, up = observer(model.prior, vector[:2])
    eye = np.eye(2) * 0.001
    site_jac = np.stack(
        [
            (observer(model.prior, vector[:2] + d)[0] - observer(model.prior, vector[:2] - d)[0])
            / 0.002
            for d in eye
        ]
    )
    delta = p - site
    distance = np.linalg.norm(delta, axis=-1)
    direction = delta / distance[..., None]
    radial = np.sum(direction * v, axis=-1)
    factor = model.observations.rf_hz[:, None] / 299792.458
    tangent = (v - radial[..., None] * direction) / distance[..., None]
    spatial = factor[..., None] * np.einsum("nka,ia->nki", tangent, site_jac)

    def timing(dp, dv):
        return -factor * (np.sum(tangent * dp, axis=-1) + np.sum(direction * dv, axis=-1))

    return (
        -factor * radial,
        np.sum(direction * up, axis=-1) >= 0,
        spatial,
        timing(pc, vc),
        timing(pr, vr),
    )


class PhaseObjective(SatelliteCorrection):
    def evaluate_joint(self, vector, clock):
        relative = self.basis @ vector[8:]
        prediction, visible, spatial, common, individual = predict(self, vector)
        prediction += (self.design @ vector[2:7] + self.baseline + self.clock_design @ clock)[
            :, None
        ]
        offsets, slopes = self.physical_corrections(clock)
        prediction += offsets[None, :] + self.delta_time * (100 * slopes)[None, :]
        terms = likelihood(self.observations.measured_hz, prediction, visible, self.score)
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
        penalty += (
            0.5 * np.sum((relative / self.score.relative_sigma_s) ** 2)
            + 0.5 * clock @ self.precision @ clock
        )
        return terms.nll + penalty, gradient, nuisance, terms


def convert(model):
    """Retain reconstructed SlopePrior state verbatim; never rerun constructor."""
    result = object.__new__(PhaseObjective)
    result.__dict__.update(model.__dict__)
    assert result.__dict__.keys() == model.__dict__.keys()
    np.testing.assert_array_equal(result.precision, model.precision)
    assert result.offset_slice == model.offset_slice and result.slope_slice == model.slope_slice
    return result
