"""Prior and data accounting use the fitted model's physical precision and powers."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("compare_dsx01_prior_bias_iterations")
    finally:
        sys.path.pop(0)


def test_cost_uses_posterior_mode_precision_and_frequency_likelihood_powers(tool):
    result = dict(
        coefficient=np.array([1.0, 2.0, 3.0]),
        coefficient_prior_precision=np.array([2.0, 0.5, 0.25]),
        noise_precision=np.array([2.0, 3.0]),
        conditional_residual_hz=np.array([80.0, 100.0, 120.0]),
        noise_gamma_cost=7.0,
        prior_gamma_cost=11.0,
        logvolume=13.0,
        elevation=np.array([-2.0, 0.0, 2.0]),
        full_objective_offset=3.0,
    )
    p = SimpleNamespace(
        calculate=lambda x: result,
        point_power=np.array([0.5, 1.0, 0.25]),
        values=np.ones(3),
        point_noise=np.array([80.0, 100.0, 120.0]),
        noise_groups=np.array([0, 0, 1]),
        members=[0],
        diagonal_logvolume=17.0,
    )
    actual = tool.parts(p, np.zeros(2))
    assert actual["weighted_data"] == 3.75
    assert actual["shared_prior"] == 4
    assert actual["curve_constant_prior"] == 2.25
    assert actual["relative_total"] == 59 and actual["full_total"] == 62


def test_radio_covariance_uses_prior_and_measurement_information_in_physical_coordinates(tool):
    covariance = tool.conditional_covariance(
        np.ones((3, 1)) * 2,
        np.ones(3) * 2,
        np.array([1.0, 0.5, 2.0]),
        np.array([0.25]),
    )
    np.testing.assert_allclose(covariance, [[1 / (0.25 + 1 + 0.5 + 2)]])


def test_native_replay_seed_preserves_saved_coordinates_and_explicit_aliases(tool, monkeypatch):
    captured = {}

    def initialize(self, scan, seed, fitted_c, **kwargs):
        captured.update(seed=seed, **kwargs)

    monkeypatch.setattr(tool.NativeDrift, "__init__", initialize)
    native = np.arange(44).reshape(2, 22)
    fit = dict(
        state=dict(beta=np.zeros(8), smooth=native, phases=[0]),
        rows=[],
        aliases=[2],
        diagnostics=dict(noise_sigma_hz=100, phase_reference_s=[0.1], point_noise_sigma_hz=[80]),
    )
    tool.problem_for(SimpleNamespace(rx_basis=[np.zeros((3, 11))]), fit, "native_band")
    assert captured["seed"]["state"]["smooth"].shape == (2, 11)
    assert captured["aliases"] == [2]
    np.testing.assert_array_equal(fit["state"]["smooth"], native)
