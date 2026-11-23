from statistics import median

import pytest

from reports.ALGO08.v3.long_solver_geography_figure import comparisons


def test_saved_solver_clocks_and_geographic_error_deltas():
    timings, deltas = comparisons()
    ratios = [candidate / named for _, named, candidate in timings]
    assert median(ratios) == pytest.approx(.661, abs=.001)
    assert sum(t[2] for t in timings) / sum(t[1] for t in timings) == pytest.approx(.510, abs=.001)
    assert deltas["c0"] == pytest.approx([-634, 254], abs=1)
    assert deltas["fitted_c"] == pytest.approx([-103, 393], abs=1)
