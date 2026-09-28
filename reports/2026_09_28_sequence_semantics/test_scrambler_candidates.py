import numpy as np
from phase_lfsr import extend
from scrambler_candidates import tap_shift


def test_tap_relation_matches_entire_period_not_only_seed():
    seed = np.array([1] + [0] * 14, dtype=np.uint8)
    b = extend(seed, 32767)
    for advance in [8, -8]:
        c = b ^ np.roll(b, -advance)
        high = b ^ c
        np.testing.assert_array_equal(np.roll(c, -tap_shift(b, advance)), high)
