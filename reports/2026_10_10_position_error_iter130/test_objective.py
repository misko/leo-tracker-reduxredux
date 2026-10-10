import runpy
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np

from leo.analysis.hard60_satellite_correction import SatelliteCorrection
from leo.analysis.regional_position_score import observer
from leo.application.hard60_runner import HARD60_SCORE
from leo.contracts.regional_position import RegionalPrior

api = runpy.run_path(str(Path(__file__).with_name("objective.py")))


def fixture():
    model = object.__new__(api["PhaseObjective"])
    model.prior = RegionalPrior(latitude_deg=38, longitude_deg=-121, altitude_m=0, radius_km=250)
    site, up = observer(model.prior, [0, 0])
    rng = np.random.default_rng(123)
    k, n = 3, 4
    nodes = np.arange(-2.0, 3.0)
    starts = (
        site
        + 800 * up
        + np.array([[100.0, 200.0, 0.0], [-200.0, 300.0, 100.0], [300.0, -100.0, 50.0]])
    )
    rates = np.array([[1.0, 5.0, 2.0], [-3.0, 4.0, 1.0], [4.0, 1.0, -2.0]])
    model.bank = NS(
        numbers=np.arange(k),
        nodes_s=nodes,
        position_km=starts[:, None, :] + nodes[None, :, None] * rates[:, None, :],
        velocity_km_s=rates[:, None, :] + nodes[None, :, None] * np.array([0.01, 0.02, -0.01]),
    )
    model.observations = NS(
        times_s=np.array([-0.7, -0.2, 0.3, 0.8]), rf_hz=np.full(n, 1e10), measured_hz=np.zeros(n)
    )
    model.basis = np.linalg.svd(np.ones((1, k)), full_matrices=True)[2][1:].T
    model.satellite_basis = model.basis.copy()
    model.design = rng.normal(size=(n, 5))
    model.baseline = np.zeros(n)
    model.clock_design = rng.normal(size=(n, 9))
    model.precision = np.eye(9) / 100
    model.offset_slice = slice(3, 5)
    model.slope_slice = slice(5, 7)
    model.delta_time = np.tile(model.observations.times_s[:, None] / 100, (1, k))
    model.score = HARD60_SCORE
    vector = np.r_[0.1, 0.2, np.zeros(5), 0.02, 0.01, -0.01]
    clock = rng.normal(size=9)
    prediction = api["predict"](model, vector)[0]
    model.observations.measured_hz = prediction[:, 0] + 30
    return model, vector, clock


def test_all_spatial_timing_clock_satellite_gradients():
    model, vector, clock = fixture()
    _, g, cg, _ = model.evaluate_joint(vector, clock)
    for values, gradient, isclock in ((vector, g, False), (clock, cg, True)):
        for i in range(len(values)):
            h = 1e-4 if i < 2 and not isclock else 1e-5
            plus = values.copy()
            minus = values.copy()
            plus[i] += h
            minus[i] -= h
            if isclock:
                finite = (
                    model.evaluate_joint(vector, plus)[0] - model.evaluate_joint(vector, minus)[0]
                ) / (2 * h)
            else:
                finite = (
                    model.evaluate_joint(plus, clock)[0] - model.evaluate_joint(minus, clock)[0]
                ) / (2 * h)
            np.testing.assert_allclose(gradient[i], finite, atol=2e-5, rtol=1e-4)


def test_zero_relative_score_and_clock_parity_but_relative_derivative_changes():
    model, vector, clock = fixture()
    vector[8:] = 0
    old = object.__new__(SatelliteCorrection)
    old.__dict__.update(model.__dict__)
    a = model.evaluate_joint(vector, clock)
    b = old.evaluate_joint(vector, clock)
    np.testing.assert_allclose(a[0], b[0], atol=1e-10, rtol=0)
    np.testing.assert_allclose(a[1][:8], b[1][:8], atol=1e-7, rtol=0)
    np.testing.assert_allclose(a[2], b[2], atol=1e-10, rtol=0)
    assert np.max(abs(a[1][8:] - b[1][8:])) > 1e-4


def test_conversion_preserves_slope_prior_precision_and_layout():
    model, _, _ = fixture()
    model.precision[model.slope_slice, model.slope_slice] = np.eye(2) / 50**2
    result = api["convert"](model)
    assert result.__dict__.keys() == model.__dict__.keys()
    assert all(result.__dict__[k] is v for k, v in model.__dict__.items())
    np.testing.assert_array_equal(result.precision, model.precision)
