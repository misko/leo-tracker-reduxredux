import numpy as np
from header_block_rank import rank
from shared_header_coordinates import shared_rules


def test_extracts_one_shared_coordinate_with_fixed_inversion():
    rng = np.random.default_rng(89)
    x = rng.integers(0, 2, size=(78, 3), dtype=np.uint8)
    bits = np.column_stack([x[:, 0], x[:, 1], x[:, 0] ^ 1, x[:, 2]])
    rules = shared_rules(bits, 2)
    assert rank([r["word"] for r in rules]) == 1
    assert rules[0]["constant"] == 1
    np.testing.assert_array_equal(rules[0]["trace"], x[:, 0])
