import numpy as np
import pytest
from rf_center_audit import center_residuals


def test_both_edges_and_tuner_rounding():
    np.testing.assert_array_equal(
        center_residuals([10709687498, 11459687500, 10940312502], [1, 4, 1]),
        [-2, 0, 2],
    )


def test_megahertz_error_is_not_hidden_by_nearest_edge():
    assert center_residuals([10710687500], [1])[0] == 1_000_000


@pytest.mark.parametrize("rf,channel", [
    ([], []), ([np.nan], [1]), ([10709687500], [1.5]),
    ([10709687500], [0]), ([10709687500], [9]), ([10709687500], [1, 2]),
])
def test_reject_invalid_coordinates(rf, channel):
    with pytest.raises(ValueError):
        center_residuals(rf, channel)
