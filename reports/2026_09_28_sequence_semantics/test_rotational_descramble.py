import numpy as np
from rotational_descramble import pn_planes


def test_symbol_advance_and_second_plane_recurrence():
    seed = np.random.default_rng(16383).integers(0, 2, 15, dtype=np.uint8)
    low, high = pn_planes(seed, np.array([2, 3]), np.arange(1040))
    np.testing.assert_array_equal(low[0, 1020:], low[1, :20])
    np.testing.assert_array_equal(high[0, 1020:], high[1, :20])
    for plane in [low, high]:
        np.testing.assert_array_equal(plane[:, 15:] ^ plane[:, 1:-14] ^ plane[:, :-15], 0)
