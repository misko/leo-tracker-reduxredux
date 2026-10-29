"""Constant component biases cannot erase slope or identify incompatible members."""

import importlib
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.research.component_frequency_bias import profile_component_bias


@pytest.fixture
def sample(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    matching = importlib.import_module("analyze_dsx01_fixed_site")
    t = np.linspace(0.0, 60.0, 25)
    physical = 40000.0 - 1000 * t + 2 * t * t
    tracks = [
        dict(receiver=rx, channel=1, rf_hz=11.5e9, times=t, values=physical + 800.0, key=str(rx))
        for rx in (1, 2)
    ]
    bank = dict(
        time_s=t,
        doppler_0=np.array([physical, physical + 10000.0]),
        elevation_deg=np.full((2, len(t)), 45.0),
    )
    return matching, matching.statistics([("shared", tracks)], bank, {"1": 0.0})


def test_zero_bias_exactly_nests_native_alias_score(sample):
    matching, stats = sample
    beta = np.zeros(8)
    best, rms, aliases, mse = matching.evaluate(stats, beta)
    result = profile_component_bias(stats, beta, bias_sigma_hz=0.0)
    np.testing.assert_array_equal(result.best, best)
    np.testing.assert_array_equal(result.aliases, aliases)
    np.testing.assert_allclose(result.score, mse, atol=1e-6)
    np.testing.assert_allclose(result.rms_hz, rms, atol=1e-6)


def test_shared_constant_posterior_and_complexity_penalty(sample):
    _, stats = sample
    result = profile_component_bias(stats, np.zeros(8), bias_sigma_hz=1000.0)
    expected = 50 * 800 / (50 + 150**2 / 1000**2)
    assert result.bias_hz[0, 0] == pytest.approx(expected)
    assert result.rms_hz[0] < 1
    assert result.score[0, 0] > result.residual_mse[0, 0]
    assert result.best.tolist() == [0]


def test_constant_cannot_absorb_slope_error(sample):
    _, stats = sample
    # Add a centered linear residual without changing the component mean.
    slope = 20000.0
    stats["rss"] += stats["xx"][:, None] * slope * slope
    stats["xz"] += stats["xx"][:, None] * slope
    result = profile_component_bias(stats, np.zeros(8), bias_sigma_hz=1000.0)
    assert result.rms_hz[0] > 2000


def test_members_must_share_a_single_bias(sample):
    _, stats = sample
    stats["mean"][0] += 2000
    stats["mean"][1] -= 2000
    result = profile_component_bias(stats, np.zeros(8), bias_sigma_hz=1000.0)
    assert result.rms_hz[0] >= 2000


def test_invalid_prior_is_rejected(sample):
    _, stats = sample
    with pytest.raises(ValueError):
        profile_component_bias(stats, np.zeros(8), bias_sigma_hz=-1.0)
