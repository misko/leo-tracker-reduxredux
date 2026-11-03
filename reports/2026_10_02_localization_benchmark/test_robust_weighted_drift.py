import numpy as np
import pytest
from robust_weighted_drift import fit_receiver, track_weight


def blocks(outlier=False):
    result = []
    for index, center in enumerate(np.linspace(-120, 120, 12)):
        times = np.linspace(center - 5, center + 5, 20)
        values = 90000 + 4 * times
        if outlier and index == 0:
            values += 30000
        result.append(
            {
                "track_index": index,
                "times": times,
                "rows": np.arange(20),
                "residual": values[:, None],
                "visible": np.array([True]),
            }
        )
    return result


def test_count_weight_is_sublinear_and_capped():
    assert track_weight(25) == 5
    assert track_weight(100) == track_weight(10000) == 10


def test_robust_line_recovers_slope_despite_extreme_track():
    data = blocks(outlier=True)
    _, line = fit_receiver(data, {index: 0 for index in range(12)})
    assert line[0] == pytest.approx(90000, abs=5)
    assert line[1] == pytest.approx(4, abs=0.1)


def test_fixed_track_alias_shifts_do_not_change_line():
    data = blocks()
    identity = {index: 0 for index in range(12)}
    _, original = fit_receiver(data, identity)
    for index, block in enumerate(data):
        block["residual"] += (index - 4) * (1 / 4.4e-6)
    _, shifted = fit_receiver(data, identity)
    np.testing.assert_allclose(shifted, original, atol=1e-6)
