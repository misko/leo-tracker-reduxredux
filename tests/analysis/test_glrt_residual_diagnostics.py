import numpy as np
import pytest

from leo.analysis.glrt_residual_diagnostics import signal_candidate_residuals, weighted_median
from leo.analysis.sparse_glrt_likelihood import FrequencyEvidence
from leo.analysis.wrapped_glrt_likelihood import WrappedConfig, wrapped_ratios


def test_candidate_and_satellite_responsibilities_preserve_mass_and_alias_invariance():
    data = FrequencyEvidence(
        ids=("a", "b", "c"),
        frequency_hz=np.array([[25.0, 4000.0], [300.0, -5000.0], [8000.0, 400.0]]),
        candidate_weight=np.array([[0.6, 0.4], [0.2, 0.8], [0.5, 0.5]]),
        signal_probability=np.array([0.9, 0.0, 0.7]),
        group=np.zeros(3, int),
        time_s=np.arange(3.0),
    )
    prediction = np.array([[0.0, 4000.0], [300.0, -5000.0], [8000.0, 500.0]])
    opportunity = np.array([[1.0, 1.0], [1.0, 1.0], [0.0, 1.0]])
    design, beta, weights = np.ones((3, 1)), np.array([20.0]), np.array([0.1, 0.6, 0.3])
    cfg = WrappedConfig()
    residual, mass, clutter = signal_candidate_residuals(
        data, prediction, opportunity, design, beta, cfg, weights
    )
    assert residual.shape == mass.shape == (3, 2, 2)
    np.testing.assert_allclose(mass.sum(axis=(1, 2)) + clutter, 1)
    assert clutter[1] == 1
    assert np.all(mass[2, :, 0] == 0)
    ratio = wrapped_ratios(data, prediction, opportunity, design, beta, cfg)
    q = data.signal_probability[:, None] * opportunity
    expected = (ratio - (1 - q)) * weights[None, 1:] / (weights[0] + ratio @ weights[1:])[:, None]
    np.testing.assert_allclose(mass.sum(axis=1), expected, atol=1e-12)
    shifted = FrequencyEvidence(
        ids=data.ids,
        frequency_hz=data.frequency_hz + cfg.period_hz,
        candidate_weight=data.candidate_weight,
        signal_probability=data.signal_probability,
        group=data.group,
        time_s=data.time_s,
    )
    other = signal_candidate_residuals(shifted, prediction, opportunity, design, beta, cfg, weights)
    np.testing.assert_allclose(other[0], residual, atol=1e-9)
    np.testing.assert_allclose(other[1], mass, atol=1e-9)
    with pytest.raises(ValueError, match="normalized"):
        signal_candidate_residuals(data, prediction, opportunity, design, beta, cfg, [1, 1, 1])


def test_weighted_median_does_not_count_candidate_alternatives_as_equal_observations():
    assert weighted_median([10, 20, 30], [0.1, 0.8, 0.1]) == 20
    assert weighted_median([10, 20], [0, 0]) is None
    with pytest.raises(ValueError, match="nonnegative"):
        weighted_median([10, 20], [1, -1])
