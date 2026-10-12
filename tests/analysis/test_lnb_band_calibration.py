from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.lnb_band_calibration import calibrated_band_observations
from leo.application.hard60_runner import HARD60_SCORE
from tests.analysis.test_regional_position_bootstrap import bootstrap_fixture


def test_measurement_calibration_is_equivalent_to_prediction_shift_for_value_and_gradient():
    original, bank, prior, _ = bootstrap_fixture()
    original = replace(original, channel=np.where(np.arange(len(original.times_s)) % 8 < 4, 1, 5))
    raw_values = original.measured_hz.copy()
    derived, correction = calibrated_band_observations(original, (-20290.0, 39264.0))
    measured = Hard60Objective(derived, bank, prior, HARD60_SCORE)
    predicted = Hard60Objective(
        original, bank, prior, HARD60_SCORE, receiver_baseline_hz=correction
    )
    vector = np.array([3.1, -5.2, 600.0, 0.5, -600.0, 0.5, 0.0, 0.3, 0.03, -0.04])
    a, b = measured.evaluate(vector), predicted.evaluate(vector)
    assert a[0] == pytest.approx(b[0], abs=1e-9)
    np.testing.assert_allclose(a[1], b[1], atol=1e-8, rtol=1e-9)
    np.testing.assert_allclose(a[2].responsibilities, b[2].responsibilities, atol=1e-11)
    np.testing.assert_array_equal(original.measured_hz, raw_values)
    assert derived.window_ids == original.window_ids
    for key in ("times_s", "rf_hz", "receiver", "channel", "margin"):
        np.testing.assert_array_equal(getattr(derived, key), getattr(original, key))


def test_no_high_band_or_zero_correction_retains_the_original_object():
    original, _, _, _ = bootstrap_fixture()
    derived, correction = calibrated_band_observations(original, (-20290.0, 39264.0))
    assert derived is original and not np.any(correction)
    assert calibrated_band_observations(original, (0.0, 0.0))[0] is original
    for values in ((0.0,), (np.nan, 0.0), (0.0, np.inf)):
        with pytest.raises(ValueError):
            calibrated_band_observations(original, values)
