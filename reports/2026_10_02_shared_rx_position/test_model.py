import numpy as np
import pytest
from model import ALIAS_HZ, bounded_line, fit_shared


def synthetic(intercept, slope):
    times = np.stack([np.linspace(-140 + index * 35, -115 + index * 35, 20) for index in range(8)])
    branch = np.arange(8) - 4
    correct = intercept + slope * times + branch[:, None] * ALIAS_HZ
    residual = np.stack(
        [correct, correct + 15000 + 300 * (times - times.mean(axis=1)[:, None])], axis=1
    )
    mask = np.ones(times.shape, dtype=bool)
    visible = np.ones(residual.shape[:2], dtype=bool)
    return times, residual, mask, visible


@pytest.mark.parametrize("slope", [-9.0, 0.0, 8.0])
def test_shared_line_recovery(slope):
    times, residual, mask, visible = synthetic(42000, slope)
    fit = fit_shared(residual, times, mask, visible, 10)
    assert fit["slope"] == pytest.approx(slope, abs=0.01)
    assert fit["intercept"] == pytest.approx(42000, abs=0.1)
    assert np.all(fit["selected"] == 0)


def test_bound_and_refitted_intercept():
    times = np.arange(100, dtype=float)
    intercept, slope = bounded_line(times, 30000 + 30 * times, np.ones(100), 10)
    assert slope == 10
    assert intercept == pytest.approx(30990)


def test_alias_invariance():
    times, residual, mask, visible = synthetic(-75000, 5)
    original = fit_shared(residual, times, mask, visible, 10)
    shifted = fit_shared(residual + 7 * ALIAS_HZ, times, mask, visible, 10)
    assert shifted["intercept"] == pytest.approx(original["intercept"], abs=0.01)
    assert shifted["slope"] == pytest.approx(original["slope"], abs=0.01)


def test_evaluation_rows_do_not_change_fit():
    times, residual, mask, visible = synthetic(-75000, 5)
    mask[:, ::3] = False
    original = fit_shared(residual, times, mask, visible, 10)
    residual[:, :, ::3] += 100000
    changed = fit_shared(residual, times, mask, visible, 10)
    assert changed["intercept"] == pytest.approx(original["intercept"])
    assert changed["slope"] == pytest.approx(original["slope"])


def test_zero_slope_control():
    times, residual, mask, visible = synthetic(-75000, 0)
    fit = fit_shared(residual, times, mask, visible, 0)
    assert fit["slope"] == 0
    assert fit["intercept"] == pytest.approx(-75000, abs=0.01)


def test_outlier_track_is_not_allowed_to_drive_line():
    times, residual, mask, visible = synthetic(-18000, 4)
    residual[-1] += 50000
    fit = fit_shared(residual, times, mask, visible, 10)
    assert fit["slope"] == pytest.approx(4, abs=0.01)
    assert fit["intercept"] == pytest.approx(-18000, abs=0.1)


def test_no_visible_candidates():
    times, residual, mask, visible = synthetic(-18000, 4)
    visible[:] = False
    fit = fit_shared(residual, times, mask, visible, 10)
    assert np.all(np.isinf(fit["costs"]))
