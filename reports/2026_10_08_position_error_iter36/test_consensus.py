import numpy as np
from consensus import PERIOD, propose, wrap


def test_recovers_line_across_alias_boundary_with_outliers():
    rng = np.random.default_rng(36)
    t = np.linspace(-150, 150, 200)
    residual = wrap(PERIOD / 2 - 100 + 43.2 * t + rng.normal(0, 20, len(t)))
    residual[::4] = rng.uniform(-PERIOD / 2, PERIOD / 2, len(t[::4]))
    result = propose(t, residual)[0]
    assert abs(wrap(result["intercept_hz"] - (PERIOD / 2 - 100))) < 10
    assert abs(result["slope_hz_s"] - 43.2) < 0.1
    assert result["support"] >= 150


def test_keeps_distinct_branches_and_is_deterministic():
    t = np.tile(np.linspace(-150, 150, 100), 2)
    residual = np.r_[1000 + 20 * t[:100], -30000 - 15 * t[100:]]
    result = propose(t, residual)
    assert len(result) == 2
    assert sorted(round(r["slope_hz_s"]) for r in result) == [-15, 20]
    assert result == propose(t, residual)


def test_rejects_insufficient_time_span():
    assert propose(np.arange(4), np.zeros(4)) == []
