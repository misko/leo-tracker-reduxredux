import numpy as np
import pytest
from satellite65745_peer_audit import fit_line


def test_channel_offsets_do_not_contaminate_slope():
    times = np.arange(240., 291.)
    channels = (times > 260).astype(int)
    values = 7 * (times - 265) + channels * 150
    result = fit_line(times, values, channels)
    assert result["slope_hz_s"] == pytest.approx(7.)


def test_robust_line_rejects_isolated_outlier():
    times = np.arange(240., 291.)
    values = 7 * (times - 265)
    values[-1] += 10000
    assert fit_line(times, values, robust=True)["slope_hz_s"] == pytest.approx(7., abs=.05)


def test_line_rejects_degenerate_times():
    with pytest.raises(ValueError, match="rank deficient"):
        fit_line(np.ones(10), np.arange(10.))
