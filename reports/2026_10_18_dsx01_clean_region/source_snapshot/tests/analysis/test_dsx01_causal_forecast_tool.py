"""Causality and bounded prior-mean checks for orbit innovation extrapolation."""

import sys
from math import lgamma
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import dsx01_causal_forecast as forecast  # noqa: E402


def test_trend_extrapolates_opposite_previous_innovation_and_caps_mean():
    z = np.array([1.0, -0.5, 0.0, 0.2])
    np.testing.assert_allclose(forecast.trend_mean(z, 20, 10, 0.5), [-1.0, 0.5, 0.0, -0.2])
    np.testing.assert_allclose(
        forecast.trend_mean(z, 20, 10, 0.5, phase_only=True), [-1.0, 0.0, 0.0, 0.0]
    )
    np.testing.assert_allclose(forecast.trend_mean(z, 20, 10, 0), np.zeros(4))
    assert max(abs(forecast.trend_mean(z * 100, 200, 10, 1))) == pytest.approx(3)
    with pytest.raises(ValueError, match="epoch gap"):
        forecast.trend_mean(z, 20, 0, 0.5)


def test_history_selection_uses_only_past_transitions_and_prefers_correct_trend(monkeypatch):
    monkeypatch.setattr(forecast, "Satrec", SimpleNamespace(twoline2rv=lambda *args: object()))

    def states(catalogue, origin, times):
        assert len(catalogue.satellites) == 3
        assert len(times) >= 3
        p = np.array([[[0.0, 1.0, 7000.0]], [[0.0, 0.0, 7000.0]], [[0.0, -1.0, 7000.0]]])
        v = np.tile(np.array([[[0.0, 1.0, 0.0]]]), (3, 1, 1))
        return p, v, np.ones((3, 1), bool)

    monkeypatch.setattr(forecast, "ecef_states", states)
    versions = [
        dict(epoch=int(k * 10e9), collected_utc_ns=int(k * 10e9), lines=["x", "y"])
        for k in range(4)
    ]
    result = forecast.select_history_shrinkage({"42": versions}, int(25e9))
    assert result["shrinkage"] == 1.0
    assert len(result["transitions"]) == 1
    assert result["transitions"][0]["validation_time_ns"] == int(20e9)
    result = forecast.select_history_shrinkage({"42": versions}, int(15e9))
    assert result["shrinkage"] == 0.0 and not result["transitions"]


def test_export_removes_future_entries_and_all_following_fields():
    from export_dsx01_causal_forecast_inputs import causal_inventory

    data = {
        "42": dict(
            past_versions=[
                dict(epoch=1, collected_utc_ns=2, lines=["a", "b"]),
                dict(epoch=3, collected_utc_ns=9, lines=["c", "d"]),
                dict(epoch=9, collected_utc_ns=2, lines=["future epoch", "early collection"]),
            ],
            first_following_newer_version=dict(lines=["secret", "future"]),
        )
    }
    assert causal_inventory(data, 5) == {
        "42": [dict(epoch=1, collected_utc_ns=2, lines=["a", "b"])]
    }


def test_nonzero_mean_bound_and_decoding_against_independent_quadrature(monkeypatch):
    from dsx01_joint_marginal import JointMarginal

    p = forecast.CausalForecast.__new__(forecast.CausalForecast)
    p.values = np.array([3.0, 5.0])
    p.q = np.ones(2)
    p.point_noise = np.ones(2)
    p.noise_groups = np.zeros(2, dtype=int)
    p.prior_mean = np.array([2.4])
    p.diagonal_logvolume = 0.0
    u = np.array([[1.0], [2.0]])
    monkeypatch.setattr(
        JointMarginal, "calculate", lambda self, x: dict(features=u, intercept=np.zeros(2))
    )
    result = p.calculate(np.zeros(2))
    np.testing.assert_allclose(
        result["conditional_residual_hz"], p.values - u @ result["coefficient"]
    )
    np.testing.assert_allclose(result["latent_coefficient"], result["coefficient"] - p.prior_mean)
    grid = np.linspace(-10.0, 15.0, 100001)
    rss = np.sum((p.values[:, None] - u * grid) ** 2, axis=0)
    logdensity = lgamma(3) - lgamma(2) - np.log(4 * np.pi) - 3 * np.log1p(rss / 4)
    logdensity += -0.5 * (grid - 2.4) ** 2 - 0.5 * np.log(2 * np.pi)
    shift = logdensity.max()
    mass = np.trapezoid(np.exp(logdensity - shift), grid)
    exact = -2 * (np.log(mass) + shift)
    posterior_mean = np.trapezoid(grid * np.exp(logdensity - shift), grid) / mass
    assert exact - 1e-8 <= result["negative_twice_elbo"] < exact + 0.5
    assert result["coefficient"][0] == pytest.approx(posterior_mean, abs=0.1)
