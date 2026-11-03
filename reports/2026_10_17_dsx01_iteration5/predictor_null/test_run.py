import numpy as np
import pytest
from run import permuted_indices


def test_preserves_lane_distributions_and_excluded_training():
    receiver = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    channel = np.array([1, 1, 2, 2, 1, 1, 2, 2])
    mask = np.array([False, False, True, True, True, True, True, True])
    order = permuted_indices(receiver, channel, mask, np.random.default_rng(101))
    np.testing.assert_array_equal(order[~mask], np.flatnonzero(~mask))
    np.testing.assert_array_equal(np.sort(order), np.arange(8))
    np.testing.assert_array_equal(receiver[order], receiver)
    np.testing.assert_array_equal(channel[order], channel)
    again = permuted_indices(receiver, channel, mask, np.random.default_rng(101))
    np.testing.assert_array_equal(order, again)


def test_shape_or_nonboolean_mask_is_rejected():
    with pytest.raises(ValueError):
        permuted_indices([0], [1, 2], np.array([True]), np.random.default_rng(0))
    with pytest.raises(ValueError):
        permuted_indices([0], [1], np.array([1]), np.random.default_rng(0))
