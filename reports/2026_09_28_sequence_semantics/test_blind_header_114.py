import numpy as np
from blind_header_114 import check_score, mixed_null_check, pair_windows


def test_recovers_unknown_generators_and_rejects_corruption():
    rng = np.random.default_rng(847)

    def encoded():
        data = np.pad(rng.integers(0, 2, (20, 32)), ((0, 0), (6, 6)))
        taps = (np.array([0o117, 0o155, 0o127])[:, None] >> np.arange(6, -1, -1)) & 1
        code = np.lib.stride_tricks.sliding_window_view(data, 7, axis=-1) @ taps.T % 2
        return pair_windows(code.reshape(20, 114), 0, (0, 1))

    mask = mixed_null_check(encoded())
    assert mask is not None
    assert check_score(encoded(), mask) == 1
    bad = encoded()
    bad[:, (mask & -mask).bit_length() - 1] ^= 1
    assert check_score(bad, mask) == -1


def test_random_and_constant_data_do_not_support_a_check():
    rng = np.random.default_rng(848)
    assert mixed_null_check(rng.integers(0, 2, (200, 14))) is None
    assert mixed_null_check(np.zeros((200, 14))) is None
