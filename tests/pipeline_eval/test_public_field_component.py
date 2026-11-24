"""Public frequency shape keeps its offset gauge and horizon semantics."""

from pathlib import Path
import sys

import numpy as np
import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports" / "ALGO08" / "v3"))
from public_field_component import compare, shape_metrics


def test_profile_preserves_signed_shape_and_removes_tone_level():
    target = np.array([70.0, -10.0, -80.0, -88.0, -95.0])
    shifts = np.array([[2.0, 0.0, -1.0, 0.0, 2.0]])
    candidates = np.array([target + 89239.0, -target - 15343.0])
    loss, rms = shape_metrics(target, candidates, np.tile(shifts, (2, 1)))
    repeated = shape_metrics(target + 1234.0, candidates - 20005.0, np.tile(shifts, (2, 1)))
    assert loss[0] < loss[1] and rms[0] == pytest.approx(0, abs=1e-10)
    np.testing.assert_allclose(repeated, (loss, rms), atol=1e-10)


def test_native_horizon_sign_required_even_with_matched_frequencies():
    frequency = np.array([[1., 2., 4., 8.]])
    altitude = np.array([[0., -1e-5, 1., 2.]])
    derivative = np.ones_like(frequency)
    horizon = np.array([[1, -1, 1, 1]], dtype=np.int8)
    tracks = [(np.arange(4), frequency[0], 4)]
    assert compare((frequency, altitude, derivative), (frequency, horizon, derivative), tracks,
                   np.array([123]))["horizon_sign_agrees"]
    with pytest.raises(ValueError, match="horizon"):
        compare((frequency, altitude, derivative), (frequency, -horizon, derivative), tracks, np.array([123]))
