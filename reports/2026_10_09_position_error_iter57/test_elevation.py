import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026_10_09_position_error_iter56"))
from elevation import predict_elevation  # noqa: E402
from smooth_likelihood import evaluate  # noqa: E402

from leo.analysis.hard60_score import predict_orbits  # noqa: E402
from leo.analysis.regional_position_score import observer  # noqa: E402
from leo.contracts.regional_position import RegionalPrior  # noqa: E402


def fixture():
    prior = RegionalPrior()
    point = np.array([13.0, -27.0])
    site, up = observer(prior, point)
    east = np.cross([0.0, 0.0, 1.0], up)
    east /= np.linalg.norm(east)
    nodes = np.array([0.0, 10.0, 20.0])
    positions, velocities = [], []
    for angle in (-0.1, 0.0, 0.5, 1.0, 1.1, 90.0):
        direction = np.cos(np.radians(angle)) * east + np.sin(np.radians(angle)) * up
        velocity = 0.03 * up + 0.1 * east
        positions.append(site + 1000 * direction + nodes[:, None] * velocity)
        velocities.append(np.tile(velocity, (3, 1)))
    bank = SimpleNamespace(
        numbers=np.arange(6),
        nodes_s=nodes,
        position_km=np.array(positions),
        velocity_km_s=np.array(velocities),
    )
    observations = SimpleNamespace(times_s=np.array([3.0, 7.0]), rf_hz=np.full(2, 11e9))
    return bank, observations, prior, point, np.zeros(6)


def test_elevation_visibility_and_position_timing_derivatives():
    bank, obs, prior, point, shifts = fixture()
    elevation, spatial, timing = predict_elevation(bank, obs, prior, point, shifts)
    _, visible, _, _ = predict_orbits(bank, obs, prior, point, shifts)
    np.testing.assert_array_equal(elevation >= 0, visible)
    for axis in range(2):
        d = np.eye(2)[axis] * 0.001
        fd = (
            predict_elevation(bank, obs, prior, point + d, shifts)[0]
            - predict_elevation(bank, obs, prior, point - d, shifts)[0]
        ) / 0.002
        np.testing.assert_allclose(spatial[:, :5, axis], fd[:, :5], rtol=1e-5, atol=1e-8)
    for j in range(6):
        d = np.eye(6)[j] * 0.001
        fd = (
            predict_elevation(bank, obs, prior, point, shifts + d)[0]
            - predict_elevation(bank, obs, prior, point, shifts - d)[0]
        ) / 0.002
        np.testing.assert_allclose(timing[:, j], fd[:, j], rtol=2e-3, atol=1e-6)


@pytest.mark.parametrize("at_boundaries", [False, True])
def test_full_likelihood_geometry_chain_rule(at_boundaries):
    bank, obs, prior, point, shifts = fixture()
    if at_boundaries:
        obs.times_s[:] = 10
        bank.position_km -= 10 * bank.velocity_km_s
    score = SimpleNamespace(sigma_hz=150, detection_budget=1.2, clutter_rate=0.3)
    prediction, _, spatial, timing = predict_orbits(bank, obs, prior, point, shifts)
    measured = prediction[:, 2] + 40
    elevation, e_spatial, e_timing = predict_elevation(bank, obs, prior, point, shifts)
    terms = evaluate(measured, prediction, elevation, score)
    gradient = np.einsum("nk,nki->i", terms["prediction_gradient"], spatial)
    gradient += np.einsum("nk,nki->i", terms["elevation_gradient"], e_spatial)
    t_gradient = np.sum(
        terms["prediction_gradient"] * timing + terms["elevation_gradient"] * e_timing, axis=0
    )

    def value(p, t):
        prediction = predict_orbits(bank, obs, prior, p, t)[0]
        elevation = predict_elevation(bank, obs, prior, p, t)[0]
        return evaluate(measured, prediction, elevation, score)["nll"]

    for axis in range(2):
        d = np.eye(2)[axis] * 0.001
        np.testing.assert_allclose(
            (value(point + d, shifts) - value(point - d, shifts)) / 0.002,
            gradient[axis],
            rtol=1e-5,
            atol=1e-7,
        )
    for j in range(6):
        d = np.eye(6)[j] * 0.001
        np.testing.assert_allclose(
            (value(point, shifts + d) - value(point, shifts - d)) / 0.002,
            t_gradient[j],
            rtol=1e-5,
            atol=1e-7,
        )
