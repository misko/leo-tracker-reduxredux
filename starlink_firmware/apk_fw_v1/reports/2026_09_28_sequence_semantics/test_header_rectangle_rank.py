import numpy as np
from header_block_rank import rank
from header_rectangle_rank import block, packed_rows


def test_rectangle_coordinates_and_column_permutation_invariance():
    data = np.arange(2 * 6 * 1024).reshape(2, 6, 1024)
    selected = block(data, (0, 2, 5), 900, 38)
    assert selected.shape == (2, 114)
    assert selected[0, 38] == data[0, 2, 900]
    rng = np.random.default_rng(114)
    bits = rng.integers(0, 2, size=(40, 114), dtype=np.uint8)
    assert rank(packed_rows(bits)) == rank(packed_rows(bits[:, ::-1]))
