import sys
from pathlib import Path

import numpy as np
import pytest
from native_elevation import predict_elevation as native

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026_10_09_position_error_iter57"))
from elevation import predict_elevation as oracle  # noqa: E402
from test_elevation import fixture  # noqa: E402


def test_native_matches_verified_numpy_geometry():
    args = fixture()
    actual, expected = native(*args), oracle(*args)
    for a, b in zip(actual, expected, strict=True):
        np.testing.assert_allclose(a, b, atol=1e-7, rtol=1e-6)


def test_bad_shapes_nonfinite_and_outside_support_raise():
    bank, obs, prior, point, shifts = fixture()
    for invalid in (np.zeros(5), np.full(6, np.nan), np.full(6, -100.0)):
        with pytest.raises(ValueError):
            native(bank, obs, prior, point, invalid)
