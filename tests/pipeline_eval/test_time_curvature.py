import numpy as np
import pytest

from tools.pipeline_eval.variants.time_curvature import active, measure


def test_exact_integral_and_invariance_to_collinear_interior_measurement():
    measured = measure([0, 10, 20], [0, 1000, 0], 10)
    subdivided = measure([0, 2, 5, 10, 20], [0, 200, 500, 1000, 0], 10)
    assert measured == pytest.approx((20.0, 1000 / np.sqrt(12)), rel=1e-13)
    assert subdivided == pytest.approx(measured, rel=1e-13)
    assert active({"times": [0, 10, 20], "values": [0, 1000, 0]}, 10)


def test_integral_skips_disconnected_clock_spans_and_rejects_short_support():
    measured = measure([0, 10, 20, 80], [0, 1000, 0, 10000], 10)
    assert measured == pytest.approx((20, 1000 / np.sqrt(12)))
    assert not active({"times": [0, 10, 40], "values": [5, 2000, -2000]}, 10)


def test_removes_affine_baseline_and_uses_only_monotone_finite_points():
    times = np.array([5, 12, 21, 28, 35])
    result = measure(times, 30 * times + 200_000, 10)
    assert result == pytest.approx((30, 0), abs=1e-10)
    assert measure([], [], 10) == (0, 0)
    with pytest.raises(ValueError, match="strictly increasing"):
        measure([3, 3], [2, -2], 10)
    with pytest.raises(ValueError, match="finite"):
        measure([2, 3], [1, np.inf], 10)
