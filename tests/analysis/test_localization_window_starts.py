import numpy as np
import pytest
from leo.analysis.localization_window_starts import constituent_window_starts


def test_scan_specific_nuisances_survive_shared_position_transfer():
    states = [np.array([8., 9., .2, 3.]), np.array([-4., 5., -.7, 6., 7.])]
    columns = [np.array([0, 1, 2, 3]), np.array([0, 1, 4, 5, 6])]
    starts = constituent_window_starts(states, columns, np.array([[8., 9.], [-4., 5.]]), 7)
    np.testing.assert_array_equal(starts, [[8., 9., .2, 3., -.7, 6., 7.], [-4., 5., .2, 3., -.7, 6., 7.]])
    starts[0, 2] = 100
    assert starts[1, 2] == .2 and states[0][2] == .2


def test_scan_order_does_not_change_transferred_state():
    states = [np.array([1., 2., 3.]), np.array([4., 5., 6.])]
    columns = [np.array([0, 1, 2]), np.array([0, 1, 3])]
    positions = np.array([[10., 11.]])
    np.testing.assert_array_equal(constituent_window_starts(states, columns, positions, 4),
        constituent_window_starts(states[::-1], columns[::-1], positions, 4))


@pytest.mark.parametrize('columns,dimension', [
    ([np.array([0,1,2]),np.array([0,1,2])],4),
    ([np.array([0,1,2]),np.array([0,1,4])],5),
    ([np.array([0,1,2]),np.array([1,0,3])],4),
    ([np.array([0,1,2]),np.array([0.,1.,3.])],4),
])
def test_rejects_ambiguous_or_incomplete_maps(columns, dimension):
    with pytest.raises(ValueError):
        constituent_window_starts([np.ones(3), np.ones(3)], columns, np.zeros((1,2)), dimension)
