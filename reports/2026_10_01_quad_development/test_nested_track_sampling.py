import numpy as np
import pytest
from nested_track_sampling import nested_indices


def test_nested_coverage_preserves_base_and_prefix_policy():
    times = np.arange(44.)
    base = np.rint(np.linspace(0, 43, 8)).astype(int)
    sixteen = nested_indices(times, base, 16)
    thirtytwo = nested_indices(times, base, 32)
    assert np.array_equal(nested_indices(times, base, 8), base)
    assert set(base) <= set(sixteen) <= set(thirtytwo)
    assert np.array_equal(nested_indices(times, sixteen, 32), thirtytwo)
    assert np.all(np.diff(sixteen) > 0)
    assert len(sixteen) == 16 and len(thirtytwo) == 32


def test_chronological_ties_and_short_tracks():
    times = np.array([4., 0., 2., 2., 1., 3.])
    assert nested_indices(times, [0, 1], 3).tolist() == [1, 2, 0]
    assert nested_indices(times, [0, 1], 99).tolist() == [1, 4, 2, 3, 5, 0]


@pytest.mark.parametrize('times,base,limit', [([0., 1.], [0, 0], 2),
    ([0., 1.], [2], 2), ([0., np.nan], [0], 2), ([0., 1.], [0, 1], 1),
    ([0., 1.], [0.5], 2)])
def test_invalid_selection_rejected(times, base, limit):
    with pytest.raises(ValueError):
        nested_indices(times, base, limit)
