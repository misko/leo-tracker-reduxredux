import numpy as np
import pytest

from leo.analysis.localization_epoch_profile import profile_unused_epochs


def test_shared_epoch_survives_until_last_track_removed():
    state = np.arange(9, dtype=float)
    first, gain = profile_unused_epochs(state, [1, 1, 3, 4], 4)
    np.testing.assert_array_equal(first, [0, 1, 2, 3, 4, 0, 6, 0, 8])
    assert gain == 2*(5**2+7**2)
    second, _ = profile_unused_epochs(first, [1, 3, 4], 4)
    np.testing.assert_array_equal(first, second)
    third, gain = profile_unused_epochs(second, [3, 4], 4)
    assert third[6] == 0 and gain == 2*6**2
    np.testing.assert_array_equal(state, np.arange(9))


def test_idempotence_and_exact_prior_minimum():
    state = np.arange(8, dtype=float)-3
    profiled, gain = profile_unused_epochs(state, [3], 3)
    assert gain == .5*4*(state@state-profiled@profiled)
    repeated, gain = profile_unused_epochs(profiled, [3], 3)
    assert gain == 0
    np.testing.assert_array_equal(repeated, profiled)


def test_invalid_assignment_and_shape_rejected():
    for assignments in [[-1], [4], [1.5]]:
        with pytest.raises(ValueError):
            profile_unused_epochs(np.zeros(8), assignments, 3)
    with pytest.raises(ValueError):
        profile_unused_epochs(np.zeros(7), [1], 3)
