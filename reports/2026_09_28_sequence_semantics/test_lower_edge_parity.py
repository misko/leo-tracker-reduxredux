import numpy as np
from lower_edge_parity import discover


def test_finds_copy_and_xor_without_fixed_column():
    rng = np.random.default_rng(83)
    x = rng.integers(0, 2, size=(39, 2), dtype=np.uint8)
    bits = np.column_stack([x, x[:, 0] ^ x[:, 1], x[:, 0] ^ 1, np.zeros(39, dtype=np.uint8)])
    rows, n = discover(bits, np.ones_like(bits, bool))
    assert n == 4
    assert (0, 3) in rows and (0, 1, 2) in rows
    assert all(4 not in r for r in rows)
