import numpy as np
from odd_parity_probe import best_odd_check, check_score


def test_odd_check_recovers_known_three_bit_constraint_on_new_rows():
    rng = np.random.default_rng(1313)
    w = rng.integers(0, 2, (4000, 14), dtype=np.uint8)
    w[:, 8] = w[:, 1] ^ w[:, 7]
    mask, score = best_odd_check(w[:2000])
    assert mask == (1 << 1) | (1 << 7) | (1 << 8)
    assert score == 1
    assert check_score(w[2000:], mask) == 1
    w[2000:, 8] ^= 1
    assert check_score(w[2000:], mask) == -1
