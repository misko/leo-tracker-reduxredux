import numpy as np
import pytest
from satellite65745_glrt_audit import correlation, residualize, slope


def test_slope_and_robust_slope_recover_linear_trend():
    times = np.arange(20.) + 240.
    values = 6. * (times - 250.)
    result = slope(times, values)
    assert result["ols_hz_per_s"] == pytest.approx(6.)
    assert result["theil_sen_hz_per_s"] == pytest.approx(6.)
    assert result["detrended_rms_hz"] == pytest.approx(0.)
    values[-1] += 10000.
    assert slope(times, values)["theil_sen_hz_per_s"] == pytest.approx(6.)


def test_partial_removal_controls_time_and_channel_offset():
    times = np.arange(20.)
    channel = np.arange(20) % 2
    design = np.column_stack([np.ones(20), times, channel])
    assert np.linalg.norm(residualize(5 * times + 100 * channel, design)) < 1e-9
    assert correlation(np.ones(20), times) is None


def test_degenerate_time_support_is_unavailable():
    assert not slope([1., 1., 1.], [0., 1., 2.])["available"]
