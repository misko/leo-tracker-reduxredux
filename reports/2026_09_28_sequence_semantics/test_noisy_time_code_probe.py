import numpy as np
from noisy_time_code_probe import choose_check


def test_noisy_nontrivial_relation_survives_discovery_search():
    rng = np.random.default_rng(516)
    bits = rng.integers(0, 2, (4000, 14), dtype=np.uint8)
    bits[:, 8] = bits[:, 0] ^ bits[:, 1] ^ bits[:, 7]
    bits[:80, 8] ^= 1
    mask, score, _ = choose_check(bits)
    assert mask == sum(1 << j for j in [0, 1, 7, 8])
    assert abs(score - 0.96) < 1e-12
