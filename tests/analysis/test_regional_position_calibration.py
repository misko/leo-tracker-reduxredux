from dataclasses import replace

import numpy as np
import pytest
from test_regional_position_bootstrap import bootstrap_fixture
from test_regional_position_score import synthetic_inputs

from leo.analysis.regional_position_bootstrap import bootstrap_position
from leo.analysis.regional_position_calibration import calibrate_position, receiver_correction
from leo.analysis.regional_position_score import WindowLikelihood


def test_correction_matches_regularized_fit_and_has_no_constant_or_line_knots():
    observations, _, _ = synthetic_inputs()
    n = len(observations.window_ids)
    signal = 40 * np.sin(observations.times_s / 17)
    terms = WindowLikelihood(0, np.ones((n, 1)), np.zeros(n), np.zeros((n, 1)), signal[:, None])
    result = receiver_correction(observations, terms)
    assert result.support_rows == tuple(range(n))
    assert np.all(np.isfinite(result.values_hz))
    np.testing.assert_allclose(result.knots_hz.sum(axis=1), 0, atol=1e-10)
    np.testing.assert_allclose(
        result.knots_hz @ (result.nodes_s - result.nodes_s.mean()), 0, atol=1e-9
    )
    for rx in (0, 1):
        mask = observations.receiver == rx
        np.testing.assert_allclose(
            result.values_hz[mask],
            np.interp(observations.times_s[mask], result.nodes_s, result.knots_hz[rx]),
        )


def test_low_support_is_not_silently_qualified():
    observations, _, _ = synthetic_inputs()
    n = len(observations.window_ids)
    terms = WindowLikelihood(0, np.ones((n, 1)), np.zeros(n), np.zeros((n, 1)), np.zeros((n, 1)))
    with pytest.raises(ValueError, match="support on a receiver"):
        receiver_correction(observations, replace(terms, responsibilities=np.zeros((n, 1))))
    bad = np.zeros((n, 1))
    bad[observations.receiver == 1] = 700
    with pytest.raises(ValueError, match="support on a receiver"):
        receiver_correction(observations, replace(terms, residual_hz=bad))


def test_full_calibration_preserves_window_inventory_and_excludes_rf_from_baseline():
    observations, bank, prior, tracks = bootstrap_fixture()
    bootstrap = bootstrap_position(observations, bank, prior, [3, -5], tracks, maximum_seconds=10)
    result = calibrate_position(observations, bank, prior, bootstrap, maximum_seconds=10)
    assert result.prefit.converged and result.postfit.converged
    assert len(result.receiver_baseline_hz) == len(observations.window_ids)
    p = result.postfit.vector
    rx = observations.receiver
    expected = result.correction.values_hz + p[2 + 2 * rx]
    expected += p[3 + 2 * rx] * (observations.times_s - observations.time_center_s)
    np.testing.assert_allclose(result.receiver_baseline_hz, expected)
